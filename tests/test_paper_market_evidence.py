"""Private encrypted market evidence; native local fixtures and invented credentials."""
from pathlib import Path
from uuid import uuid4
import hashlib,json,pickle,os
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_market_evidence import protect_market_evidence,publish_market_evidence,open_market_evidence
import compertum.runtime.paper_market_evidence as module
from test_persistence import owned
from test_storage import manager
import test_paper_market_collection as f

@pytest.fixture
def evidence(owned):
 project,leases=owned;m=manager(owned);e=leases['execution']
 credential=seal_paper_credentials(e,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))
 with f.pages([f.body('HISTORY','next'),f.body('HISTORY')]) as (port,seen):
  c=f.collection(e,credential,port);f.run(c)
 s=protect_market_evidence(e,c.private_snapshot(),task_id=str(uuid4()))
 return project,leases,m,c,s

def publish(evidence):
 _,_,m,_,s=evidence;g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext));return g,publish_market_evidence(m,g,s)

def opened(evidence,receipt):
 return open_market_evidence(evidence[1]['execution'],'paper-primary',evidence[4].collection_id,receipt)

def test_roundtrip_keeps_exact_originals_and_historical_purpose(evidence):
 project,leases,m,c,s=evidence;g,r=publish(evidence);raw=(project.root_path/r['path']).read_bytes()
 assert raw==s.ciphertext and all(k.encode() not in raw for k in (f.KEY,f.SECRET))
 assert all(k not in json.dumps(r) for k in (f.KEY,f.SECRET))
 with opened(evidence,r) as p:
  v=p.snapshot();assert v['collection']==c.private_snapshot().to_payload()
  assert v['use']=='HISTORICAL_ONLY' and v['purpose']=='OPERATIONAL_ONLY' and v['freshness']=='NOT_RESTORED'
  assert v['financial_accepted'] is v['transport_authorized'] is v['research_eligible'] is False
  with pytest.raises(RuntimeRefused):pickle.dumps(p)
  buffer=p._buffer;assert any(buffer)
 assert not any(buffer)
 with pytest.raises(RuntimeRefused):p.snapshot()
 assert publish_market_evidence(m,g,s)==r
 again=protect_market_evidence(leases['execution'],c.private_snapshot(),task_id=s.task_id)
 assert again.ciphertext!=s.ciphertext
 with pytest.raises(RuntimeRefused):publish_market_evidence(m,g,again)

@pytest.mark.parametrize('role',['coordinator','evaluation'])
def test_wrong_role_refused(evidence,role):
 _,leases,_,c,s=evidence;_,r=publish(evidence)
 with pytest.raises(RuntimeRefused):protect_market_evidence(leases[role],c.private_snapshot(),task_id=s.task_id)
 with pytest.raises(RuntimeRefused):
  with open_market_evidence(leases[role],'paper-primary',s.collection_id,r):pass

@pytest.mark.parametrize('fault',['alias','collection','task','artifact','path','hash','size'])
def test_context_and_manifest_changes_refused(evidence,fault):
 _,r=publish(evidence);alias='paper-primary';cid=evidence[4].collection_id
 if fault=='alias':alias='other'
 elif fault=='collection':cid=str(uuid4())
 elif fault=='task':r['task_id']=str(uuid4())
 elif fault=='artifact':r['artifact_id']=str(uuid4())
 elif fault=='path':r['path']='state/credentials.bin'
 elif fault=='hash':r['sha256']='f'*64
 else:r['size_bytes']+=1
 with pytest.raises(RuntimeRefused):
  with open_market_evidence(evidence[1]['execution'],alias,cid,r):pass

@pytest.mark.parametrize('fault',['missing','status','written','category','task','duplicate'])
def test_unique_exact_publication_ledger_required(evidence,fault):
 _,_,m,_,s=evidence;g,r=publish(evidence);db=m.store.conn
 with db:
  if fault=='missing':db.execute('DELETE FROM reservations WHERE id=?',(g.grant_id,))
  elif fault=='duplicate':db.execute('INSERT INTO reservations SELECT ?,task,category,maximum,written,status,path,manifest FROM reservations WHERE id=?',(str(uuid4()),g.grant_id))
  else:db.execute('UPDATE reservations SET '+fault+'=? WHERE id=?',({'status':'ABANDONED','written':0,'category':'data','task':str(uuid4())}[fault],g.grant_id))
 with pytest.raises(RuntimeRefused):
  with opened(evidence,r):pass

