"""In-process RPC simulation over native stores; full native routing is separate."""
from contextlib import contextmanager
from types import SimpleNamespace
import base64,hashlib,json
import pytest
from test_paper_read_owner import owner,command,prepare,approve,start
from test_execution_health import pair
from compertum.runtime.errors import RuntimeRefused

@pytest.fixture
def publication(owner,monkeypatch):
 import compertum.runtime.paper_read_publication as module
 o=owner
 @contextmanager
 def remote_scope(remote):yield
 monkeypatch.setattr(module,'_remote_scope',remote_scope)
 remote=SimpleNamespace(descriptor=SimpleNamespace(registration=SimpleNamespace(project_id=o.a.lease.project_id,identity=SimpleNamespace(role='execution'))))
 def rpc(remote,action,payload):
  if action=='paper_read':return o.a.handle(payload)
  assert action=='paper_read_transfer';return o.a.transfer(payload)
 monkeypatch.setattr(module,'call_owner',rpc)
 return o,module.PaperReadPublication(o.manager,remote),module

def launch(publication):
 from uuid import uuid4
 o,pub,module=publication
 p=pub.handle('a'*64,dict(operation='prepare',packet_id=str(uuid4()),account_alias='fixture'))
 pub.handle('a'*64,dict(operation='authorize',packet_id=p['packet_id'],plan_sha256=p['plan_sha256']))
 pub.handle('a'*64,dict(operation='start',packet_id=p['packet_id'],plan_sha256=p['plan_sha256']))
 for _ in range(20):o.a.tick()
 return p

def test_opaque_publication_ack_closes_owner_transfer(publication):
 o,pub,module=publication;p=launch(publication)
 for _ in range(10):pub.tick()
 s=pub.handle('a'*64,dict(operation='status',packet_id=p['packet_id']))
 assert s['state']=='PUBLISHED' and s['publication']['state']=='PUBLISHED'
 manifest=s['publication']['manifest'];raw=(o.manager.root/manifest['path']).read_bytes()
 assert hashlib.sha256(raw).hexdigest()==manifest['sha256'] and o.a._cipher is None
 o.a.require_checkpoint();assert len(o.calls)==6
 assert pub.handle('a'*64,dict(operation='start',packet_id=p['packet_id'],plan_sha256=p['plan_sha256']))['consumed']
 assert len(o.calls)==6

@pytest.mark.parametrize('fault',['offset','total_bytes','sha256','project_id','task_id','packet_id','account_alias','data','truncated','oversize'])
def test_wrong_or_incomplete_chunk_is_never_published(publication,monkeypatch,fault):
 o,pub,module=publication;p=launch(publication);original=module.call_owner
 def corrupt(remote,action,payload):
  r=original(remote,action,payload)
  if action=='paper_read_transfer':
   r=dict(r)
   if fault=='data':r['data']='not base64@'
   elif fault=='truncated':r['data']=base64.b64encode(base64.b64decode(r['data'])[:-1]).decode()
   elif fault=='oversize':r['data']=base64.b64encode(b'x'*32769).decode()
   elif fault=='offset':r[fault]=True
   elif fault=='total_bytes':r[fault]+=1
   else:r[fault]='wrong'
  return r
 monkeypatch.setattr(module,'call_owner',corrupt)
 for _ in range(10):pub.tick()
 s=pub.handle('a'*64,dict(operation='status',packet_id=p['packet_id']))
 assert s['publication']['state']=='FAILED'
 assert not list(o.manager.root.glob('artifacts/runs/*/paper-read-*.bin'))
 assert o.a._cipher is not None


def test_public_control_cannot_supply_private_routing(publication):
 o,pub,module=publication
 from uuid import uuid4
 with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):pub.handle('a'*64,dict(operation='prepare',packet_id=str(uuid4()),account_alias='fixture',reservation_id=str(uuid4())))

def test_interrupted_transfer_is_terminal_after_coordinator_restart(publication):
 o,pub,module=publication;p=launch(publication);pub.tick()
 assert pub._route(p['packet_id'])['publication']['state']=='TRANSFERRING'
 restarted=module.PaperReadPublication(o.manager,pub.remote);restarted.tick()
 s=restarted.handle('a'*64,dict(operation='status',packet_id=p['packet_id']))
 assert s['publication']['state']=='FAILED' and s['publication']['reason']=='READ_COORDINATOR_RESTARTED'
 assert len(o.calls)==6
