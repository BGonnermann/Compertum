"""Native DPAPI/owner fixtures with invented replies; PAPER_TLS origin is injected.

Run only after M3 completes. These tests do not establish actual account access.
"""
import json
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime import paper_account_binding as b,paper_opening as m
from test_execution_health import pair
from test_paper_read_owner import owner
from test_paper_read_publication import publication
from test_paper_account_binding import invented_paper_origin,propose,confirm,call


def opened(fixture):
 o,pub,p,r=propose(fixture);confirm(pub,p,r);manifest=pub._route(p['packet_id'])['publication']['manifest']
 return o,pub,p,r,manifest


def test_native_original_pin_and_private_current_reader(publication,invented_paper_origin):
 o,pub,p,r,manifest=opened(publication)
 a=o.a.opening(p['packet_id'],manifest)
 assert a['opening_status']=='CURRENT_CLEAN_OPENING' and a['scope']=='INITIAL_BASELINE_ONLY'
 assert a['trading_status']=='BLOCKED' and not a['transport_authorized'] and not a['financial_accepted'] and a['actual_flat'] is None
 before=b._state(o.a,m._PREFIX+'fixture');confirm(pub,p,r)
 assert b._state(o.a,m._PREFIX+'fixture')==before
 assert o.a.opening_history('fixture')['opening_status']=='HISTORICAL_ONLY'
 assert len(o.calls)==6


def test_unverified_native_origin_cannot_create_opening(publication):
 o,pub,p,r=propose(publication)
 with pytest.raises(RuntimeRefused,match='PAPER_ACCOUNT_NATIVE_ORIGIN_REQUIRED'):confirm(pub,p,r)
 assert b._state(o.a,m._PREFIX+'fixture') is None


@pytest.mark.parametrize('point',['alias','confirmation','opening'])
def test_native_atomic_confirmation_interruption(publication,invented_paper_origin,monkeypatch,point):
 o,pub,p,r=propose(publication);original=b._put
 def interrupted(owner,key,value,**kw):
  original(owner,key,value,**kw)
  if (point=='alias' and key.startswith(b._ALIAS)) or (point=='confirmation' and key.startswith(b._PREFIX)) or (point=='opening' and key.startswith(m._PREFIX)):raise RuntimeRefused('INJECTED_OPENING_INTERRUPTION')
 with monkeypatch.context() as mp:
  mp.setattr(b,'_put',interrupted)
  with pytest.raises(RuntimeRefused,match='INJECTED_OPENING_INTERRUPTION'):confirm(pub,p,r)
 assert b._state(o.a,b._ALIAS+'fixture') is None and b._state(o.a,m._PREFIX+'fixture') is None
 assert b._stored(o.a,p['packet_id'])['confirmed_at'] is None
 confirm(pub,p,r);manifest=pub._route(p['packet_id'])['publication']['manifest']
 assert o.a.opening(p['packet_id'],manifest)['opening_status']=='CURRENT_CLEAN_OPENING'


def test_native_later_cash_always_compares_first_protected_cash(publication,invented_paper_origin,monkeypatch):
 import test_paper_read_owner as fixture
 o,pub,p,r,manifest=opened(publication);before=b._state(o.a,m._PREFIX+'fixture');original=fixture.body;cash=['100000.01']
 def body(op):
  value=original(op)
  return dict(value,cash=cash[0]) if op=='ACCOUNT' else value
 monkeypatch.setattr(fixture,'body',body)
 o,pub,p2,r2,m2=opened(publication);assert o.a.opening(p2['packet_id'],m2)['opening_status']=='CURRENT_CLEAN_OPENING'
 cash[0]='100000.02';o,pub,p3,r3,m3=opened(publication);result=o.a.opening(p3['packet_id'],m3)
 assert result['opening_status']=='BLOCKED' and 'UNEXPLAINED_CASH_CHANGE' in result['deficiencies']
 assert b._state(o.a,m._PREFIX+'fixture')==before
 cash[0]='-1';o,pub,p4,r4,m4=opened(publication);result=o.a.opening(p4['packet_id'],m4)
 assert result['opening_status']=='BLOCKED' and 'NEGATIVE_ACCOUNT_CASH' in result['deficiencies']
 assert b._state(o.a,m._PREFIX+'fixture')==before


