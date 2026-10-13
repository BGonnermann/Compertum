"""Native coordinator preregistration before either lane is created."""
import hashlib,json
from uuid import uuid4
import pytest
from test_persistence import owned
from test_storage import manager
from test_clean_pair import pair_inputs
from test_environment_manifest import environment
from compertum.clean_pair import build_pair,PairRecord
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.runs import SavedRuns
from compertum.persistence import open_store


def setup(owned,pair_inputs,monkeypatch):
 from compertum import clean_registration as m
 args,_=pair_inputs;args={**args,'project_id':owned[0].project_id};pair=build_pair(**args)
 monkeypatch.setattr(m,'runtime_identity',lambda:json.loads(pair.content)['runtime'])
 runs=SavedRuns(manager(owned));m.initialize(runs.store)
 return m,runs,pair,args


def test_pair_registration_is_exact_durable_and_idempotent(owned,pair_inputs,monkeypatch):
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);v=json.loads(pair.content)
 assert m.register_pair(runs,pair)==pair
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_members').fetchone()[0]==4
 assert runs.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0]==0
 assert runs.store.conn.execute('SELECT count(*) FROM sealed_campaigns').fetchone()[0]==0
 assert m.register_pair(runs,pair)==pair
 runs.store.close();store=open_store(owned[1]['coordinator'],'coordinator')
 assert m.read_registration(store.conn,owned[0],v['pair_id'])==pair
 for lane in ('source','wheel'):assert m.member_registration(store.conn,owned[0],v[lane]['run_id'])==(pair,lane)

@pytest.mark.parametrize('lane',['source','wheel'])
@pytest.mark.parametrize('table',['baseline_runs','baseline_history','sealed_campaigns'])
def test_either_existing_lane_prevents_retrospective_registration(owned,pair_inputs,monkeypatch,lane,table):
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);v=json.loads(pair.content);run=v[lane]['run_id']
 with runs.store.conn:
  if table=='baseline_runs':runs.store.conn.execute('INSERT INTO baseline_runs VALUES(?,?)',(run,'{}'))
  elif table=='baseline_history':runs.store.conn.execute('INSERT INTO baseline_history VALUES(?,1,?,?)',(run,'{}','0'*64))
  else:runs.store.conn.execute('INSERT INTO sealed_campaigns VALUES(?,?,?,?,?,NULL)',(run,v[lane]['seal_id'],'{}','0'*64,'{}'))
 with pytest.raises(DataError):m.register_pair(runs,pair)
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_pairs').fetchone()[0]==0


def test_pair_membership_cannot_be_shared_or_rewritten(owned,pair_inputs,monkeypatch):
 m,runs,pair,args=setup(owned,pair_inputs,monkeypatch);m.register_pair(runs,pair)
 other=build_pair(**{**args,'pair_id':str(uuid4())})
 with pytest.raises(DataError):m.register_pair(runs,other)
 changed=build_pair(**{**args,'data_manifest_sha256':'f'*64})
 with pytest.raises(DataError):m.register_pair(runs,changed)
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_pairs').fetchone()[0]==1

@pytest.mark.parametrize('fault',['member_deleted','extra_member','body','hash'])
def test_damaged_registration_fails_closed(owned,pair_inputs,monkeypatch,fault):
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);m.register_pair(runs,pair);pid=json.loads(pair.content)['pair_id']
 with runs.store.conn:
  if fault=='member_deleted':runs.store.conn.execute('DELETE FROM clean_campaign_members WHERE member_id=(SELECT member_id FROM clean_campaign_members LIMIT 1)')
  elif fault=='extra_member':runs.store.conn.execute('INSERT INTO clean_campaign_members VALUES(?,?,?,?)',(str(uuid4()),pid,'source','run_id'))
  elif fault=='body':runs.store.conn.execute("UPDATE clean_campaign_pairs SET body='{}'")
  else:runs.store.conn.execute('UPDATE clean_campaign_pairs SET sha256=?',('0'*64,))
 with pytest.raises(DataError):m.read_registration(runs.store.conn,owned[0],pid)
 with pytest.raises(DataError):m.member_registration(runs.store.conn,owned[0],str(uuid4()))


