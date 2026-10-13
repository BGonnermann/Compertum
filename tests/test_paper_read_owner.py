"""Native owner/store and DPAPI; reserve capacity and replies are explicitly simulated."""
import hashlib,json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_execution_health import pair,connect
from test_paper_read_preparation import KEY,SECRET
from test_paper_read_packet import body
from compertum.persistence import open_store
from compertum.storage import StorageManager,create_journal_reserve,reserve_runtime_paths
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_credential_slot import provision_paper_slot
from compertum.runtime.errors import RuntimeRefused

@pytest.fixture
def owner(pair,monkeypatch,tmp_path):
 import compertum.runtime.paper_read_owner as module
 e,w,c,stops=pair;connect(e,w)
 from test_winhttp_get import warm_budget
 budget=warm_budget(e.lease)
 project=resolve_project(tmp_path);coord=acquire_owner(project,'coordinator');db=open_store(coord,'coordinator')
 from test_storage import manager as create_manager
 manager=create_manager((project,{'coordinator':coord}));reserve_runtime_paths(manager)
 protected=seal_paper_credentials(e.lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
 provision_paper_slot(e.lease,protected)
 store=open_store(e.lease,'execution');reserve=create_journal_reserve(e.lease,65536)
 monkeypatch.setattr(module,'execution_durable',lambda *a:reserve.receipt())
 clock=SimpleNamespace(utc=0,mono=100.)
 clock.utc=__import__('datetime').datetime.fromisoformat('2023-11-24T14:30:00+00:00').timestamp()
 monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:clock.utc,monotonic=lambda:clock.mono))
 calls=[]
 class Get:
  native_closed=False;status_code=None
  def __init__(self,lease,request,protected,timeout,*,_permit=None):
   budget._commit(_permit,'PAPER','READ')
   assert store.conn.in_transaction is False
   state=json.loads(store.conn.execute('SELECT body FROM paper_read_packets').fetchone()[0]);assert state['consumed'] is True
   self.request=request;calls.append(self)
  def poll(self):
   self.status_code=200;self.native_closed=True
   return SimpleNamespace(status_code=200,body=json.dumps(body(self.request.to_payload()['operation'])).encode())
  def close(self):self.native_closed=True
 monkeypatch.setattr(module,'_start_get',Get)
 a=module.PaperReadOwner(store,reserve,e)
 task=str(uuid4());grant=manager.reserve_bytes(task,'records',3*1024**2)
 ctx=SimpleNamespace(a=a,e=e,w=w,c=c,clock=clock,calls=calls,manager=manager,task=task,grant=grant,protected=protected,module=module)
 try:yield ctx
 finally:a.close();release_owner(coord)

def command(o,operation,**fields):
 return o.a.handle(dict(subject_key='a'*64,command=dict(operation=operation,**fields)))
def prepare(o):
 return command(o,'prepare',packet_id=str(uuid4()),task_id=o.task,account_alias='fixture',reservation_id=o.grant.grant_id)
def approve(o,p):return command(o,'authorize',packet_id=p['packet_id'],plan_sha256=p['plan_sha256'])
def start(o,p):return command(o,'start',packet_id=p['packet_id'],plan_sha256=p['plan_sha256'])

def test_preparation_is_not_authority_and_start_is_consumed_before_first_get(owner):
 o=owner;p=prepare(o);assert p['state']=='PREPARED' and not p['consumed'] and not o.calls
 with pytest.raises(RuntimeRefused,match='READ_GRANT_REQUIRED'):start(o,p)
 approve(o,p);s=start(o,p);assert s['consumed'] and not o.calls
 o.a.tick();assert len(o.calls)==1
 assert start(o,p)['consumed'];o.a.tick();assert len(o.calls)==1

def test_complete_sequence_seals_once_without_exposing_private_data(owner):
 o=owner;p=prepare(o);approve(o,p);start(o,p)
 for _ in range(20):o.a.tick()
 status=command(o,'status',packet_id=p['packet_id'])
 assert status['state']=='EVIDENCE_READY' and status['responses']==6 and status['attempts']==6
 assert len(o.calls)==6 and status['financial_accepted'] is False
 assert KEY not in json.dumps(status) and SECRET not in json.dumps(status)
 assert 'ciphertext' not in status and status['evidence']['size_bytes']>0
 o.a.tick();assert len(o.calls)==6

