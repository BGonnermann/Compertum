import hashlib,json,sys
from pathlib import Path
from uuid import uuid4
import pytest
from test_persistence import owned
from test_storage import manager
sys.path.insert(0,str(Path(__file__).parent/'helpers'))
from data_fixture import batch,encoded
from compertum.data.publication import publish_snapshot
from compertum.data import DataError

def test_native_publication_preserves_exact_input_and_is_idempotent(owned):
 storage=manager(owned);task=str(uuid4());raw=encoded(batch())
 first=publish_snapshot(storage,task,raw,maximum_bytes=32768)
 assert first['status']=='OFFLINE_COMPONENT_VERIFIED'
 path=storage.root/first['artifact']['path'];bundle=json.loads(path.read_bytes())
 assert bundle['original_utf8'].encode()==raw and bundle['input_sha256']==hashlib.sha256(raw).hexdigest()
 assert publish_snapshot(storage,task,raw,maximum_bytes=32768)==first
 assert len(storage.reservations())==1
 path.write_text('corrupt retained output')
 with pytest.raises(DataError,match='PUBLICATION_CORRUPT'):publish_snapshot(storage,task,raw,maximum_bytes=32768)

def test_rejection_retains_bad_synthetic_input_but_sensitive_input_is_hash_only(owned):
 storage=manager(owned);task=str(uuid4());b=batch();b['bars'].pop();raw=encoded(b)
 rejected=publish_snapshot(storage,task,raw,maximum_bytes=32768)
 assert rejected['status']=='REJECTED' and rejected['reason']=='MISSING_ROW'
 bundle=json.loads((storage.root/rejected['artifact']['path']).read_bytes());assert bundle['original_utf8'].encode()==raw
 secret=b'{"password":"never-retain-this-value"}'
 receipt=publish_snapshot(storage,task,secret,maximum_bytes=32768)
 saved=(storage.root/receipt['artifact']['path']).read_bytes()
 assert receipt['reason']=='SENSITIVE_INPUT' and b'never-retain-this-value' not in saved
 assert json.loads(saved)['original_utf8'] is None

def test_budget_is_aggregate_immutable_and_corrections_create_new_artifacts(owned):
 storage=manager(owned);task=str(uuid4());b=batch();first=publish_snapshot(storage,task,encoded(b),maximum_bytes=24000)
 b['bars'][0]['close']=b['bars'][1]['close']='106';second=publish_snapshot(storage,task,encoded(b),maximum_bytes=24000)
 assert first['snapshot_sha256']!=second['snapshot_sha256']
 assert (storage.root/first['artifact']['path']).exists()
 with pytest.raises(DataError,match='OUTPUT_BUDGET_CONFLICT'):publish_snapshot(storage,task,encoded(b),maximum_bytes=48000)
 for i in range(30):
  b['source']['vintage']=f'correction-{i}'
  try:publish_snapshot(storage,task,encoded(b),maximum_bytes=24000)
  except DataError as error:
   assert error.code=='OUTPUT_BUDGET';break
 else:pytest.fail('aggregate output cap was not enforced')
 assert sum(r['written'] for r in storage.reservations())<=24000


def test_escaped_sensitive_rejection_never_retains_encoded_secret(owned):
 storage=manager(owned);raw=b'{"\\u0070assword":"never-retain-this-value"}'
 receipt=publish_snapshot(storage,str(uuid4()),raw,maximum_bytes=32768)
 saved=(storage.root/receipt['artifact']['path']).read_bytes()
 assert receipt['reason']=='SENSITIVE_INPUT' and b'never-retain-this-value' not in saved


def test_interrupted_publication_preserves_orphan_and_refuses_success(owned):
 storage=manager(owned);task=str(uuid4());raw=encoded(batch());digest=hashlib.sha256(raw).hexdigest()
 path=storage.root/f'artifacts/runs/{task}/data/input-{digest}.json';path.parent.mkdir(parents=True);path.write_bytes(b'orphaned-fixture')
 with pytest.raises(DataError,match='PUBLICATION_INCOMPLETE'):publish_snapshot(storage,task,raw,maximum_bytes=32768)
 assert path.read_bytes()==b'orphaned-fixture'


def test_oversized_corruption_is_rejected_before_large_read(owned,monkeypatch):
 storage=manager(owned);task=str(uuid4());raw=encoded(batch());receipt=publish_snapshot(storage,task,raw,maximum_bytes=32768)
 target=storage.root/receipt['artifact']['path'];expected=receipt['artifact']['size_bytes'];target.write_bytes(b'x'*100000)
 original_open=Path.open
 class BoundedRead:
  def __init__(self,stream):self.stream=stream
  def __enter__(self):return self
  def __exit__(self,*args):self.stream.close()
  def __getattr__(self,name):return getattr(self.stream,name)
  def read(self,size=-1):
   assert 0<=size<=expected+1,'corrupt artifact read exceeded declared bound'
   return self.stream.read(size)
  def readinto(self,buffer):
   assert len(buffer)<=expected+1,'corrupt artifact read exceeded declared bound'
   return self.stream.readinto(buffer)
 def checked_open(path,*args,**kwargs):
  stream=original_open(path,*args,**kwargs)
  return BoundedRead(stream) if path==target and args==('rb',) else stream
 monkeypatch.setattr(Path,'open',checked_open)
 with pytest.raises(DataError,match='PUBLICATION_CORRUPT'):publish_snapshot(storage,task,raw,maximum_bytes=32768)


def test_failure_after_atomic_file_publish_has_no_success_receipt(owned,monkeypatch):
 storage=manager(owned);task=str(uuid4());raw=encoded(batch());original_open=storage.open_artifact
 def interrupted_open(*args):
  writer=original_open(*args);real_publish=writer.publish
  def interrupted_publish():
   real_publish()
   raise RuntimeError('synthetic interruption after durable publication')
  monkeypatch.setattr(writer,'publish',interrupted_publish);return writer
 monkeypatch.setattr(storage,'open_artifact',interrupted_open)
 with pytest.raises(RuntimeError,match='synthetic interruption'):publish_snapshot(storage,task,raw,maximum_bytes=32768)
 path=next((storage.root/f'artifacts/runs/{task}/data').glob('input-*.json'));before=path.read_bytes()
 monkeypatch.setattr(storage,'open_artifact',original_open)
 with pytest.raises(DataError,match='PUBLICATION_INCOMPLETE'):publish_snapshot(storage,task,raw,maximum_bytes=32768)
 assert path.read_bytes()==before and json.loads(before)['original_utf8'].encode()==raw
