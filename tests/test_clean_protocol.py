"""Protocol pins must agree with committed registration in both owners."""
import copy,hashlib,json
from uuid import uuid4
import pytest
from test_persistence import owned
from test_storage import manager
from test_clean_pair import pair_inputs
from test_environment_manifest import environment
from test_clean_registration import setup
from compertum.clean_pair import build_pair
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import build_protocol,read_protocol


def arguments(pair,lane='source'):
 v=json.loads(pair.content)
 return dict(development_run_id=v[lane]['run_id'],development_sha256='d'*64,data_manifest_sha256=v['data_manifest_sha256'],holdout_manifest_sha256=v['holdout_manifest_sha256'],runtime=v['runtime'],clean_pair={'record':v,'sha256':pair.sha256,'lane':lane})


def test_versioned_protocol_binds_exact_registered_lane(pair_inputs):
 args,_=pair_inputs;pair=build_pair(**args)
 for lane in ('source','wheel'):
  p=build_protocol(**arguments(pair,lane));v=read_protocol(p.content,expected_sha256=p.sha256)
  assert v['schema']=='synthetic-protocol-v2' and v['clean_pair']==arguments(pair,lane)['clean_pair']
  assert len(p.content)<=24*1024 and v['financial_accepted'] is False
  legacy=build_protocol(**{k:v for k,v in arguments(pair,lane).items() if k!='clean_pair'})
  assert json.loads(legacy.content)['schema']=='synthetic-protocol-v1'


@pytest.mark.parametrize('field',['development_run_id','data_manifest_sha256','holdout_manifest_sha256','runtime','lane','pin','extra'])
def test_protocol_cannot_change_registered_pins(pair_inputs,field):
 args,_=pair_inputs;pair=build_pair(**args);kw=arguments(pair)
 if field=='development_run_id':kw[field]=str(uuid4())
 elif field in {'data_manifest_sha256','holdout_manifest_sha256'}:kw[field]='f'*64
 elif field=='runtime':kw[field]['package_sha256']='f'*64
 elif field=='lane':kw['clean_pair']['lane']='wheel'
 elif field=='pin':kw['clean_pair']['sha256']='f'*64
 else:kw['clean_pair']['authority']=True
 with pytest.raises(DataError):build_protocol(**kw)


@pytest.mark.parametrize('fault',['missing_binding','missing_registration','changed_lane','changed_seal','deleted_membership'])
def test_committed_registration_is_required_without_downgrade(owned,pair_inputs,monkeypatch,fault):
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);m.register_pair(runs,pair);kw=arguments(pair)
 p=json.loads(build_protocol(**kw).content);sid=p['clean_pair']['record']['source']['seal_id']
 if fault=='missing_binding':p=json.loads(build_protocol(**{k:v for k,v in kw.items() if k!='clean_pair'}).content)
 elif fault=='missing_registration':
  with runs.store.conn:
   runs.store.conn.execute('DELETE FROM clean_campaign_members');runs.store.conn.execute('DELETE FROM clean_campaign_pairs')
 elif fault=='changed_lane':p['clean_pair']['lane']='wheel'
 elif fault=='changed_seal':sid=str(uuid4())
 else:
  with runs.store.conn:runs.store.conn.execute('DELETE FROM clean_campaign_members')
 with pytest.raises(DataError):m.require_protocol(runs.store.conn,owned[0],p,sid)


def test_evaluation_independently_requires_committed_registration(owned,pair_inputs,monkeypatch):
 import compertum.evaluation_seals as e
 from compertum.persistence import open_store
 from compertum.storage import reserve_runtime_paths
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);reserve_runtime_paths(runs.storage)
 seals=e.EvaluationSeals(open_store(owned[1]['evaluation'],'evaluation'))
 v=json.loads(pair.content);monkeypatch.setattr(e,'runtime_identity',lambda:v['runtime'])
 p=build_protocol(**arguments(pair));sid=v['source']['seal_id']
 e.reserve_seal_append(runs.storage)
 with pytest.raises(DataError):seals.create(sid,p.content,p.sha256)
 assert e.verify_seal_journal(owned[0])['sequence']==0
 m.register_pair(runs,pair)
 assert seals.create(sid,p.content,p.sha256)['development_admitted'] is False
 from compertum.recovery_lineage import validate_sealed_dependencies
 validate_sealed_dependencies(runs.store.conn,owned[0].project_id,e.verify_seal_journal(owned[0]))
 # Exact retry also checks current registration, even after journal CREATE.
 with runs.store.conn:runs.store.conn.execute('DELETE FROM clean_campaign_members')
 with pytest.raises(DataError):seals.create(sid,p.content,p.sha256)
 with pytest.raises(DataError):validate_sealed_dependencies(runs.store.conn,owned[0].project_id,e.verify_seal_journal(owned[0]))


def test_evaluation_cannot_create_legacy_protocol_for_registered_run(owned,pair_inputs,monkeypatch):
 import compertum.evaluation_seals as e
 from compertum.persistence import open_store
 from compertum.storage import reserve_runtime_paths
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);m.register_pair(runs,pair);reserve_runtime_paths(runs.storage)
 seals=e.EvaluationSeals(open_store(owned[1]['evaluation'],'evaluation'));v=json.loads(pair.content)
 monkeypatch.setattr(e,'runtime_identity',lambda:v['runtime']);kw=arguments(pair);kw.pop('clean_pair');p=build_protocol(**kw)
 e.reserve_seal_append(runs.storage)
 with pytest.raises(DataError):seals.create(v['source']['seal_id'],p.content,p.sha256)
 assert e.verify_seal_journal(owned[0])['sequence']==0


@pytest.mark.parametrize('fault',['reserved_seal','run_as_seal','seal_as_run','deleted_rows','dropped_tables','deleted_head'])
def test_registry_loss_and_reserved_identifiers_cannot_create_legacy_seals(owned,pair_inputs,monkeypatch,fault):
 import compertum.evaluation_seals as e
 from compertum.persistence import open_store
 from compertum.storage import reserve_runtime_paths
 m,runs,pair,_=setup(owned,pair_inputs,monkeypatch);m.register_pair(runs,pair);reserve_runtime_paths(runs.storage)
 seals=e.EvaluationSeals(open_store(owned[1]['evaluation'],'evaluation'));v=json.loads(pair.content)
 monkeypatch.setattr(e,'runtime_identity',lambda:v['runtime']);kw=arguments(pair);kw.pop('clean_pair');sid=v['source']['seal_id']
 if fault=='reserved_seal':kw['development_run_id']=str(uuid4())
 elif fault=='run_as_seal':kw['development_run_id']=str(uuid4());sid=v['source']['run_id']
 elif fault=='seal_as_run':kw['development_run_id']=v['source']['seal_id'];sid=str(uuid4())
 else:
  with runs.store.conn:
   if fault=='deleted_rows':
    runs.store.conn.execute('DELETE FROM clean_campaign_members');runs.store.conn.execute('DELETE FROM clean_campaign_pairs')
   elif fault=='dropped_tables':
    runs.store.conn.execute('DROP TABLE clean_campaign_members');runs.store.conn.execute('DROP TABLE clean_campaign_pairs')
   else:runs.store.conn.execute("DELETE FROM state WHERE key='clean_registration_head'")
 p=build_protocol(**kw);e.reserve_seal_append(runs.storage)
 with pytest.raises(DataError):seals.create(sid,p.content,p.sha256)
 assert e.verify_seal_journal(owned[0])['sequence']==0
 if fault in {'deleted_rows','dropped_tables','deleted_head'}:
  with pytest.raises(DataError):m.initialize(runs.store)
