"""Real storage/loopback evidence; coordinator RPC is an in-process test adapter."""
from contextlib import nullcontext
import importlib,time
from types import SimpleNamespace
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair
from test_paper_read_owner import owner
from test_paper_market_owner_native import native_market
from test_paper_market_collection import pages


@pytest.fixture
def publication(native_market,monkeypatch):
 o=native_market;module=importlib.import_module('compertum.runtime.paper_market_publication')
 remote=SimpleNamespace(descriptor=SimpleNamespace(registration=SimpleNamespace(project_id=o.e.lease.project_id,identity=SimpleNamespace(role='execution'))))
 monkeypatch.setattr(module,'_remote_scope',lambda remote:nullcontext())
 o.rpc=[]
 def call(remote,action,payload):
  o.rpc.append((action,payload['command']['operation'] if action=='paper_market_read' else payload['operation']))
  if action=='paper_market_read':return o.a.market_handle(payload)
  assert action=='paper_market_transfer';return o.a.market_transfer(payload)
 monkeypatch.setattr(module,'call_owner',call)
 o.pub_module=module;o.remote=remote;o.pub=module.PaperMarketPublication(o.manager,remote);o.call=call
 return o


def command(o,operation,*,subject='a'*64,**fields):return o.pub.handle(subject,dict(operation=operation,**fields))
def prepare(o,job=None):return command(o,'prepare',job_id=job or str(uuid4()),account_alias='fixture',mode='HISTORY',symbol='MSFT',history_job_id=None)
def start(o,p):
 command(o,'authorize',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
 return command(o,'start',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
def until(o,p,phase):
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  if o.pub.entries[p['job_id']]['phase']==phase:return
  o.a.tick();o.pub.tick();time.sleep(.002)
 raise AssertionError('publication phase not reached: '+phase)


@pytest.fixture
def collecting(publication):
 o=publication
 with pages([canonical(dict(bars={'MSFT':[]},next_page_token=None))]) as (port,seen):
  o.market_port=port;p=prepare(o);start(o,p)
  yield o,p,seen


def test_publication_allocates_genuine_ids_transfers_once_and_retains_exact_manifest(collecting):
 o,p,seen=collecting;until(o,p,'DONE');s=command(o,'status',job_id=p['job_id'])
 assert s['state']==s['publication']['state']=='PUBLISHED' and s['manifest']==s['publication']['manifest']
 assert len(seen)==1 and o.a._market._cipher is None
 path=o.manager.root/s['manifest']['path'];assert path.is_file()
 before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]
 assert command(o,'start',job_id=p['job_id'],grant_sha256=p['grant_sha256'])['state']=='PUBLISHED'
 for _ in range(3):o.pub.tick()
 assert len(seen)==1 and o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]==before


@pytest.mark.parametrize('change',['subject','url','manifest','clock','priority','mode_list'])
def test_public_scope_refuses_substitution_before_rpc_or_storage(publication,change):
 o=publication;p=prepare(o);before=len(o.rpc);rows=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()
 if change=='subject':
  with pytest.raises(RuntimeRefused):command(o,'status',subject='b'*64,job_id=p['job_id'])
 else:
  c=dict(operation='prepare',job_id=str(uuid4()),account_alias='fixture',mode='HISTORY',symbol='MSFT',history_job_id=None)
  if change=='mode_list':c['mode']=[]
  else:c[change]={} if change=='manifest' else 0 if change in {'clock','priority'} else 'https://example.invalid'
  with pytest.raises(RuntimeRefused):o.pub.handle('a'*64,c)
 assert len(o.rpc)==before and o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()==rows


@pytest.mark.parametrize('phase',['PUBLISH','ACK','DONE'])
def test_coordinator_recreation_never_recollects_or_allocates_another_artifact(collecting,phase):
 o,p,seen=collecting;until(o,p,phase);before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]
 o.rpc.clear();o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
 for _ in range(4):o.pub.tick()
 s=command(o,'status',job_id=p['job_id'])
 assert len(seen)==1 and o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]==before
 assert not any(op in {'prepare','authorize','start','chunk'} for _,op in o.rpc)
 assert s['publication']['state']==('FAILED' if phase=='PUBLISH' else 'PUBLISHED')


def test_lost_ack_reply_preserves_manifest_and_recovers_only_ack(collecting,monkeypatch):
 o,p,seen=collecting;until(o,p,'ACK');before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]
 def lost(remote,action,payload):
  result=o.call(remote,action,payload)
  if action=='paper_market_transfer' and payload['operation']=='ack':raise RuntimeRefused('INJECTED_ACK_REPLY_LOSS')
  return result
 monkeypatch.setattr(o.pub_module,'call_owner',lost);o.pub.tick()
 route=o.pub._route(p['job_id']);assert route['publication']['state']=='FAILED' and route['publication']['manifest']
 manifest=route['publication']['manifest'];monkeypatch.setattr(o.pub_module,'call_owner',o.call)
 o.rpc.clear();o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
 for _ in range(4):o.pub.tick()
 assert o.pub._route(p['job_id'])['publication']==dict(state='PUBLISHED',reason=None,manifest=manifest)
 assert not any(op in {'prepare','authorize','start','chunk'} for _,op in o.rpc) and len(seen)==1
 assert o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]==before


