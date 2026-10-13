"""Account attestation routing; all replies and PAPER_TLS substitutions are invented."""
import json,pickle
from contextlib import contextmanager
from uuid import uuid4
import pytest
from test_execution_health import pair
from test_paper_read_owner import owner
from test_paper_read_publication import publication,launch
from test_paper_read_preparation import ACCOUNT,KEY,SECRET
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_account_binding import _AccountProposal,_history


def published(fixture):
 o,pub,module=fixture;p=launch(fixture)
 for _ in range(10):pub.tick()
 assert pub.handle('a'*64,dict(operation='status',packet_id=p['packet_id']))['state']=='PUBLISHED'
 return o,pub,p


def call(pub,p,op,**kw):return pub.handle('a'*64,dict(operation=op,packet_id=p['packet_id'],**kw))


@pytest.fixture
def invented_paper_origin(monkeypatch):
 import compertum.runtime.paper_preflight as module
 original=module.native_read_provenance
 def substituted(*args):return dict(original(*args),origin='PAPER_TLS')
 monkeypatch.setattr(module,'native_read_provenance',substituted)


def propose(fixture):
 o,pub,p=published(fixture);r=call(pub,p,'account_propose');return o,pub,p,r


def confirm(pub,p,r,**kw):
 return call(pub,p,'account_confirm',proposal_sha256=r['proposal_sha256'],acknowledgement=r['required_acknowledgement'],**kw)


def test_unverified_origin_cannot_confirm_account(publication):
 o,pub,p,r=propose(publication)
 assert r['confirmation_recorded'] is False and r['transport_authorized'] is False
 assert r['actual_flat'] is None and r['financial_accepted'] is False
 assert all(x not in json.dumps(r) for x in (ACCOUNT,KEY,SECRET,'100000'))
 with pytest.raises(RuntimeRefused,match='PAPER_ACCOUNT_NATIVE_ORIGIN_REQUIRED'):confirm(pub,p,r)
 assert len(o.calls)==6
 assert o.a.store.conn.execute("SELECT count(*) FROM state WHERE key LIKE 'paper_account_alias:%'").fetchone()==(0,)
 with pytest.raises(RuntimeRefused):pickle.dumps(o.a._account_proposal)
 with pytest.raises(RuntimeRefused):_AccountProposal()


def test_explicit_confirmation_is_not_order_authority(publication,invented_paper_origin):
 o,pub,p,r=propose(publication)
 assert call(pub,p,'account_propose')==r
 assert call(pub,p,'account_status')['identity_status']=='UNCONFIRMED'
 receipt=confirm(pub,p,r);assert receipt['confirmation_recorded'] and receipt['live_context']=='NOT_ASSERTED'
 assert confirm(pub,p,r)==receipt
 live=call(pub,p,'account_status')
 assert live['identity_status']=='CONFIRMED_CURRENT_CONTEXT' and live['opening_status']=='EMPTY_PORTFOLIO_OBSERVED'
 assert live['trading_status']=='BLOCKED' and live['actual_flat'] is None and not live['transport_authorized']
 assert live['local_history']['status']=='VERIFIED_ZERO_PRE_SCHEMA'
 assert o.a.store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='fake_intents'").fetchone() is None
 assert len(o.calls)==6


@pytest.mark.parametrize('change',['subject','hash','ack','manifest','future_flag'])
def test_exact_binding_rejects_substitution(publication,invented_paper_origin,change):
 o,pub,p,r=propose(publication);kw=dict(operation='account_confirm',packet_id=p['packet_id'],proposal_sha256=r['proposal_sha256'],acknowledgement=r['required_acknowledgement']);subject='a'*64
 if change=='subject':subject='b'*64
 elif change=='hash':kw['proposal_sha256']='b'*64
 elif change=='ack':kw['acknowledgement']='YES'
 elif change=='manifest':kw['manifest']={}
 else:kw['account_verified']=True
 with pytest.raises(RuntimeRefused):pub.handle(subject,kw)
 assert not call(pub,p,'account_status')['confirmation_recorded']


@pytest.mark.parametrize('change',['expired','close','restart','credentials','artifact'])
def test_live_confirmation_never_survives_invalid_context(publication,invented_paper_origin,monkeypatch,change):
 o,pub,p,r=propose(publication);confirm(pub,p,r)
 if change=='expired':o.clock.utc+=31;o.clock.mono+=31
 elif change=='close':o.a.close()
 elif change=='restart':o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
 elif change=='credentials':
  import compertum.runtime.paper_preflight as m
  from compertum.runtime.paper_credentials import seal_paper_credentials
  replacement=seal_paper_credentials(o.a.lease,'fixture',bytearray(b'DIFFERENTKEY'),bytearray(b'DIFFERENTSECRET'))
  monkeypatch.setattr(m,'load_paper_slot',lambda *a:replacement)
 else:
  path=o.manager.root/pub._route(p['packet_id'])['publication']['manifest']['path'];path.write_bytes(b'broken encrypted fixture')
 if change=='close':
  with pytest.raises(RuntimeRefused):call(pub,p,'account_status')
 else:
  live=call(pub,p,'account_status');assert live['identity_status']=='HISTORICAL_ONLY' and live['opening_status']=='UNVERIFIED'