@pytest.mark.parametrize('fault',['truncated','corrupt','trailing','oversize'])
def test_damaged_ciphertext_refused(evidence,fault):
 project,_,m,_,_=evidence;g,r=publish(evidence);path=project.root_path/r['path'];raw=path.read_bytes()
 raw={'truncated':raw[:40],'corrupt':raw[:90]+bytes([raw[90]^255])+raw[91:],'trailing':raw+b'extra','oversize':b'x'*(3*1024**2+1)}[fault]
 path.write_bytes(raw);r['sha256']=hashlib.sha256(raw).hexdigest();r['size_bytes']=len(raw)
 with m.store.conn:m.store.conn.execute('UPDATE reservations SET written=?,manifest=? WHERE id=?',(len(raw),canonical(r).decode(),g.grant_id))
 with pytest.raises(RuntimeRefused):
  with opened(evidence,r):pass

@pytest.mark.parametrize('fault',['purpose','project','aggregate','raw_hash','request_hash','cursor','received','dispatch','validated','state','extra','attempts'])
def test_semantic_tampering_refused(evidence,fault):
 s=evidence[4];entropy=module._context(s.project_id,s.account_alias,s.task_id,s.collection_id)
 plain=module._crypt_evidence(bytearray(s.ciphertext),entropy,decrypt=True)
 try:
  frames=module._frames(plain,entropy);v=json.loads(frames[1]);r=v['records'][-1]
  if fault=='purpose':v['purpose']='RESEARCH'
  elif fault=='project':v['plan']['project_id']='f'*64
  elif fault=='aggregate':v['aggregate']['financial_accepted']=True
  elif fault=='raw_hash':r['diagnostic']['raw_sha256']='f'*64
  elif fault=='request_hash':r['diagnostic']['request_sha256']='f'*64
  elif fault=='cursor':r['request']['parameters']['page_token']='wrong'
  elif fault=='received':r['diagnostic']['received_at']='2026-10-09T13:20:01Z'
  elif fault=='dispatch':r['dispatched_at']='2026-10-09T13:25:00Z'
  elif fault=='validated':r['validated_at']=None
  elif fault=='state':v['state']='READY'
  elif fault=='extra':v['extra']='unrecognized'
  else:v['attempts']=0
  frames[1]=canonical(v);meta=json.loads(frames[0]);meta['snapshot_sha256']=hashlib.sha256(frames[1]).hexdigest();frames[0]=canonical(meta)
  with pytest.raises((RuntimeRefused,ValueError)):module._validate(frames,s.project_id,s.account_alias,s.task_id,s.collection_id)
 finally:module._wipe(plain)

@pytest.mark.parametrize('phase',['write','rename','index'])
def test_interrupted_publication_and_retry(evidence,monkeypatch,phase):
 from compertum.storage import BoundedWriter
 _,_,m,_,s=evidence;g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext));ow=BoundedWriter.write;op=BoundedWriter.publish
 def write(w,b):ow(w,b);raise RuntimeRefused('INJECTED_WRITE')
 def pub(w):
  if phase=='index':op(w)
  else:w.stream.close();w.path.rename(w.destination)
  raise RuntimeRefused('INJECTED_PUBLICATION')
 monkeypatch.setattr(BoundedWriter,'write' if phase=='write' else 'publish',write if phase=='write' else pub)
 with pytest.raises(RuntimeRefused):publish_market_evidence(m,g,s)
 monkeypatch.setattr(BoundedWriter,'write',ow);monkeypatch.setattr(BoundedWriter,'publish',op)
 if phase=='index':
  r=publish_market_evidence(m,g,s)
  with opened(evidence,r) as p:assert p.snapshot()['use']=='HISTORICAL_ONLY'
 else:
  with pytest.raises(RuntimeRefused):publish_market_evidence(m,g,s)
  if phase=='rename':
   r=dict(artifact_id=str(uuid4()),task_id=s.task_id,path=module._path(s.task_id,s.collection_id),size_bytes=len(s.ciphertext),sha256=hashlib.sha256(s.ciphertext).hexdigest())
   with pytest.raises(RuntimeRefused):
    with opened(evidence,r):pass

