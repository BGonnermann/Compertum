"""Native owners/SQLite/DPAPI; 64 KiB reserve and market producers are simulated."""
import importlib,json
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_paper_read_owner import owner
from test_execution_health import pair
from compertum.runtime.errors import RuntimeRefused


@pytest.fixture
def market(owner,monkeypatch):
 o=owner;module=importlib.import_module('compertum.runtime.paper_market_owner')
 o.clock.utc=datetime.fromisoformat('2023-11-24T14:00:00+00:00').timestamp()
 monkeypatch.setattr(module,'time',o.module.time)
 o.market_calls=[];o.market_module=module;o.fail_close=False;o.events=[]
 class Producer:
  def __init__(self,lease,plan,protected,*,collection_id,mode):
   assert not o.a.db.in_transaction
   v=json.loads(o.a.db.execute('SELECT value FROM state WHERE key=?',('paper_market_job:'+collection_id,)).fetchone()[0])
   assert v['state']=='RUNNING' and v['consumed']
   self.job=collection_id;self._pending=None;self._cleanup_pending=None;self._closed=False
   self.state='READY';self.reason=None;self.attempts=0;self.pages=0;o.market_calls.append(self)
  def status(self):return dict(state=self.state,reason=self.reason,attempts=self.attempts,pages=self.pages)
  def dispatch(self):self.attempts+=1;self.state='PENDING';o.events.append('market')
  def poll(self):self.pages+=1;self.state='PAGINATION_COMPLETE'
  def cancel(self):self.state='INCOMPLETE';self.reason='CANCELLED'
  def private_snapshot(self):return self
  def close(self):
   self._closed=True
   if o.fail_close:self._cleanup_pending=object();raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')
   self._cleanup_pending=None
 monkeypatch.setattr(module,'_MarketCollection',Producer)
 monkeypatch.setattr(module,'protect_market_evidence',lambda lease,snapshot,task_id:SimpleNamespace(ciphertext=b'simulated-cipher',collection_id=snapshot.job))
 return o


def send(o,operation,*,subject='a'*64,**fields):
 return o.a.market_handle(dict(subject_key=subject,command=dict(operation=operation,**fields)))


def prepare(o,**kw):
 args=dict(job_id=str(uuid4()),task_id=o.task,reservation_id=o.grant.grant_id,account_alias='fixture',mode='HISTORY',symbol='MSFT',history=None)
 args.update(kw);return send(o,'prepare',**args)


def authorize(o,p):return send(o,'authorize',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
def start(o,p):return send(o,'start',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
def status(o,p):return send(o,'status',job_id=p['job_id'])


def test_prepare_authorize_start_commit_before_constructor_and_never_repeat(market):
 o=market;p=prepare(o);assert p['state']=='PREPARED' and not p['consumed'] and not o.market_calls
 with pytest.raises(RuntimeRefused,match='MARKET_GRANT_REQUIRED'):start(o,p)
 authorize(o,p);s=start(o,p);assert s['consumed'] and len(o.market_calls)==1 and not o.events
 assert start(o,p)==s and len(o.market_calls)==1
 o.a.tick();assert o.events==['market']
 o.a.tick();s=status(o,p);assert s['state']=='EVIDENCE_READY' and s['summary']['responses']==1 and s['evidence']
 o.a.tick();assert len(o.market_calls)==1


@pytest.mark.parametrize('change',['subject','grant','plan_hash','field'])
def test_wrong_subject_grant_or_caller_overrides_refuse(market,change):
 o=market;p=prepare(o);args=dict(job_id=p['job_id'],grant_sha256=p['grant_sha256'])
 if change=='subject':args['subject']='b'*64
 elif change=='grant':args['grant_sha256']='b'*64
 elif change=='plan_hash':args['grant_sha256']=p['plan_sha256']
 else:args['url']='https://example.invalid'
 with pytest.raises(RuntimeRefused):send(o,'authorize',**args)
 assert not o.market_calls


@pytest.mark.parametrize('wall,mono',[(60,60),(-1,-1),(6,0),(0,6)])
def test_expired_reversed_or_divergent_clock_cannot_start(market,wall,mono):
 o=market;p=prepare(o);authorize(o,p);o.clock.utc+=wall;o.clock.mono+=mono
 with pytest.raises(RuntimeRefused,match='MARKET_GRANT_EXPIRED'):start(o,p)
 assert not o.market_calls and not status(o,p)['consumed']


def test_ignored_consumption_write_never_constructs_producer(market):
 o=market;p=prepare(o);authorize(o,p)
 o.a.db.execute("CREATE TRIGGER deny_market_consume BEFORE UPDATE ON state WHEN NEW.key LIKE 'paper_market_job:%' BEGIN SELECT RAISE(IGNORE); END")
 with pytest.raises(RuntimeRefused,match='MARKET_WRITE_UNVERIFIED'):start(o,p)
 assert not o.market_calls and not status(o,p)['consumed']


def test_constructor_failure_is_consumed_and_not_retried(market,monkeypatch):
 o=market;p=prepare(o);authorize(o,p);calls=[]
 def fail(*a,**kw):calls.append(True);raise RuntimeRefused('PAPER_COLLECTION_INVALID')
 monkeypatch.setattr(o.market_module,'_MarketCollection',fail)
 result=start(o,p);assert result['state']=='ABORTED' and result['consumed']
 assert start(o,p)==result and calls==[True]


def test_collection_capacity_and_reservation_are_verified(market):
 o=market
 with pytest.raises(RuntimeRefused,match='MARKET_STORAGE_UNVERIFIED'):prepare(o,reservation_id=str(uuid4()))
 p=prepare(o);authorize(o,p);start(o,p)
 with pytest.raises(RuntimeRefused,match='MARKET_OWNER_CAPACITY'):prepare(o)


def test_account_confirmation_preserved_and_account_tick_goes_first(market,monkeypatch):
 o=market;marker=SimpleNamespace(close=lambda:None);o.a._preflight=marker;o.a._account_proposal=marker
 p=prepare(o);authorize(o,p);start(o,p)
 assert o.a._preflight is marker and o.a._account_proposal is marker
 monkeypatch.setattr(o.a,'_tick_account',lambda:o.events.append('account'))
 o.a.tick();assert o.events==['account','market']


def test_market_only_owner_ticks_and_checkpoint_waits_for_publication(market):
 o=market;p=prepare(o);authorize(o,p);start(o,p)
 with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):o.a.require_checkpoint()
 o.a.tick();o.a.tick();assert status(o,p)['state']=='EVIDENCE_READY'
 with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):o.a.require_checkpoint()