@pytest.mark.parametrize('field,value',[('subject_key','b'*64),('plan_sha256','b'*64)])
def test_wrong_grant_binding_refused(owner,field,value):
 o=owner;p=prepare(o);packet=dict(subject_key='a'*64,command=dict(operation='authorize',packet_id=p['packet_id'],plan_sha256=p['plan_sha256']))
 if field=='subject_key':packet[field]=value
 else:packet['command'][field]=value
 with pytest.raises(RuntimeRefused):o.a.handle(packet)
 assert not o.calls

@pytest.mark.parametrize('delta',[60,61,-1])
def test_expired_or_reversed_start_refused(owner,delta):
 o=owner;p=prepare(o);approve(o,p);o.clock.utc+=delta;o.clock.mono+=delta
 with pytest.raises(RuntimeRefused,match='READ_GRANT_EXPIRED'):start(o,p)
 assert not o.calls

def test_lost_health_and_cancel_stop_further_gets(owner):
 o=owner;p=prepare(o);approve(o,p);start(o,p);o.a.tick();o.e.halt('FIXTURE_HEALTH_LOST');o.a.tick()
 assert command(o,'status',packet_id=p['packet_id'])['state']=='ABORTED' and len(o.calls)==1

def test_cancel_pending_stops_without_health_requirement(owner):
 o=owner;p=prepare(o);approve(o,p);start(o,p);o.a.tick();o.e.halt('FIXTURE_HEALTH_LOST')
 result=command(o,'cancel',packet_id=p['packet_id']);assert result['state']=='CANCELED'
 o.a.tick();assert len(o.calls)==1 and o.calls[0].native_closed

def test_restart_cannot_reissue_consumed_packet(owner):
 o=owner;p=prepare(o);approve(o,p);start(o,p);o.a.tick();o.a.close()
 o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
 assert start(o,p)['state']=='INTERRUPTED';o.a.tick();assert len(o.calls)==1

def test_storage_reservation_and_no_public_transport_overrides(owner):
 o=owner
 with pytest.raises(RuntimeRefused):command(o,'prepare',packet_id=str(uuid4()),task_id=o.task,account_alias='fixture',reservation_id=str(uuid4()))
 p=prepare(o)
 with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):command(o,'authorize',packet_id=p['packet_id'],plan_sha256=p['plan_sha256'],url='http://127.0.0.1')

def test_ignored_consume_write_never_dispatches(owner):
 o=owner;p=prepare(o);approve(o,p)
 o.a.store.conn.execute("CREATE TRIGGER deny_read_update BEFORE UPDATE ON paper_read_packets BEGIN SELECT RAISE(IGNORE); END")
 with pytest.raises(RuntimeRefused,match='READ_WRITE_UNVERIFIED'):start(o,p)
 o.a.tick();assert not o.calls


def test_rejected_200_reply_keeps_numeric_status_without_body(owner):
 o=owner;p=prepare(o);approve(o,p);start(o,p);o.a.tick()
 o.calls[0].poll=lambda:SimpleNamespace(status_code=200,body=b'not json')
 o.a.tick();s=command(o,'status',packet_id=p['packet_id'])
 assert s['state']=='ABORTED' and s['requests'][0]['http_status']==200
 assert b'not json' not in o.a.db.execute('SELECT body FROM paper_read_packets').fetchone()[0].encode()

def test_large_valid_deficiency_set_fits_compact_owner_receipt(owner):
 from test_paper_portfolio import order
 o=owner;p=prepare(o);approve(o,p);start(o,p);page=0
 for _ in range(13):
  o.a.tick();g=o.calls[-1];op=g.request.to_payload()['operation'];data=body(op)
  if op=='POSITIONS':data=[None]*200
  elif op=='ORDERS':
   data=[order(page*25+i,asset_class='crypto',order_class='bracket',client_order_id='foreign-'+str(page*25+i)) for i in range(24 if page==7 else 25)];page+=1
  g.poll=lambda data=data:SimpleNamespace(status_code=200,body=json.dumps(data).encode())
  o.a.tick()
 s=command(o,'status',packet_id=p['packet_id']);assert s['state']=='EVIDENCE_READY' and s['responses']==13
 assert len(o.a.db.execute('SELECT body FROM paper_read_packets').fetchone()[0].encode())<16000


def test_cipher_chunks_are_ordered_bounded_and_duplicate_safe(owner):
 import base64
 o=owner;p=prepare(o);approve(o,p);start(o,p)
 for _ in range(20):o.a.tick()
 s=command(o,'status',packet_id=p['packet_id']);sha=s['evidence']['sha256']
 args=dict(operation='chunk',packet_id=p['packet_id'],offset=0,sha256=sha)
 first=o.a.transfer(args);assert first==o.a.transfer(args)
 assert len(base64.b64decode(first['data']))<=32768
 with pytest.raises(RuntimeRefused):o.a.transfer(dict(args,offset=1))
 with pytest.raises(RuntimeRefused):o.a.transfer(dict(args,sha256='a'*64))
 with pytest.raises(RuntimeRefused):o.a.require_checkpoint()