def test_same_account_new_packet_preserves_alias_but_changed_account_refuses(publication,invented_paper_origin,monkeypatch):
 o,pub,p,r=propose(publication);confirm(pub,p,r)
 o,pub,p2,r2=propose(publication);assert r2['proposal_sha256']!=r['proposal_sha256'];confirm(pub,p2,r2)
 import test_paper_read_owner as fixture
 original=fixture.body
 def changed(op):
  value=original(op)
  return dict(value,id='22222222-2222-4222-8222-222222222222') if op=='ACCOUNT' else value
 monkeypatch.setattr(fixture,'body',changed)
 o,pub,p3=published(publication)
 with pytest.raises(RuntimeRefused,match='PAPER_ACCOUNT_ALIAS_CONFLICT'):call(pub,p3,'account_propose')


@pytest.mark.parametrize('change',['missing_mirror','bad_mirror','missing_guard','partial_schema','conflict'])
def test_missing_or_partial_history_is_not_an_empty_opening(publication,invented_paper_origin,change):
 o,pub,p=published(publication);db=o.a.store.conn
 with db:
  if change=='missing_mirror':db.execute("DELETE FROM state WHERE key='fake_attempt_guard_head'")
  elif change=='bad_mirror':db.execute("UPDATE state SET value='{}' WHERE key='fake_attempt_guard_head'")
  elif change=='partial_schema':db.execute('CREATE TABLE fake_intent_events(seq INTEGER)')
  elif change=='conflict':db.execute("INSERT INTO state VALUES('fake_attempt_conflict','true')")
 if change=='missing_guard':
  path=o.a.store.root/'state/fake-execution-attempts/head.json';path.rename(path.with_suffix('.retained'))
 assert _history(o.a)['status']=='UNVERIFIED'
 r=call(pub,p,'account_propose');confirm(pub,p,r)
 live=call(pub,p,'account_status');assert live['opening_status']=='BLOCKED' and 'LOCAL_HISTORY_UNVERIFIED' in live['deficiencies']


@pytest.mark.parametrize('kind',['position','foreign_order','disabled','negative_cash'])
def test_identity_attestation_does_not_adopt_unexplained_economics(publication,invented_paper_origin,monkeypatch,kind):
 import test_paper_read_owner as fixture
 from test_paper_portfolio import order
 original=fixture.body
 def changed(op):
  v=original(op)
  if op=='POSITIONS' and kind=='position':return [None]
  if op=='ORDERS' and kind=='foreign_order':return [order(1,client_order_id='foreign-order')]
  if op=='ACCOUNT' and kind=='disabled':return dict(v,account_blocked=True)
  if op=='ACCOUNT' and kind=='negative_cash':return dict(v,cash='-1')
  return v
 monkeypatch.setattr(fixture,'body',changed)
 o,pub,p,r=propose(publication);confirm(pub,p,r);live=call(pub,p,'account_status')
 assert live['identity_status']=='CONFIRMED_CURRENT_CONTEXT' and live['opening_status']=='BLOCKED'
 assert live['trading_status']=='BLOCKED' and live['actual_flat'] is None


def test_failed_atomic_confirmation_does_not_claim_alias(publication,invented_paper_origin):
 o,pub,p,r=propose(publication);db=o.a.store.conn
 db.execute("CREATE TRIGGER refuse_confirmation BEFORE UPDATE ON state WHEN NEW.key LIKE 'paper_account_proposal:%' BEGIN SELECT RAISE(ABORT,'invented failure'); END")
 with pytest.raises(RuntimeRefused):confirm(pub,p,r)
 assert db.execute("SELECT count(*) FROM state WHERE key LIKE 'paper_account_alias:%'").fetchone()==(0,)
 assert not call(pub,p,'account_status')['confirmation_recorded']


def test_expiry_during_artifact_check_cannot_commit_confirmation(publication,invented_paper_origin,monkeypatch):
 o,pub,p,r=propose(publication)
 import compertum.runtime.paper_account_binding as module
 original=module.open_read_evidence
 @contextmanager
 def slowed(*a,**kw):
  with original(*a,**kw) as opened:
   yield opened
   o.clock.utc+=31;o.clock.mono+=31
 monkeypatch.setattr(module,'open_read_evidence',slowed)
 with pytest.raises(RuntimeRefused):confirm(pub,p,r)
 assert o.a.store.conn.execute("SELECT count(*) FROM state WHERE key LIKE 'paper_account_alias:%'").fetchone()==(0,)



