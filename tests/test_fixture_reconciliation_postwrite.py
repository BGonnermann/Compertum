"""A real file changes during SQL. Native source identity is explicitly simulated."""
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.identity import resolve_project
from test_fixture_order_reconciliation_context import observed,dispatch_inputs,owner,original_owner,risk_inputs,account,confirmed,inputs,history,completed,pair,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,simulated_source,reconcile

def test_source_change_during_accounting_rolls_back_and_preserves_changed_file(observed,monkeypatch,tmp_path):
 o,intent,component,root,module=observed
 raw,file_id=module._reserved_source_file();path=tmp_path/'original-order-source.jsonl';path.write_bytes(raw)
 monkeypatch.setattr(module,'_reserved_source_file',lambda *args:(path.read_bytes(),file_id))
 def change():path.write_bytes(raw+b' ');return 1
 o.a.db.create_function('change_original_source',0,change)
 with o.a.db:
  o.a.db.execute("CREATE TRIGGER source_changes_after_observation AFTER INSERT ON state WHEN new.key LIKE 'native_fixture_source:%' BEGIN SELECT change_original_source(); END")
 before=verify_attempt_guard(resolve_project(o.a.store.root))
 with pytest.raises(RuntimeRefused):reconcile(observed)
 assert path.read_bytes()==raw+b' '
 assert o.a.db.execute("SELECT value FROM state WHERE key='native_fixture_source:fixture'").fetchone() is None
 assert verify_attempt_guard(resolve_project(o.a.store.root))==before