def test_owner_release_wipes_and_revokes(evidence):
 _,r=publish(evidence)
 with opened(evidence,r) as p:
  buffer=p._buffer;release_owner(evidence[1]['execution']);assert not any(buffer)
  with pytest.raises(RuntimeRefused):p.snapshot()

def test_consumer_error_preserved_and_buffer_wiped(evidence):
 _,r=publish(evidence);error=ValueError('fixture consumer')
 with pytest.raises(ValueError) as caught:
  with opened(evidence,r) as p:buffer=p._buffer;raise error
 assert caught.value is error and not any(buffer)

@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
@pytest.mark.parametrize('case',['complete','cancel_zero','dispatch_zero','null_final','late','http','bad_page','repeated','cap','secret_second'])
def test_real_collection_shapes_roundtrip_without_upgrade(evidence,monkeypatch,mode,case):
 import compertum.runtime.paper_market_collection as producer
 _,leases,m,old,_=evidence;old.close();e=leases['execution'];key='HISTORY_ROWS_MISSING' if case=='null_final' else f.KEY
 credential=seal_paper_credentials(e,'paper-primary',bytearray(key.encode()),bytearray(f.SECRET.encode()));clock=f.Clock()
 if case=='null_final' and mode=='CURRENT_ACTIONS':
  # This generated diagnostic literal is also a permitted invented API key.
  key='HALT_STATUS_UNVERIFIED';credential=seal_paper_credentials(e,'paper-primary',bytearray(key.encode()),bytearray(f.SECRET.encode()))
 bodies=[f.body(mode)]
 if case=='repeated':bodies=[f.body(mode,'x'),f.body(mode,'x')]
 elif case=='cap':bodies=[f.body(mode,str(i)) for i in range(8)]
 elif case=='bad_page':bodies=[b'{"bars":[],"corporate_actions":[],"next_page_token":null}']
 elif case=='http':bodies=[b'{"message":"refused"}']
 elif case=='secret_second':bodies=[f.body(mode,'x'),canonical(dict(message=f.KEY))]
 if case=='late':
  clock.at='2026-10-09T13:24:59Z';name='qualify_market_inputs' if mode=='HISTORY' else 'qualify_action_inputs';original=getattr(producer,name)
  def late(*a,**kw):
   result=original(*a,**kw);clock.at='2026-10-09T13:25:00.000000001Z';return result
  monkeypatch.setattr(producer,name,late)
 with f.pages(bodies,[403] if case=='http' else None) as (port,seen):
  c=f.collection(e,credential,port,mode,clock=clock)
  if case=='cancel_zero':c.cancel()
  elif case=='dispatch_zero':
   clock.at='2026-10-09T13:25:00Z'
   with pytest.raises(RuntimeRefused):c.dispatch()
  else:f.run(c)
 snapshot=c.private_snapshot().to_payload();s=protect_market_evidence(e,c.private_snapshot(),task_id=str(uuid4()));g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext));r=publish_market_evidence(m,g,s)
 with open_market_evidence(e,'paper-primary',s.collection_id,r) as p:
  result=p.snapshot();assert result['collection']==snapshot and result['freshness']=='NOT_RESTORED'
 if case=='complete':assert snapshot['state']=='PAGINATION_COMPLETE'
 else:assert snapshot['state']=='INCOMPLETE'
 if case=='null_final':assert snapshot['aggregate'] is None and snapshot['records'][-1]['validated_at'] is None
 if case.endswith('zero'):assert snapshot['records']==[] and len(seen)==0


def test_framing_maximum_and_authenticated_cipher_length():
 entropy=module._context('a'*64,'paper-primary',str(uuid4()),str(uuid4()));frames=[b'x'*8192,b'y'*(2*1024**2)]
 plain=module._pack(frames,entropy);encrypted=bytearray();restored=bytearray()
 try:
  assert 2*1024**2<len(plain)<=2*1024**2+16384 and module._frames(plain,entropy)==frames
  encrypted=module._crypt_evidence(plain,entropy,decrypt=False);size=len(encrypted);module._wipe(encrypted)
  plain[72:76]=size.to_bytes(4,'big');h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);plain[40:72]=h.digest()
  encrypted=module._crypt_evidence(plain,entropy,decrypt=False);assert len(encrypted)==size
  restored=module._crypt_evidence(encrypted,entropy,decrypt=True);assert module._frames(restored,entropy,cipher_size=size)==frames
  with pytest.raises(RuntimeRefused):module._frames(restored,entropy,cipher_size=size+1)
  with pytest.raises(RuntimeRefused):module._pack([frames[0],frames[1]+b'x'],entropy)
  with pytest.raises(RuntimeRefused):module._crypt_evidence(bytearray(module._PLAIN_MAX+1),entropy,decrypt=False)
  with pytest.raises(RuntimeRefused):module._crypt_evidence(bytearray(module._CIPHER_MAX+1),entropy,decrypt=True)
 finally:module._wipe(plain);module._wipe(encrypted);module._wipe(restored)