def test_account_status_repeated_request_is_fresh_not_cached(publication,invented_paper_origin):
 from compertum.runtime.supervisor import Supervisor
 from compertum.runtime.ipc import ProtocolDecision
 o,pub,p,r=propose(publication);confirm(pub,p,r)
 s=object.__new__(Supervisor);s.store=o.manager.store
 s.store.conn.execute('CREATE TABLE operator_requests(request_id TEXT PRIMARY KEY,binding TEXT,result TEXT,error TEXT)')
 s._dispatch=lambda decision,action,payload:pub.handle(decision.subject_key,payload)
 decision=ProtocolDecision(str(uuid4()),'a'*64,'b'*64,1);payload=dict(operation='account_status',packet_id=p['packet_id'])
 assert s.handle(decision,'paper_read',payload)['identity_status']=='CONFIRMED_CURRENT_CONTEXT'
 o.clock.utc+=31;o.clock.mono+=31
 assert s.handle(decision,'paper_read',payload)['identity_status']=='HISTORICAL_ONLY'
 assert s.store.conn.execute('SELECT count(*) FROM operator_requests').fetchone()==(0,)


def test_existing_empty_journal_is_read_without_repair(publication,invented_paper_origin):
 from compertum.fake_execution_journal import FakeIntentJournal
 o,pub,module=publication;FakeIntentJournal(o.a.store)
 before=o.a.store.conn.total_changes
 h=_history(o.a);assert h['status']=='VERIFIED_HISTORY' and h['empty'] is True
 assert o.a.store.conn.total_changes==before
 o,pub,p,r=propose(publication);confirm(pub,p,r)
 assert call(pub,p,'account_status')['opening_status']=='EMPTY_PORTFOLIO_OBSERVED'



@pytest.mark.parametrize('field,value',[
 ('created_at',ACCOUNT),('expires_at',{}),('account_alias',None),('subject_key','b'*64),
 ('version',True),('generation',False),('purpose','WRONG_PURPOSE')],ids=['private-id-time','object-time','null-alias','changed-subject','bool-version','bool-generation','purpose'])
def test_corrupt_saved_proposal_never_reaches_historical_output(publication,invented_paper_origin,field,value):
 from compertum.data.encoding import canonical
 import hashlib
 o,pub,p,r=propose(publication);key='paper_account_proposal:'+p['packet_id']
 saved=json.loads(o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0]);saved['proposal'][field]=value
 saved['proposal_sha256']=hashlib.sha256(canonical(saved['proposal'])).hexdigest()
 with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(canonical(saved).decode(),key))
 with pytest.raises(RuntimeRefused):call(pub,p,'account_status')


def test_expiry_during_history_read_cannot_report_current_confirmation(publication,invented_paper_origin,monkeypatch):
 import compertum.runtime.paper_account_binding as module
 o,pub,p,r=propose(publication);confirm(pub,p,r);original=module._history
 def slowed(owner):
  result=original(owner);o.clock.utc+=31;o.clock.mono+=31;return result
 monkeypatch.setattr(module,'_history',slowed)
 result=call(pub,p,'account_status')
 assert result['identity_status']=='HISTORICAL_ONLY' and result['live_context']=='UNAVAILABLE'
 assert result['opening_status']=='UNVERIFIED'


def test_boolean_zero_history_is_not_verified_empty(publication,invented_paper_origin):
 from compertum.data.encoding import canonical
 from compertum.fake_attempt_guard import ZERO
 o,pub,p=published(publication)
 with o.a.db:o.a.db.execute("UPDATE state SET value=? WHERE key='fake_attempt_guard_head'",(canonical(dict(sequence=False,sha256=ZERO)).decode(),))
 assert _history(o.a)['status']=='UNVERIFIED'
 r=call(pub,p,'account_propose');confirm(pub,p,r)
 assert call(pub,p,'account_status')['opening_status']=='BLOCKED'


@pytest.mark.parametrize('field,value',[('version',True),('first_packet_id',ACCOUNT),('confirmed_at',ACCOUNT),('identity_sha256','bad')])
def test_corrupt_alias_mapping_is_refused(publication,invented_paper_origin,field,value):
 from compertum.data.encoding import canonical
 o,pub,p,r=propose(publication);confirm(pub,p,r);key='paper_account_alias:fixture'
 saved=json.loads(o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0]);saved[field]=value
 with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(canonical(saved).decode(),key))
 with pytest.raises(RuntimeRefused):call(pub,p,'account_status')