def test_wrong_project_and_runtime_are_refused(owned,pair_inputs,monkeypatch):
 m,runs,pair,args=setup(owned,pair_inputs,monkeypatch)
 with pytest.raises(DataError):m.register_pair(runs,build_pair(**{**args,'project_id':'f'*64}))
 monkeypatch.setattr(m,'runtime_identity',lambda:{})
 with pytest.raises(DataError):m.register_pair(runs,pair)


def test_registration_count_cannot_exceed_bound(owned,pair_inputs,monkeypatch):
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);monkeypatch.setattr(m,'MAX_PAIRS',0)
 with pytest.raises(DataError):m.register_pair(runs,pair)
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_pairs').fetchone()[0]==0


def test_membership_insert_abort_rolls_back_entire_registration(owned,pair_inputs,monkeypatch):
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch)
 with runs.store.conn:runs.store.conn.execute("CREATE TRIGGER reject_second BEFORE INSERT ON clean_campaign_members WHEN (SELECT count(*) FROM clean_campaign_members)=1 BEGIN SELECT RAISE(ABORT,'fixture interruption'); END")
 with pytest.raises(DataError):m.register_pair(runs,pair)
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_pairs').fetchone()[0]==0
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_members').fetchone()[0]==0
 with runs.store.conn:runs.store.conn.execute('DROP TRIGGER reject_second')
 assert m.register_pair(runs,pair)==pair


@pytest.mark.parametrize('conflict',['run_id','seal_id'])
def test_journal_only_seal_prevents_retrospective_registration(owned,pair_inputs,monkeypatch,conflict):
 from compertum.evaluation_seals import EvaluationSeals,reserve_seal_append
 from compertum.evaluation_protocol import build_protocol
 from compertum.runtime.identity_pins import runtime_identity
 from compertum.storage import reserve_runtime_paths
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);v=json.loads(pair.content)
 reserve_runtime_paths(runs.storage);seals=EvaluationSeals(open_store(owned[1]['evaluation'],'evaluation'))
 run=v['source']['run_id'] if conflict=='run_id' else str(uuid4())
 seal=v['source']['seal_id'] if conflict=='seal_id' else str(uuid4())
 p=build_protocol(development_run_id=run,development_sha256='a'*64,data_manifest_sha256='b'*64,holdout_manifest_sha256='c'*64,runtime=runtime_identity())
 reserve_seal_append(runs.storage);seals.create(seal,p.content,p.sha256)
 assert runs.store.conn.execute('SELECT count(*) FROM sealed_campaigns').fetchone()[0]==0
 with pytest.raises(DataError):m.register_pair(runs,pair)
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_pairs').fetchone()[0]==0


def test_actual_pair_bound_accepts_32_then_refuses_33(owned,pair_inputs,monkeypatch):
 m,runs,_,args=setup(owned,pair_inputs,monkeypatch)
 def fresh():return build_pair(**{**args,**{k:str(uuid4()) for k in ('pair_id','source_run_id','source_seal_id','wheel_run_id','wheel_seal_id')}})
 for _ in range(32):m.register_pair(runs,fresh())
 with pytest.raises(DataError):m.register_pair(runs,fresh())
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_pairs').fetchone()[0]==32
 assert runs.store.conn.execute('SELECT count(*) FROM clean_campaign_members').fetchone()[0]==128


@pytest.mark.parametrize('table,column',[('clean_campaign_pairs','body'),('clean_campaign_pairs','pair_id'),('clean_campaign_members','lane')])
def test_oversized_sqlite_text_is_not_materialized(owned,pair_inputs,monkeypatch,table,column):
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);m.register_pair(runs,pair);pid=json.loads(pair.content)['pair_id']
 with runs.store.conn:runs.store.conn.execute('UPDATE '+table+' SET '+column+'=?',('x'*(m.MAX_PAIR_BYTES+1),))
 class Cursor:
  def __init__(self,cursor):self.cursor=cursor
  def fetchall(self):
   rows=self.cursor.fetchall()
   assert all(type(cell) is not str or len(cell)<=m.MAX_PAIR_BYTES for row in rows for cell in row),'unbounded SQLite text materialized'
   return rows
 class DB:
  def execute(self,*a):return Cursor(runs.store.conn.execute(*a))
 with pytest.raises(DataError):m.read_registration(DB(),owned[0],pid)