@pytest.mark.parametrize('fault',['magic','digest','length','trailing','missing'])
def test_exact_frame_validation(evidence,fault):
 s=evidence[4];entropy=module._context(s.project_id,s.account_alias,s.task_id,s.collection_id);plain=module._crypt_evidence(bytearray(s.ciphertext),entropy,decrypt=True)
 try:
  if fault=='magic':plain[0]^=255
  elif fault=='digest':plain[40]^=255
  elif fault=='length':plain[76:80]=(8193).to_bytes(4,'big')
  elif fault=='trailing':plain.extend(b'extra')
  else:plain.pop()
  if fault!='digest':
   h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);plain[40:72]=h.digest()
  with pytest.raises(RuntimeRefused):module._frames(plain,entropy)
 finally:module._wipe(plain)


def test_grant_and_encryption_purposes_are_exact(evidence):
 _,_,m,c,s=evidence
 for task,category,size in ((str(uuid4()),'records',len(s.ciphertext)),(s.task_id,'data',len(s.ciphertext)),(s.task_id,'records',len(s.ciphertext)+1)):
  g=m.reserve_bytes(task,category,size)
  with pytest.raises(RuntimeRefused):publish_market_evidence(m,g,s)
 from compertum.runtime import paper_read_evidence as account
 for entropy in (module._context('f'*64,s.account_alias,s.task_id,s.collection_id),account._context(s.project_id,s.account_alias,s.task_id,s.collection_id)):
  with pytest.raises(RuntimeRefused):module._crypt_evidence(bytearray(s.ciphertext),entropy,decrypt=True)
 assert not (m.root/'artifacts').exists()


def test_added_metadata_is_secrecy_checked(evidence):
 _,leases,_,old,_=evidence;old.close();key=str(uuid4());e=leases['execution']
 credential=seal_paper_credentials(e,'paper-primary',bytearray(key.encode()),bytearray(f.SECRET.encode()))
 with f.pages([f.body('HISTORY')]) as (port,_):c=f.collection(e,credential,port);f.run(c)
 with pytest.raises(RuntimeRefused,match='SECRET_REFLECTION'):protect_market_evidence(e,c.private_snapshot(),task_id=key)


def test_seal_holds_lease_lock_during_concurrent_close(evidence,monkeypatch):
 import threading
 _,leases,_,c,s=evidence;original=module._crypt_evidence;attempt=threading.Event();done=threading.Event();threads=[]
 def close():attempt.set();c.close();done.set()
 def crypt(*a,**kw):
  if not threads:
   thread=threading.Thread(target=close);threads.append(thread);thread.start();assert attempt.wait(2) and not done.is_set()
  return original(*a,**kw)
 monkeypatch.setattr(module,'_crypt_evidence',crypt)
 sealed=protect_market_evidence(leases['execution'],c.private_snapshot(),task_id=s.task_id)
 for thread in threads:thread.join(2)
 assert done.is_set() and sealed.ciphertext
 with pytest.raises(RuntimeRefused):protect_market_evidence(leases['execution'],c.private_snapshot(),task_id=s.task_id)


