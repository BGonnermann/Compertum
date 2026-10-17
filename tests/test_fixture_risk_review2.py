"""Second risk review. Store identities are real; all financial inputs are invented."""
import sqlite3
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_risk_review import (risk_inputs,context,simulated_source,confirmed,inputs,history,
 completed,pair,owner,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,account)

@pytest.mark.parametrize('kind',['embedded-null','generated-column'])
def test_snapshot_checks_all_selected_bytes_before_reading_them(kind):
 from compertum.native_write_journal import _logical_snapshot
 db=sqlite3.connect(':memory:')
 try:
  if kind=='embedded-null':
   db.execute('CREATE TABLE huge(value TEXT)');db.execute('INSERT INTO huge VALUES(?)',('x\0'+'x'*(9*1024**2),))
  else:
   db.execute('CREATE TABLE huge(value INTEGER,extra BLOB GENERATED ALWAYS AS (zeroblob(9437184)) VIRTUAL)')
   db.execute('INSERT INTO huge(value) VALUES(1)')
  with pytest.raises(RuntimeRefused,match='NATIVE_WRITE_HISTORY_BOUND'):_logical_snapshot(db)
 finally:db.close()

@pytest.mark.parametrize('phase',['factory','prepared'])
@pytest.mark.parametrize('field',['instance','db'])
def test_post_health_presence_internal_replacement_refuses(risk_inputs,monkeypatch,phase,field):
 from compertum.runtime import paper_final_proof as module,paper_fixture_risk as risk_module
 o=risk_inputs[0];presence=o.a._presence;captured=getattr(presence,field)
 proofs=context(risk_inputs)._prepare_proofs() if phase=='prepared' else None
 armed=[phase=='prepared'];join=risk_module._join
 def ready(*args):
  result=join(*args);armed[0]=True;return result
 monkeypatch.setattr(risk_module,'_join',ready)
 original=module._health_finish
 def replace(*args):
  original(*args)
  if armed[0]:setattr(presence,field,object())
 monkeypatch.setattr(module,'_health_finish',replace)
 try:
  with pytest.raises(RuntimeRefused):
   if proofs is None:context(risk_inputs)
   else:module._verify_proofs(*proofs)
 finally:setattr(presence,field,captured)
