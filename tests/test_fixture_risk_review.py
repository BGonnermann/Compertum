"""Regression cases from risk review one. All financial inputs are invented."""
import sqlite3
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_risk_calculation import calculate,portfolio,position,order
from test_native_write_journal import journal,paper,native,records,attempt,consume
from test_paper_fixture_risk_context import (risk_inputs,context,simulated_source,confirmed,inputs,history,
 completed,pair,owner,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,account)

@pytest.mark.parametrize('purpose',['CANCEL','CLOSE_LONG'])
def test_risk_reducing_control_allows_fees_above_cash(purpose):
 values=dict(portfolio=portfolio(cash='0',positions=[position()],orders=[order()] if purpose=='CANCEL' else []),
  purpose=purpose,outstanding_fees='0.02')
 if purpose=='CANCEL':values['inputs']=None
 result=calculate(**values).to_payload()
 assert result['original_cash']=='0' and result['available_cash']=='-0.02'
 assert result['request']['operation']==('CANCEL_ORDER' if purpose=='CANCEL' else 'SUBMIT_ORDER')

@pytest.mark.parametrize('phase',['insert','update'])
@pytest.mark.parametrize('target',['restored','surrounding'])
def test_recovery_refuses_trigger_changes(journal,phase,target):
 from compertum.fake_attempt_guard import append_record,verify_attempt_guard
 from compertum.native_write_journal import _NativeWriteJournal
 project,lease,store,j=journal;p,d=records(lease)
 if phase=='insert':
  with store.conn:append_record(store,attempt(p,d))
 else:consume(journal,p,d)
 with store.conn:
  store.conn.execute("INSERT INTO state VALUES('review-surrounding','unchanged')")
  mutation=("UPDATE fake_intents SET state='NATIVE_ACKNOWLEDGED' WHERE intent_id=NEW.intent_id;"
   if target=='restored' else "UPDATE state SET value='changed' WHERE key='review-surrounding';")
  store.conn.execute('CREATE TRIGGER review_recovery AFTER '+phase.upper()+' ON fake_intents BEGIN '+mutation+' END')
 with pytest.raises(RuntimeRefused):_NativeWriteJournal(store,j.reserve)
 assert verify_attempt_guard(project)['records']==[attempt(p,d)]
 assert store.conn.execute("SELECT value FROM state WHERE key='review-surrounding'").fetchone()==('unchanged',)

@pytest.mark.parametrize('kind',['TEXT','BLOB','schema'])
def test_snapshot_refuses_large_values_before_materializing(kind):
 from compertum.native_write_journal import _logical_snapshot
 db=sqlite3.connect(':memory:')
 try:
  if kind=='schema':db.execute('CREATE VIEW huge AS SELECT 1 /*'+'x'*70000+'*/')
  else:
   db.execute('CREATE TABLE huge(value '+kind+')')
   db.execute('INSERT INTO huge VALUES(?)',('x'*(9*1024**2) if kind=='TEXT' else b'x'*(9*1024**2),))
  # SQLite itself rejects an oversized materialized result under this bound.
  # Length checks and CASE projections can still inspect and refuse it safely.
  db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,65536)
  with pytest.raises(RuntimeRefused,match='NATIVE_WRITE_HISTORY_BOUND'):_logical_snapshot(db)
 finally:db.close()

@pytest.mark.parametrize('phase',['factory','prepared'])
@pytest.mark.parametrize('field',['_intents','_input_context','_presence'])
def test_post_health_replacement_refuses(risk_inputs,monkeypatch,phase,field):
 from compertum.runtime import paper_final_proof as module
 o=risk_inputs[0];captured=getattr(o.a,field)
 proofs=context(risk_inputs)._prepare_proofs() if phase=='prepared' else None
 armed=[phase=='prepared']
 if phase=='factory':
  from compertum.runtime import paper_fixture_risk as risk_module
  join=risk_module._join
  def ready(*args):
   result=join(*args);armed[0]=True;return result
  monkeypatch.setattr(risk_module,'_join',ready)
 original=module._health_finish
 def replace(*args):
  original(*args)
  if armed[0]:setattr(o.a,field,object())
 monkeypatch.setattr(module,'_health_finish',replace)
 try:
  with pytest.raises(RuntimeRefused):
   if proofs is None:context(risk_inputs)
   else:module._verify_proofs(*proofs)
 finally:setattr(o.a,field,captured)