def test_native_original_decryption_cannot_refresh_expired_current_context(publication,invented_paper_origin,monkeypatch):
 from contextlib import contextmanager
 o,pub,p,r,manifest=opened(publication);original=m.open_read_evidence
 @contextmanager
 def slow(*args):
  with original(*args) as evidence:yield evidence
  o.clock.utc+=31;o.clock.mono+=31
 monkeypatch.setattr(m,'open_read_evidence',slow)
 with pytest.raises(RuntimeRefused,match='PAPER_PREFLIGHT_STALE'):o.a.opening(p['packet_id'],manifest)


def test_native_original_missing_pin_is_never_recreated(publication,invented_paper_origin):
 o,pub,p,r,manifest=opened(publication)
 with o.a.db:o.a.db.execute('DELETE FROM state WHERE key=?',(m._PREFIX+'fixture',))
 o,pub,p2,r2,m2=opened(publication)
 assert b._state(o.a,m._PREFIX+'fixture') is None
 with pytest.raises(RuntimeRefused,match='UNRECORDED'):o.a.opening(p2['packet_id'],m2)


def test_native_restore_marker_keeps_first_observation_blocked(publication,invented_paper_origin):
 o,pub,module=publication
 (o.a.store.root/'state/generations').mkdir()
 o,pub,p,r,manifest=opened(publication);result=o.a.opening(p['packet_id'],manifest)
 assert result['opening_status']=='BLOCKED' and 'RESTORE_HISTORY_PRESENT' in result['deficiencies']
 before=b._state(o.a,m._PREFIX+'fixture')
 o,pub,p2,r2,m2=opened(publication);assert b._state(o.a,m._PREFIX+'fixture')==before
 assert o.a.opening(p2['packet_id'],m2)['opening_status']=='BLOCKED'


def test_native_reopened_owner_preserves_history_without_live_qualification(publication,invented_paper_origin):
 o,pub,p,r,manifest=opened(publication);before=b._state(o.a,m._PREFIX+'fixture')
 o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
 assert b._state(o.a,m._PREFIX+'fixture')==before
 assert o.a.opening_history('fixture')['opening_status']=='HISTORICAL_ONLY'
 with pytest.raises(RuntimeRefused):o.a.opening(p['packet_id'],manifest)


def _opening_restart_child(root, phase):
 """Real separate processes; reuse explicitly simulated transport/64 KiB fixtures."""
 import hashlib,os
 from contextlib import contextmanager
 from pathlib import Path
 root=Path(root);saved=root/'opening-restart-baseline.json'
 if phase=='first':
  with pytest.MonkeyPatch.context() as mp:
   with contextmanager(pair.__wrapped__)(root,mp) as peers:
    with contextmanager(owner.__wrapped__)(peers,mp,root) as fixture:
     published=publication.__wrapped__(fixture,mp)
     invented_paper_origin.__wrapped__(mp)
     o,pub,p,r,manifest=opened(published)
     assert o.a.opening(p['packet_id'],manifest)['opening_status']=='CURRENT_CLEAN_OPENING'
     record=dict(pin=b._state(o.a,m._PREFIX+'fixture'),manifest=manifest,packet=p['packet_id'],
                 generation=o.a.lease.generation,instance=o.a.lease.identity.process_instance_id,
                 pid=os.getpid(),project_id=o.a.lease.project_id,calls=len(o.calls))
     assert record['calls']==6
     assert hashlib.sha256((root/manifest['path']).read_bytes()).hexdigest()==manifest['sha256']
  saved.write_text(json.dumps(record),encoding='utf-8')
  return dict(phase=phase,generation=record['generation'],instance=record['instance'],pid=record['pid'])
 assert phase=='restart'
 from compertum.persistence import open_store
 from compertum.storage import open_journal_reserve
 from compertum.runtime.identity import resolve_project
 from compertum.runtime.owners import acquire_owner,release_owner
 from compertum.runtime.execution_health import MutualHealth
 from compertum.runtime import paper_read_owner as reader
 original=json.loads(saved.read_text(encoding='utf-8'));lease=acquire_owner(resolve_project(root),'execution')
 calls=[]
 try:
  assert lease.generation==original['generation']+1
  assert lease.identity.process_instance_id!=original['instance']
  assert lease.project_id==original['project_id']
  health=MutualHealth(lease,lambda reason:None,required=True)
  store=open_store(lease,'execution');reserve=open_journal_reserve(lease)
  def denied(*args,**kwargs):
   calls.append(True);raise AssertionError('Restart must not dispatch transport')
  with pytest.MonkeyPatch.context() as mp:
   mp.setattr(reader,'_start_get',denied)
   a=reader.PaperReadOwner(store,reserve,health)
   try:
    assert b._state(a,m._PREFIX+'fixture')==original['pin']
    manifest=original['manifest']
    assert hashlib.sha256((root/manifest['path']).read_bytes()).hexdigest()==manifest['sha256']
    historical=a.opening_history('fixture')
    assert historical['opening_status']=='HISTORICAL_ONLY'
    assert historical['opening_reference_sha256']==original['pin']['sha256']
    assert historical['trading_status']=='BLOCKED' and not historical['transport_authorized']
    assert not historical['financial_accepted'] and historical['actual_flat'] is None
    with pytest.raises(RuntimeRefused,match='PAPER_ACCOUNT_PROPOSAL_UNAVAILABLE'):
     a.opening(original['packet'],manifest)
    a.tick()
    assert not calls and not health.status()['verified']
    assert b._state(a,m._PREFIX+'fixture')==original['pin']
    result=dict(phase=phase,generation=lease.generation,instance=lease.identity.process_instance_id,
                pid=os.getpid(),history=historical,calls=len(calls),reserve_bytes=reserve.receipt()['unused_bytes'])
   finally:a.close()
 finally:release_owner(lease)
 return result