def test_failed_terminal_write_keeps_same_seal_publishable(owner,monkeypatch):
 o=owner;p=prepare(o);approve(o,p);start(o,p);original=o.a._write;failed=[]
 def fail_once(value,**kw):
  if value['state']=='EVIDENCE_READY' and not failed:failed.append(o.a._cipher.ciphertext);raise RuntimeRefused('READ_WRITE_UNVERIFIED')
  return original(value,**kw)
 monkeypatch.setattr(o.a,'_write',fail_once)
 for _ in range(20):o.a.tick()
 s=command(o,'status',packet_id=p['packet_id'])
 assert s['state']=='ABORTED' and s['evidence'] is not None and len(failed)==1
 assert o.a._cipher.ciphertext==failed[0] and s['evidence']['sha256']==hashlib.sha256(failed[0]).hexdigest()
 assert o.a._active is None and o.a._packet is None

@pytest.mark.parametrize('status',[401,408,500])
def test_failed_http_status_is_retained_without_error_body(owner,status):
 o=owner;p=prepare(o);approve(o,p);start(o,p);o.a.tick();g=o.calls[0]
 def fail():g.status_code=status;raise RuntimeRefused('HTTP_STATUS_UNACCEPTABLE')
 g.poll=fail;o.a.tick();s=command(o,'status',packet_id=p['packet_id'])
 assert s['state']=='ABORTED' and s['requests'][0]['http_status']==status and len(o.calls)==1


def test_packet_deadline_stops_before_another_get(owner,monkeypatch):
 import compertum.runtime.paper_read_packet as module
 o=owner;monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:o.clock.mono))
 p=prepare(o);approve(o,p);start(o,p);o.a.tick();o.a.tick()
 o.clock.mono+=30;o.clock.utc+=30;o.a.tick();s=command(o,'status',packet_id=p['packet_id'])
 assert s['state']=='ABORTED' and s['reason']=='PAPER_PACKET_DEADLINE' and len(o.calls)==1
 assert s['evidence'] is not None


def test_unpublished_ack_cannot_clear_cipher(owner):
 from compertum.runtime.paper_read_evidence import publish_read_evidence
 o=owner;p=prepare(o);approve(o,p);start(o,p)
 for _ in range(20):o.a.tick()
 cipher=o.a._cipher;g=o.manager.split_grant(o.grant,len(cipher.ciphertext))
 fake=dict(artifact_id=str(uuid4()),path=f'artifacts/runs/{o.task}/paper-read-{p["packet_id"]}.bin',size_bytes=len(cipher.ciphertext),sha256=hashlib.sha256(cipher.ciphertext).hexdigest(),task_id=o.task)
 with pytest.raises(RuntimeRefused):o.a.transfer(dict(operation='ack',packet_id=p['packet_id'],manifest=fake))
 assert o.a._cipher is cipher
 receipt=publish_read_evidence(o.manager,g,cipher)
 ack=o.a.transfer(dict(operation='ack',packet_id=p['packet_id'],manifest=receipt));assert ack['state']=='PUBLISHED'
 assert o.a.transfer(dict(operation='ack',packet_id=p['packet_id'],manifest=receipt))==ack
 assert o.a._cipher is None


def test_read_routes_keep_write_capabilities_closed(monkeypatch):
 from compertum.runtime.supervisor import Supervisor,ACTIONS
 from compertum.runtime.bootstrap import validate_worker_commands
 from compertum.domain import capability_for
 s=object.__new__(Supervisor);s.partial_fixture=True
 with pytest.raises(RuntimeRefused,match='EXECUTION_UNAVAILABLE'):s._dispatch(SimpleNamespace(subject_key='a'*64),'paper_read',{'operation':'status'})
 assert 'paper_read' in ACTIONS and 'paper_read_transfer' not in ACTIONS
 for action in ('paper.arm','paper.start','paper.cancel','paper.close'):assert capability_for(action).exit_code!=0
 for role in ('execution','watchdog','evaluation'):
  for action in ('paper_read','paper_read_transfer'):
   with pytest.raises(RuntimeRefused,match='WORKER_COMMAND_DENIED'):validate_worker_commands(role,frozenset({action}))
