"""Real SQLite records; inert grants carry no native request authority."""
import importlib,sqlite3
from copy import deepcopy
from uuid import uuid4
import pytest
from test_paper_market_grants import values,PROJECT
from compertum.runtime.paper_market_grants import build_grant,initial_record
from compertum.runtime.errors import RuntimeRefused
from compertum.data.encoding import canonical


@pytest.fixture
def records(tmp_path):
 module=importlib.import_module('compertum.runtime.paper_market_records')
 db=sqlite3.connect(tmp_path/'market.sqlite');db.execute('CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
 try:yield module.MarketRecords(db,PROJECT),db,module
 finally:db.close()


def record():
 return initial_record(build_grant(**dict(values(),job_id=str(uuid4()),task_id=str(uuid4()),reservation_id=str(uuid4()))))


def test_records_survive_reopen_with_immutable_identity_and_no_authority(records):
 r,db,module=records;v=record()
 with db:r.write(v,new=True)
 assert r.read(v['grant']['job_id'])==v
 restarted=module.MarketRecords(db,PROJECT)
 assert restarted.read(v['grant']['job_id'])==v
 assert len(r.all())==1


def test_restart_interrupts_unfinished_records_without_rewriting_grants(records):
 r,db,module=records;items=[]
 for state in ('PREPARED','GRANTED','RUNNING','EVIDENCE_READY','COMPLETE','CANCELED','ABORTED'):
  v=record();v.update(state=state,consumed=state not in {'PREPARED','GRANTED'})
  if state=='COMPLETE':continue # FRESH completion is covered separately by the grant contract.
  if state=='EVIDENCE_READY':v.update(summary=dict(state='INCOMPLETE',reason='CANCELLED',attempts=0,responses=0),evidence=dict(size_bytes=128,sha256='e'*64))
  with db:r.write(v,new=True)
  items.append(deepcopy(v))
 r.interrupt_unfinished()
 for v in items:
  after=r.read(v['grant']['job_id'])
  assert after['grant']==v['grant'] and after['consumed']==v['consumed'] and after['evidence']==v['evidence']
  assert after['state']==('INTERRUPTED' if v['state'] in {'PREPARED','GRANTED','RUNNING','EVIDENCE_READY'} else v['state'])


def test_record_limit_is_transactional_and_does_not_evict_history(records):
 r,db,module=records
 for _ in range(32):
  with db:r.write(record(),new=True)
 with pytest.raises(RuntimeRefused,match='MARKET_HISTORY_BOUND'),db:r.write(record(),new=True)
 assert len(r.all())==32


@pytest.mark.parametrize('field',['task_id','reservation_id'])
def test_record_storage_identities_cannot_be_reused(records,field):
 r,db,module=records;v=record()
 with db:r.write(v,new=True)
 kwargs=dict(values(),job_id=str(uuid4()),task_id=str(uuid4()),reservation_id=str(uuid4()))
 kwargs[field]=v['grant'][field];other=initial_record(build_grant(**kwargs))
 with pytest.raises(RuntimeRefused,match='MARKET_STORAGE_REUSED'),db:r.write(other,new=True)
 assert len(r.all())==1


def test_existing_immutable_grant_cannot_be_replaced_even_with_recomputed_hash(records):
 r,db,module=records;v=record()
 with db:r.write(v,new=True)
 kwargs=dict(values(),job_id=v['grant']['job_id'],task_id=v['grant']['task_id'],reservation_id=v['grant']['reservation_id'],subject_key='f'*64)
 changed=initial_record(build_grant(**kwargs))
 with pytest.raises(RuntimeRefused,match='MARKET_WRITE_UNVERIFIED'),db:r.write(changed)
 assert r.read(v['grant']['job_id'])==v


def test_ignored_record_write_is_detected(records):
 r,db,module=records;v=record()
 with db:r.write(v,new=True)
 db.execute("CREATE TRIGGER deny_market BEFORE UPDATE ON state BEGIN SELECT RAISE(IGNORE); END")
 v['state']='GRANTED'
 with pytest.raises(RuntimeRefused,match='MARKET_WRITE_UNVERIFIED'),db:r.write(v)
 assert r.read(v['grant']['job_id'])['state']=='PREPARED'


@pytest.mark.parametrize('change',['oversize','invalid_json','other_project','wrong_key','unknown_version','missing_version'])
def test_corrupt_or_foreign_persisted_state_refuses_reopen(records,change):
 r,db,module=records;v=record();key='paper_market_job:'+v['grant']['job_id']
 with db:r.write(v,new=True)
 if change=='oversize':db.execute('UPDATE state SET value=? WHERE key=?',('x'*32769,key))
 elif change=='invalid_json':db.execute('UPDATE state SET value=? WHERE key=?',('{',key))
 elif change=='other_project':
  kwargs=values();kwargs.update(job_id=v['grant']['job_id'],project_id='f'*64)
  from compertum.paper_market_inputs import prepare_market_plan
  kwargs['plan']=prepare_market_plan(project_id='f'*64,account_alias='fixture',symbol='MSFT',session_date='2023-11-24',created_at='2023-11-24T14:00:00+00:00')
  db.execute('UPDATE state SET value=? WHERE key=?',(canonical(initial_record(build_grant(**kwargs))).decode(),key))
 elif change=='wrong_key':db.execute('UPDATE state SET key=? WHERE key=?',('paper_market_job:'+str(uuid4()),key))
 elif change=='unknown_version':db.execute("UPDATE state SET value='2' WHERE key='paper_market_owner_version'")
 else:db.execute("DELETE FROM state WHERE key='paper_market_owner_version'")
 db.commit()
 with pytest.raises(RuntimeRefused):module.MarketRecords(db,PROJECT)


def test_unrelated_account_state_is_unchanged(records):
 r,db,module=records
 with db:db.execute("INSERT INTO state VALUES('paper_read_owner_version','1')")
 before=db.execute("SELECT value FROM state WHERE key='paper_read_owner_version'").fetchone()
 with db:r.write(record(),new=True)
 r.interrupt_unfinished()
 assert db.execute("SELECT value FROM state WHERE key='paper_read_owner_version'").fetchone()==before


def published_record():
 v=record();g=v['grant']
 v.update(state='PUBLISHED',consumed=True,summary=dict(state='PAGINATION_COMPLETE',reason=None,attempts=1,responses=1),
          evidence=dict(size_bytes=128,sha256='e'*64),manifest=dict(artifact_id=str(uuid4()),task_id=g['task_id'],
          path=f'artifacts/runs/{g["task_id"]}/market-collection-{g["job_id"]}.bin',size_bytes=128,sha256='e'*64))
 return v


@pytest.mark.parametrize('change',['consumed','publication','evidence','terminal'])
def test_stale_record_cannot_erase_irreversible_progress(records,change):
 r,db,module=records;v=published_record() if change in {'publication','evidence'} else record()
 if change=='consumed':v.update(state='RUNNING',consumed=True)
 if change=='terminal':v.update(state='CANCELED',reason='OPERATOR_CANCELED')
 with db:r.write(v,new=True)
 stale=deepcopy(v)
 if change=='consumed':stale.update(state='PREPARED',consumed=False)
 elif change=='terminal':stale.update(state='GRANTED',reason=None)
 else:stale.update(state='RUNNING',manifest=None,evidence=None if change=='evidence' else stale['evidence'])
 with pytest.raises(RuntimeRefused),db:r.write(stale)
 assert r.read(v['grant']['job_id'])==v


@pytest.mark.parametrize('change',['deleted','changed','ignored_lock'])
@pytest.mark.parametrize('operation',['read','write'])
def test_live_schema_marker_is_required(records,change,operation):
 r,db,module=records;v=record()
 with db:r.write(v,new=True)
 if change=='deleted':db.execute("DELETE FROM state WHERE key='paper_market_owner_version'")
 elif change=='changed':db.execute("UPDATE state SET value='2' WHERE key='paper_market_owner_version'")
 else:db.execute("CREATE TRIGGER deny_market_lock BEFORE UPDATE ON state WHEN NEW.key='paper_market_owner_version' BEGIN SELECT RAISE(IGNORE); END")
 db.commit()
 if change=='ignored_lock' and operation=='read':assert r.read(v['grant']['job_id'])==v;return
 with pytest.raises(RuntimeRefused):
  if operation=='read':r.read(v['grant']['job_id'])
  else:
   with db:r.write(record(),new=True)


def test_restart_preserves_publication_and_interrupts_fresh_complete(records):
 from test_paper_market_grants import fresh_values
 r,db,module=records;published=published_record()
 fresh=initial_record(build_grant(**fresh_values()));fresh.update(state='COMPLETE',consumed=True,summary=dict(state='PAIR_COMPLETE',reason=None,attempts=2,responses=2))
 with db:r.write(published,new=True);r.write(fresh,new=True)
 r.interrupt_unfinished()
 assert r.read(published['grant']['job_id'])==published
 after=r.read(fresh['grant']['job_id'])
 assert after['state']=='INTERRUPTED' and after['consumed'] and after['grant']==fresh['grant'] and after['summary']==fresh['summary']


def test_ignored_restart_update_rolls_back_entire_interruption(records):
 r,db,module=records;items=sorted([record(),record()],key=lambda v:v['grant']['job_id'])
 with db:
  for v in items:r.write(v,new=True)
 key='paper_market_job:'+items[1]['grant']['job_id']
 db.execute("CREATE TRIGGER deny_one_restart BEFORE UPDATE ON state WHEN NEW.key='"+key+"' BEGIN SELECT RAISE(IGNORE); END")
 with pytest.raises(RuntimeRefused,match='MARKET_WRITE_UNVERIFIED'):r.interrupt_unfinished()
 assert r.all()==items