def test_publish_before_route_save_crash_recovers_unique_committed_ledger(collecting,monkeypatch):
 o,p,seen=collecting;until(o,p,'PUBLISH');original=o.pub._save
 def fail(route,**kw):
  if route['publication']['manifest'] is not None:raise RuntimeRefused('INJECTED_ROUTE_COMMIT')
  return original(route,**kw)
 monkeypatch.setattr(o.pub,'_save',fail)
 with pytest.raises(RuntimeRefused,match='INJECTED_ROUTE_COMMIT'):o.pub.tick()
 assert o.pub._route(p['job_id'])['publication']['manifest'] is None
 rows=o.manager.store.conn.execute("SELECT manifest FROM reservations WHERE task=? AND status='PUBLISHED'",(p['task_id'],)).fetchall();assert len(rows)==1
 before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]
 o.rpc.clear();o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
 for _ in range(4):o.pub.tick()
 assert o.pub._route(p['job_id'])['publication']['state']=='PUBLISHED' and len(seen)==1
 assert o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]==before
 assert not any(op in {'prepare','authorize','start','chunk'} for _,op in o.rpc)


def test_both_owner_objects_recreated_ack_without_retained_cipher(collecting):
 o,p,seen=collecting;until(o,p,'ACK');manifest=o.pub._route(p['job_id'])['publication']['manifest']
 o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e);assert o.a._market._cipher is None
 o.rpc.clear();o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
 for _ in range(4):o.pub.tick()
 s=command(o,'status',job_id=p['job_id']);assert s['state']=='PUBLISHED' and s['manifest']==manifest and len(seen)==1
 assert not any(op in {'prepare','authorize','start','chunk'} for _,op in o.rpc)


@pytest.mark.parametrize('fault',['duplicate','status','category','parent'])
def test_invalid_recovery_ledger_stays_failed_without_ack(collecting,fault):
 o,p,seen=collecting;until(o,p,'ACK');route=o.pub._route(p['job_id']);path=route['publication']['manifest']['path'];db=o.manager.store.conn
 with db:
  if fault=='duplicate':db.execute('INSERT INTO reservations SELECT ?,task,category,maximum,written,status,path,manifest FROM reservations WHERE path=?',(str(uuid4()),path))
  elif fault=='parent':db.execute("UPDATE reservations SET status='ABANDONED' WHERE id=?",(route['reservation_id'],))
  else:db.execute('UPDATE reservations SET '+fault+'=? WHERE path=?',('ABANDONED' if fault=='status' else 'data',path))
 o.rpc.clear();o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
 for _ in range(4):o.pub.tick()
 assert o.pub._route(p['job_id'])['publication']['state']=='FAILED'
 assert not any(action=='paper_market_transfer' for action,_ in o.rpc) and len(seen)==1


@pytest.mark.parametrize('fault',['job','grant','mode','offset','total','extra','base64','length','body'])
def test_corrupt_chunk_refuses_publication_without_another_request(collecting,monkeypatch,fault):
 import base64
 o,p,seen=collecting;until(o,p,'COLLECT')
 def corrupt(remote,action,payload):
  reply=o.call(remote,action,payload)
  if action=='paper_market_transfer' and payload['operation']=='chunk':
   if fault=='job':reply['job_id']=str(uuid4())
   elif fault=='grant':reply['grant_sha256']='f'*64
   elif fault=='mode':reply['mode']='CURRENT_ACTIONS'
   elif fault=='offset':reply['offset']=True
   elif fault=='total':reply['total_bytes']+=1
   elif fault=='extra':reply['raw_body']='not allowed'
   elif fault=='base64':reply['data']='?'
   else:
    raw=base64.b64decode(reply['data']);raw=raw[:-1] if fault=='length' else bytes([raw[0]^255])+raw[1:]
    reply['data']=base64.b64encode(raw).decode()
  return reply
 monkeypatch.setattr(o.pub_module,'call_owner',corrupt);o.pub.tick()
 route=o.pub._route(p['job_id']);assert route['publication']['state']=='FAILED' and route['publication']['manifest'] is None
 assert o.manager.store.conn.execute("SELECT 1 FROM reservations WHERE task=? AND status='PUBLISHED'",(p['task_id'],)).fetchone() is None
 for _ in range(3):o.pub.tick()
 assert len(seen)==1 and o.a._market._cipher is not None


