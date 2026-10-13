"""Account waiting with simulated replies, plus native child restart fence."""
import json,os,subprocess
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.service_budget import queue_for
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from test_execution_health import pair
from test_paper_read_owner import owner,prepare,approve,start,command
from test_winhttp_get import server,start as native_start,finish


@pytest.mark.parametrize('ending',['continue','cancel','deadline'])
def test_account_waiting_has_no_request_row_attempt_or_renewal(owner,ending):
 o=owner;q=queue_for(o.e.lease)
 with server(stall=True) as (port,arrived,seen):
  blocker=native_start(o.e.lease,port);assert arrived.wait(1)
  try:
   p=prepare(o);approve(o,p);start(o,p);o.a.tick()
   state=command(o,'status',packet_id=p['packet_id'])
   stored=json.loads(o.a.db.execute('SELECT body FROM paper_read_packets').fetchone()[0])
   assert state['attempts']==0 and not stored['requests'] and not o.calls and q.status()['queued']==1
   if ending=='cancel':command(o,'cancel',packet_id=p['packet_id'])
   elif ending=='deadline':
    o.a._packet._started_real_ns-=31*10**9;o.a.tick()
    assert command(o,'status',packet_id=p['packet_id'])['reason']=='PAPER_PACKET_DEADLINE'
   else:
    blocker.close();o.a.tick();assert len(o.calls)==1
   assert q.status()['queued']==0 and len(seen)==1
  finally:blocker.close()


def test_registered_reconciliation_overtakes_queued_collection(owner):
 o=owner;q=queue_for(o.e.lease)
 from compertum.runtime.paper_credentials import seal_paper_credentials
 import test_paper_market_collection as f
 protected=seal_paper_credentials(o.e.lease,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))
 with server(stall=True) as (port,arrived,seen),f.pages([f.body('HISTORY')]) as (data_port,data_seen):
  blocker=native_start(o.e.lease,port);assert arrived.wait(1)
  collection=f.collection(o.e.lease,protected,data_port)
  try:
   assert collection.dispatch()=='WAITING'
   p=prepare(o);approve(o,p);start(o,p);o.a.tick();assert q.status()['queued']==2
   blocker.close();assert collection.dispatch()=='WAITING' and not data_seen
   o.a.tick();assert len(o.calls)==1 and collection._attempts==0
   o.a.tick();collection.dispatch();f.finish(collection)
   assert len(data_seen)==1 and q.status()['data_used']==1
  finally:blocker.close();collection.close()


def test_new_native_owner_after_child_exit_gets_real_startup_fence(tmp_path):
 from test_fixture_processes import fixture_module
 code="""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path('tests').resolve()))
from test_winhttp_get import warm_budget,start,finish
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.service_budget import queue_for
lease=acquire_owner(resolve_project(Path(sys.argv[1])),'execution');q=warm_budget(lease)
try:
 for _ in range(100):finish(start(lease,int(sys.argv[2])))
 print(json.dumps(dict(generation=lease.generation,used=q.status()['paper_used'])))
finally:release_owner(lease)
"""
 with server() as (port,_,seen):
  child=fixture_module().python_process(['-B','-c',code,str(tmp_path),str(port)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:out,err=child.communicate(timeout=20)
  except subprocess.TimeoutExpired:child.kill();child.communicate();raise
  assert child.returncode==0,err
  assert json.loads(out)==dict(generation=1,used=100) and len(seen)==100
  lease=acquire_owner(resolve_project(tmp_path),'execution')
  try:
   q=queue_for(lease);assert lease.generation==2 and not q.status()['ready'] and not q.status()['fixture_only']
   with pytest.raises(RuntimeRefused,match='HTTP_ADMISSION_WAITING'):native_start(lease,port)
   assert len(seen)==100
  finally:release_owner(lease)