def test_native_child_exit_reopens_without_credentials(tmp_path):
 import subprocess
 from compertum.runtime.identity import resolve_project
 from compertum.runtime.owners import acquire_owner
 from compertum.runtime.paper_credential_slot import SLOT_PATH
 from test_fixture_processes import fixture_module
 code="""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('tests').resolve()))
from uuid import uuid4
import test_paper_market_collection as f
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_market_evidence import protect_market_evidence,publish_market_evidence
from compertum.config import load_config
from compertum.storage import StorageManager
root=Path(sys.argv[1]);project=resolve_project(root);c=acquire_owner(project,'coordinator');e=acquire_owner(project,'execution')
try:
 config=root/'config.toml';config.write_bytes(Path('config/default.toml').read_bytes());m=StorageManager(c,load_config(config,root))
 credential=seal_paper_credentials(e,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))
 with f.pages([f.body('HISTORY')]) as (port,_):collection=f.collection(e,credential,port);f.run(collection)
 sealed=protect_market_evidence(e,collection.private_snapshot(),task_id=str(uuid4()));g=m.reserve_bytes(sealed.task_id,'records',len(sealed.ciphertext));r=publish_market_evidence(m,g,sealed)
 print(json.dumps(dict(collection_id=sealed.collection_id,manifest=r)))
finally:release_owner(e);release_owner(c)
"""
 child=fixture_module().python_process(['-B','-c',code,str(tmp_path)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:out,err=child.communicate(timeout=20)
 except subprocess.TimeoutExpired:child.kill();child.communicate();raise
 assert child.returncode==0,err
 result=json.loads(out);e=acquire_owner(resolve_project(tmp_path),'execution')
 try:
  assert e.generation==2 and not (tmp_path/SLOT_PATH).exists() and all(k not in out for k in (f.KEY,f.SECRET))
  with open_market_evidence(e,'paper-primary',result['collection_id'],result['manifest']) as p:
   v=p.snapshot();assert v['metadata']['execution_generation']==1 and len(v['collection']['records'])==1 and v['freshness']=='NOT_RESTORED'
 finally:release_owner(e)


def test_large_real_pages_preserve_every_original(evidence):
 _,leases,m,old,_=evidence;old.close();e=leases['execution']
 credential=seal_paper_credentials(e,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))
 bodies=[canonical(dict(bars={'AAPL':[]},next_page_token=str(i+1) if i<7 else None,unknown='x'*45000)) for i in range(8)]
 with f.pages(bodies) as (port,_):c=f.collection(e,credential,port);v=f.run(c)
 s=protect_market_evidence(e,c.private_snapshot(),task_id=str(uuid4()));g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext));r=publish_market_evidence(m,g,s)
 with open_market_evidence(e,'paper-primary',s.collection_id,r) as p:assert [x['body_utf8'].encode() for x in p.snapshot()['collection']['records']]==bodies
 assert len(c.private_snapshot().content)>350000

@pytest.mark.parametrize('field',['ciphertext','task_id','collection_id','account_alias','project_id'])
def test_changed_protected_wrapper_cannot_publish(evidence,field):
 _,_,m,_,s=evidence
 value={'ciphertext':b'plaintext fixture marker','task_id':str(uuid4()),'collection_id':str(uuid4()),'account_alias':'changed','project_id':'f'*64}[field]
 object.__setattr__(s,field,value);g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext))
 with pytest.raises(RuntimeRefused):publish_market_evidence(m,g,s)
 assert not (m.root/'artifacts').exists()


def test_private_open_admission_is_bounded_before_decrypt(evidence,monkeypatch):
 _,r=publish(evidence);original=module._crypt_evidence;calls=[]
 def crypt(*a,**kw):calls.append(kw['decrypt']);return original(*a,**kw)
 monkeypatch.setattr(module,'_crypt_evidence',crypt)
 with opened(evidence,r) as first:
  with pytest.raises(RuntimeRefused,match='MARKET_EVIDENCE_CAPACITY'):
   with opened(evidence,r):pass
  assert calls==[True]
  first.close();assert not any(first._buffer)
  with opened(evidence,r) as second:assert second.snapshot()['freshness']=='NOT_RESTORED'
 assert calls==[True,True]
 from compertum.runtime.owners import _LEASES
 assert not any(type(x) is module._OpenedMarketEvidence for x in _LEASES[evidence[1]['execution']].resources)


def test_publication_uses_the_verified_ciphertext_even_if_wrapper_changes(evidence,monkeypatch):
 project,_,m,_,s=evidence;original=s.ciphertext;open_artifact=m.open_artifact
 def opened_writer(*a,**kw):
  writer=open_artifact(*a,**kw);object.__setattr__(s,'ciphertext',b'x'*len(original));return writer
 monkeypatch.setattr(m,'open_artifact',opened_writer)
 g=m.reserve_bytes(s.task_id,'records',len(original));r=publish_market_evidence(m,g,s)
 assert (project.root_path/r['path']).read_bytes()==original
 with opened(evidence,r) as p:assert p.snapshot()['freshness']=='NOT_RESTORED'