def test_ignored_recovered_manifest_write_prevents_ack(collecting):
 o,p,seen=collecting;until(o,p,'ACK');db=o.manager.store.conn
 before=db.execute('SELECT count(*) FROM reservations').fetchone()[0]
 o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote);o.rpc.clear()
 db.execute("CREATE TRIGGER deny_recovery BEFORE UPDATE ON state WHEN NEW.key LIKE 'paper_market_route:%' BEGIN SELECT RAISE(IGNORE); END")
 try:
  with pytest.raises(RuntimeRefused,match='MARKET_ROUTE_WRITE_UNVERIFIED'):o.pub.tick()
  assert not o.rpc and o.a._market._cipher is not None
 finally:db.execute('DROP TRIGGER deny_recovery');db.commit()
 o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
 for _ in range(4):o.pub.tick()
 assert o.pub._route(p['job_id'])['publication']['state']=='PUBLISHED' and len(seen)==1
 assert db.execute('SELECT count(*) FROM reservations').fetchone()[0]==before


@pytest.mark.parametrize('fault',['bytes','partial','open_ledger'])
def test_recovery_rejects_tampered_or_partial_artifact_before_ack(collecting,fault):
 o,p,seen=collecting;until(o,p,'ACK');route=o.pub._route(p['job_id']);manifest=route['publication']['manifest'];path=o.manager.root/manifest['path']
 if fault=='bytes':
  raw=path.read_bytes();path.write_bytes(bytes([raw[0]^255])+raw[1:])
 elif fault=='partial':path.with_name(path.name+'.partial-fixture').write_bytes(b'partial')
 else:
  with o.manager.store.conn:o.manager.store.conn.execute("UPDATE reservations SET status='OPEN' WHERE path=?",(manifest['path'],))
 o.rpc.clear();o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
 for _ in range(4):o.pub.tick()
 assert o.pub._route(p['job_id'])['publication']['state']=='FAILED' and not o.rpc and len(seen)==1


def test_oversize_evidence_is_refused_before_chunk_or_child_reservation(collecting,monkeypatch):
 o,p,seen=collecting
 def oversized(remote,action,payload):
  reply=o.call(remote,action,payload)
  if action=='paper_market_read' and payload['command']['operation']=='status':reply['evidence']=dict(size_bytes=3*1024**2+1,sha256='e'*64)
  return reply
 monkeypatch.setattr(o.pub_module,'call_owner',oversized)
 before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]
 o.pub.tick();assert o.pub._route(p['job_id'])['publication']['state']=='FAILED'
 assert not any(action=='paper_market_transfer' for action,_ in o.rpc)
 assert o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]==before


@pytest.mark.parametrize('failure',['before_owner','lost_reply'])
def test_explicit_prepare_retry_keeps_same_route_and_publishes_once(publication,monkeypatch,failure):
 o=publication;job=str(uuid4());failed=[]
 def transient(remote,action,payload):
  if action=='paper_market_read' and payload['command']['operation']=='prepare' and not failed:
   failed.append(True)
   if failure=='lost_reply':o.call(remote,action,payload)
   raise RuntimeRefused('INJECTED_PREPARE_REPLY')
  return o.call(remote,action,payload)
 monkeypatch.setattr(o.pub_module,'call_owner',transient)
 with pytest.raises(RuntimeRefused,match='INJECTED_PREPARE_REPLY'):prepare(o,job)
 before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]
 p=prepare(o,job);assert o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]==before
 with pages([canonical(dict(bars={'MSFT':[]},next_page_token=None))]) as (port,seen):
  o.market_port=port;start(o,p);until(o,p,'DONE')
  assert len(seen)==1 and o.pub._route(job)['publication']['state']=='PUBLISHED'
 assert o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]==before+1


def test_file_rename_without_publication_commit_never_recovers_ack(collecting,monkeypatch):
 from compertum.storage import BoundedWriter
 o,p,seen=collecting;until(o,p,'PUBLISH')
 def fail_after_rename(writer):
  writer.stream.close();writer.path.rename(writer.destination);raise RuntimeRefused('INJECTED_PRE_LEDGER')
 monkeypatch.setattr(BoundedWriter,'publish',fail_after_rename);o.pub.tick()
 route=o.pub._route(p['job_id']);assert route['publication']['state']=='FAILED' and route['publication']['manifest'] is None
 final=o.manager.root/f'artifacts/runs/{p["task_id"]}/market-collection-{p["job_id"]}.bin';assert final.is_file()
 assert o.manager.store.conn.execute("SELECT 1 FROM reservations WHERE task=? AND status='PUBLISHED'",(p['task_id'],)).fetchone() is None
 before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0];raw=final.read_bytes()
 o.rpc.clear();o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
 for _ in range(4):o.pub.tick()
 assert o.pub._route(p['job_id'])['publication']['state']=='FAILED' and not o.rpc and len(seen)==1
 assert final.read_bytes()==raw and o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]==before