def test_native_new_process_preserves_opening_without_restoring_authority(tmp_path):
 import os,subprocess,sys
 from pathlib import Path
 receipts=[]
 code="import json,sys;sys.path.insert(0,sys.argv[1]);from test_paper_opening_native import _opening_restart_child;print(json.dumps(_opening_restart_child(sys.argv[2],sys.argv[3])))"
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 for phase in ('first','restart'):
  process=subprocess.Popen([sys.executable,'-B','-c',code,str(Path(__file__).parent),str(tmp_path),phase],
                           executable=sys._base_executable,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000)
  try:
   out,err=process.communicate(timeout=30)
   assert process.returncode==0 and not err,err.decode()
   receipt=json.loads(out);assert receipt['phase']==phase and receipt['pid']==process.pid
   receipts.append(receipt)
  finally:
   if process.poll() is None:process.kill();process.communicate(timeout=5)
 assert receipts[1]['generation']==receipts[0]['generation']+1
 assert receipts[1]['instance']!=receipts[0]['instance']
 assert receipts[1]['calls']==0 and receipts[1]['reserve_bytes']==65536
 (tmp_path/'opening-process-restart-receipt.json').write_text(json.dumps(dict(
     processes=receipts,transport='INVENTED_RESPONSES_AND_INJECTED_PAPER_TLS',
     reserve='64_KIB_FIXTURE_NOT_FULL_CAPACITY',financial_accepted=False)),encoding='utf-8')


@pytest.mark.parametrize('kind',['negative_cash','blocked_account'])
def test_native_blocked_first_account_remains_blocked_when_later_clean(publication,invented_paper_origin,monkeypatch,kind):
 import test_paper_read_owner as fixture
 original=fixture.body
 def body(op):
  value=original(op)
  if op!='ACCOUNT':return value
  return dict(value,**({'cash':'-1'} if kind=='negative_cash' else {'trading_blocked':True}))
 with monkeypatch.context() as mp:
  mp.setattr(fixture,'body',body);o,pub,p,r,manifest=opened(publication)
 before=b._state(o.a,m._PREFIX+'fixture');assert before['reference']['disposition']=='BLOCKED'
 o,pub,p2,r2,m2=opened(publication);result=o.a.opening(p2['packet_id'],m2)
 assert result['opening_status']=='BLOCKED' and b._state(o.a,m._PREFIX+'fixture')==before

@pytest.fixture
def reflected_publication(monkeypatch,request):
 import test_paper_read_owner as fixture
 monkeypatch.setattr(fixture,'KEY','PAPER_CLEAN_OPENING_REFERENCE')
 return request.getfixturevalue('publication')


def test_native_new_reference_secret_cannot_enter_execution_state(reflected_publication,invented_paper_origin):
 o,pub,p,r=propose(reflected_publication)
 with pytest.raises(RuntimeRefused,match='SECRET_REFLECTION'):confirm(pub,p,r)
 assert b._state(o.a,b._ALIAS+'fixture') is None and b._state(o.a,m._PREFIX+'fixture') is None
 assert b._stored(o.a,p['packet_id'])['confirmed_at'] is None
 assert all('PAPER_CLEAN_OPENING_REFERENCE' not in value for (value,) in o.a.db.execute('SELECT value FROM state'))
