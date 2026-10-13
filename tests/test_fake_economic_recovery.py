"""Bound opening evidence survives independent execution database rollback."""
import json,sqlite3
from copy import deepcopy
from uuid import uuid4
import pytest
from test_fake_economic_opening import opened,declare
from test_execution_authority import authority
from test_execution_health import pair
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.fake_recovery import snapshot_attempts,preserved_attempt_evidence,validate_snapshot_boundary
from compertum.runtime.identity import resolve_project
from compertum.runtime.errors import RuntimeRefused

def test_snapshot_retains_exact_independent_opening_pin(opened):
 store,b=opened;pin=declare(store,b);project=resolve_project(store.root)
 assert snapshot_attempts(store.conn,project.project_id)['opening']==pin
 assert preserved_attempt_evidence(project,verify_attempt_guard(project))

@pytest.mark.parametrize('fault',['mirror','file','missing_file','prior_database'])
def test_preserved_opening_conflict_compromises_recovery(opened,fault):
 store,b=opened;declare(store,b);project=resolve_project(store.root)
 if fault=='file':
  p=store.root/'state/fake-economic-opening.json';p.write_text(p.read_text().replace('5500','5501'))
 elif fault=='missing_file':
  p=store.root/'state/fake-economic-opening.json';p.rename(p.with_name('preserved-opening.json'))
 elif fault=='mirror':
  pin=store.get_state('fake_economic_opening');pin['sha256']='f'*64
  with store.conn:store.conn.execute("UPDATE state SET value=? WHERE key='fake_economic_opening'",(json.dumps(pin),))
 else:
  target=store.root/'state/generations'/str(uuid4())/'execution.sqlite';target.parent.mkdir(parents=True)
  with sqlite3.connect(target) as saved:
   store.conn.backup(saved);pin=store.get_state('fake_economic_opening');pin['sha256']='f'*64
   saved.execute("UPDATE state SET value=? WHERE key='fake_economic_opening'",(json.dumps(pin),))
 assert not preserved_attempt_evidence(project,verify_attempt_guard(project))

def test_missing_manifest_opening_pin_is_not_legacy_when_snapshot_is_bound(opened):
 store,b=opened;pin=declare(store,b);project=resolve_project(store.root);snapshot=snapshot_attempts(store.conn,project.project_id)
 manifest={'fake_attempt_guard':snapshot['head'],'fake_economic_opening':pin}
 validate_snapshot_boundary(snapshot,manifest)
 for mutation in ('missing','wrong'):
  other=deepcopy(manifest)
  if mutation=='missing':del other['fake_economic_opening']
  else:other['fake_economic_opening']['sha256']='f'*64
  with pytest.raises(RuntimeRefused,match='RECOVERY_LINEAGE_MISMATCH'):validate_snapshot_boundary(snapshot,other)


@pytest.mark.parametrize('damage',[False,True])
def test_lineage_readers_close_on_success_and_failure(opened,monkeypatch,damage):
 from compertum import fake_recovery as module
 store,b=opened;declare(store,b);project=resolve_project(store.root)
 if damage:
  with store.conn:store.conn.execute("UPDATE metadata SET value='wrong' WHERE key='role'")
 connections=[];connect=sqlite3.connect
 def tracked(*args,**kwargs):
  conn=connect(*args,**kwargs);connections.append(conn);return conn
 monkeypatch.setattr(module.sqlite3,'connect',tracked)
 try:
  assert preserved_attempt_evidence(project,verify_attempt_guard(project)) is (not damage)
  assert len(connections)>=2
  for conn in connections:
   with pytest.raises(sqlite3.ProgrammingError):conn.execute('SELECT 1')
 finally:
  for conn in connections:conn.close()


def test_opening_change_after_staged_hash_refuses_publication(tmp_path):
 from test_fake_recovery import invoke
 setup=invoke(tmp_path,'prepare_opening')
 result=invoke(tmp_path,'mutate_opening_restore',setup['manifest'])
 assert result=={'refused':'RESTORE_JOURNAL_CHANGED'}
 assert not (tmp_path/'state/active-generation.json').exists()
 assert json.loads((tmp_path/'state/restore-operation.json').read_bytes())['status']=='STAGING_EXECUTION'
 assert (tmp_path/'retained-opening.json').is_file()


@pytest.mark.parametrize('damage',['none','opening','boundary'])
def test_interrupted_restore_requires_retained_opening_boundary(tmp_path,damage):
 from test_fake_recovery import invoke
 setup=invoke(tmp_path,'prepare_opening');invoke(tmp_path,'crash_restore',setup['manifest'],expected_exit=17)
 record_path=tmp_path/'state/restore-operation.json';record=json.loads(record_path.read_bytes())
 assert record['fake_economic_opening']['status']=='VERIFIED'
 if damage=='opening':(tmp_path/'state/fake-economic-opening.json').rename(tmp_path/'retained-opening.json')
 elif damage=='boundary':
  del record['fake_economic_opening'];record_path.write_text(json.dumps(record))
 assert invoke(tmp_path,'recover')['status']==('PUBLISHED' if damage=='none' else 'ABORTED')