def test_zero_response_cancellation_seals_evidence_before_disposal(market):
 o=market;p=prepare(o);authorize(o,p);start(o,p)
 s=send(o,'cancel',job_id=p['job_id'])
 assert s['state']=='CANCELED' and s['summary']==dict(state='INCOMPLETE',reason='CANCELLED',attempts=0,responses=0)
 assert s['evidence'] and o.market_calls[0]._closed
 assert not o.events


def test_health_loss_stops_market_and_keeps_failed_evidence(market):
 o=market;p=prepare(o);authorize(o,p);start(o,p);o.e.halt('FIXTURE_HEALTH_LOST');o.a.tick()
 s=status(o,p);assert s['state']=='ABORTED' and s['reason']=='EXECUTION_HEALTH_UNVERIFIED' and s['evidence']
 assert not o.events and o.market_calls[0]._closed


def test_close_failure_retains_resource_blocks_replacement_and_checkpoint(market):
 o=market;p=prepare(o);authorize(o,p);start(o,p);o.fail_close=True
 try:
  with pytest.raises(RuntimeRefused,match='HTTP_CLEANUP_UNVERIFIED'):o.a.close()
  assert not o.a._closed and o.a._market._producer is o.market_calls[0]
  with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):o.a.require_checkpoint()
  with pytest.raises(RuntimeRefused,match='READ_OWNER_CAPACITY'):o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
  with pytest.raises(RuntimeRefused,match='MARKET_OWNER_CAPACITY'):prepare(o)
 finally:o.fail_close=False;o.a.close()


def test_restart_invalidates_market_grants_without_recollection(market):
 o=market;p=prepare(o);authorize(o,p);start(o,p);o.a.close()
 o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
 assert start(o,p)['state']=='INTERRUPTED';o.a.tick();assert len(o.market_calls)==1 and not o.events


def test_collection_after_original_cutoff_refused(market):
 o=market;o.clock.utc+=25*60
 with pytest.raises(RuntimeRefused):prepare(o)
 assert not o.market_calls


@pytest.mark.parametrize('fault',['mode_list','mode_dict','symbol','symbol_list','after_cutoff','weekend'])
def test_invalid_prepare_is_bounded_and_owner_accepts_later_valid_input(market,fault):
 o=market;at=o.clock.utc;args={}
 if fault=='mode_list':args['mode']=[]
 elif fault=='mode_dict':args['mode']={}
 elif fault=='symbol':args['symbol']='INVALID'
 elif fault=='symbol_list':args['symbol']=[]
 elif fault=='after_cutoff':o.clock.utc+=25*60+1
 else:o.clock.utc=datetime.fromisoformat('2023-11-25T14:00:00+00:00').timestamp()
 with pytest.raises(RuntimeRefused):prepare(o,**args)
 assert not o.market_calls and not o.a._market.records.all() and not o.a._closed
 o.clock.utc=at;p=prepare(o);authorize(o,p);start(o,p)
 assert len(o.market_calls)==1 and status(o,p)['consumed']
