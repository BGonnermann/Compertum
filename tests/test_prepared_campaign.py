"""Prepared campaign transport admits no computation inside the coordinator."""
import hashlib,json
from uuid import uuid4
import pytest
from test_persistence import owned
from test_clean_pair import pair_inputs
from test_environment_manifest import environment
from test_clean_registration import setup
from helpers.saved_campaign_fixture import campaign_folds
from compertum.clean_pair import build_pair,attach_environment
from compertum.modeling.campaign import build_campaign,read_campaign
from compertum.data.encoding import canonical
from compertum.data.errors import DataError


def sha(raw):return hashlib.sha256(raw).hexdigest()

@pytest.fixture
def prepared(owned,pair_inputs,monkeypatch):
 import compertum.development_seals as d
 import compertum.evaluation_seals as e
 import compertum.simulation.runs as r
 from compertum.storage import reserve_runtime_paths
 from compertum.persistence import open_store
 m,runs,initial,args=setup(owned,pair_inputs,monkeypatch);runtime=json.loads(initial.content)['runtime']
 campaign=build_campaign(campaign_folds(),identity=runtime);args={**args,'mathematical_sha256':campaign.sha256};pair=build_pair(**args)
 for module in (d,e,r):monkeypatch.setattr(module,'runtime_identity',lambda:runtime)
 reserve_runtime_paths(runs.storage);seals=e.EvaluationSeals(open_store(owned[1]['evaluation'],'evaluation'))
 raw=attach_environment(campaign.content,pair=pair,manifest=args['source'],lane='source')
 return m,runs,seals,pair,args,campaign,raw


def create(prepared,**changes):
 from compertum.development_seals import create_prepared_campaign
 m,runs,seals,pair,args,campaign,raw=prepared;v=json.loads(pair.content)
 kw=dict(run_id=v['source']['run_id'],raw=raw,expected_sha256=sha(raw),seal_id=v['source']['seal_id'],evaluation=seals);kw.update(changes)
 return create_prepared_campaign(runs,**kw)


def test_prepared_input_registration_status_and_prepare_do_no_numerical_work(prepared,monkeypatch):
 import compertum.modeling.campaign as numerical
 import compertum.environment_manifest as environment_module
 from compertum.evaluation_seals import verify_seal_journal
 m,runs,seals,pair,args,campaign,raw=prepared;m.register_pair(runs,pair);v=json.loads(pair.content);run=v['source']['run_id']
 def forbidden(*a,**k):raise AssertionError('coordinator numerical or payload verification')
 monkeypatch.setattr(numerical,'build_campaign',forbidden);monkeypatch.setattr(environment_module,'verify_environment',forbidden)
 result=create(prepared);assert result['state']=='PAUSED' and result['request_sha256']==sha(raw)
 assert create(prepared)==result and runs.status(run)==result
 assert verify_seal_journal(seals.project)['sequence']==2
 runs.control(run,str(uuid4()),'resume');assert runs.prepare_campaign(run)['unit']==0
 with pytest.raises(DataError,match='CLEAN_NATIVE_EXECUTION_REQUIRED'):runs.step(run)
 with pytest.raises(DataError,match='CLEAN_NATIVE_EXECUTION_REQUIRED'):runs.campaign_scorecard(run)
 assert runs.summary(run)['attempts']==[]


@pytest.mark.parametrize('fault',['unregistered','hash','run','seal','legacy_input','missing_rows'])
def test_prepared_input_refusals_precede_ticket_and_journal(prepared,fault):
 from compertum.evaluation_seals import verify_seal_journal
 m,runs,seals,pair,args,campaign,raw=prepared;kw={}
 if fault!='unregistered':m.register_pair(runs,pair)
 if fault=='hash':kw['expected_sha256']='0'*64
 elif fault=='run':kw['run_id']=str(uuid4())
 elif fault=='seal':kw['seal_id']=str(uuid4())
 elif fault=='legacy_input':kw.update(raw=campaign.content,expected_sha256=campaign.sha256)
 elif fault=='missing_rows':
  with runs.store.conn:runs.store.conn.execute('DELETE FROM clean_campaign_members')
 with pytest.raises(DataError):create(prepared,**kw)
 assert runs.store.conn.execute('SELECT count(*) FROM sealed_campaigns').fetchone()[0]==0
 assert verify_seal_journal(seals.project)['sequence']==0


def test_worker_decodes_same_mathematics_and_still_checks_all_folds(prepared):
 m,runs,seals,pair,args,campaign,raw=prepared
 assert read_campaign(raw,expected_sha256=sha(raw),identity=json.loads(pair.content)['runtime'])==json.loads(campaign.content)
 bad=json.loads(campaign.content);bad['folds'][0]['market_sha256']='0'*64;changed=canonical(bad)
 changedpair=build_pair(**{**args,'mathematical_sha256':sha(changed)})
 wrapped=attach_environment(changed,pair=changedpair,manifest=args['source'],lane='source')
 with pytest.raises(DataError):read_campaign(wrapped,expected_sha256=sha(wrapped),identity=bad['identity'])


@pytest.mark.parametrize('fault',['provider','protected_date','units','trial','extra','budget'])
def test_structural_preparation_refuses_scope_and_contract_changes(prepared,fault):
 from compertum.prepared_campaign import read_prepared
 m,runs,seals,pair,args,campaign,raw=prepared;body=json.loads(campaign.content)
 if fault=='provider':body['folds'][0]['snapshots'][0]['source']['provider']='alpaca'
 elif fault=='protected_date':body['folds'][0]['snapshots'][0]['bars'][0]['session_date']='2024-01-02'
 elif fault=='units':body['units'].pop()
 elif fault=='trial':body['trials'][0]['sha256']='0'*64
 elif fault=='extra':body['unregistered']=True
 else:body['maximum_bytes']=True
 if fault in {'provider','protected_date'}:
  body['fold_pins']=[{'year':f['year'],'sha256':sha(canonical(f))} for f in body['folds']]
  definition={k:body[k] for k in ('features','universe','registered_family','cost_bps','seeds','rng_state','resolved_models','identity','fold_pins','policy','fit_activation')}
  body['trials']=[{'candidate_id':v['candidate_id'],'sha256':sha(canonical({'candidate':v,'definition':definition}))} for v in body['registered_family']]
 changed=canonical(body)
 with pytest.raises(DataError):
  changedpair=build_pair(**{**args,'mathematical_sha256':sha(changed)})
  wrapped=attach_environment(changed,pair=changedpair,manifest=args['source'],lane='source')
  read_prepared(wrapped,expected_sha256=sha(wrapped),identity=body['identity'])


@pytest.mark.parametrize('value',[[],None,1,'x'])
def test_non_object_campaign_input_has_data_error_contract(value):
 raw=canonical(value)
 with pytest.raises(DataError):read_campaign(raw,expected_sha256=sha(raw),identity={})


def test_prepared_input_reader_runs_without_numerical_imports(prepared,tmp_path):
 import subprocess,sys
 from test_campaign_import_boundary import GUARD
 raw=prepared[-1];path=tmp_path/'input.json';path.write_bytes(raw)
 code=GUARD+'''\nfrom pathlib import Path
import hashlib,json
from compertum.prepared_campaign import read_prepared
raw=Path(sys.argv[1]).read_bytes()
body,pair,lane=read_prepared(raw,expected_sha256=hashlib.sha256(raw).hexdigest(),identity=json.loads(raw)['identity'])
assert lane=='source'
'''
 result=subprocess.run([sys.executable,'-B','-c',code,str(path)],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr


@pytest.mark.parametrize('fault',['strip','changed'])
def test_saved_clean_state_cannot_omit_its_launch_expectations(prepared,fault):
 from compertum.development_seals import check_campaign_seal
 m,runs,seals,pair,args,campaign,raw=prepared;m.register_pair(runs,pair);create(prepared)
 state=runs._load(json.loads(pair.content)['source']['run_id'])
 if fault=='strip':state.pop('clean_environment',None)
 else:state['clean_environment']={'unverified':True}
 with pytest.raises(DataError):check_campaign_seal(runs.store,state)


def test_independent_history_accepts_the_bound_clean_state(prepared):
 from compertum.audit_campaign import reconstruct_history
 m,runs,seals,pair,args,campaign,raw=prepared;m.register_pair(runs,pair);create(prepared)
 run=json.loads(pair.content)['source']['run_id'];state=runs._load(run)
 history=[dict(seq=n,body=b,sha256=h) for n,b,h in runs.store.conn.execute('SELECT seq,body,sha256 FROM baseline_history WHERE run_id=? ORDER BY seq',(run,))]
 assert reconstruct_history(canonical(state),history,[])[0]==state


@pytest.mark.parametrize('fault',['strip','lane'])
@pytest.mark.parametrize('reader',['scorecard','aggregate'])
def test_independent_reader_checks_original_envelope_pins_before_math(prepared,monkeypatch,fault,reader):
 from compertum.modeling import campaign_scorecard
 from compertum import audit_campaign as module
 m,runs,seals,pair,args,campaign,raw=prepared;m.register_pair(runs,pair);create(prepared)
 run=json.loads(pair.content)['source']['run_id'];state=runs._load(run)
 if fault=='strip':state.pop('clean_environment')
 else:state['clean_environment']['lane']='wheel'
 # The original input digest remains exact. No completed-campaign claim here;
 # mismatched envelope pins must fail before expensive numerical reconstruction.
 def forbidden(*a,**k):raise AssertionError('numerical reconstruction before original envelope binding')
 monkeypatch.setattr(campaign_scorecard,'read_campaign',forbidden);monkeypatch.setattr(module,'read_campaign',forbidden)
 with pytest.raises(DataError,match='CLEAN_ENVIRONMENT_UNVERIFIED'):
  if reader=='scorecard':campaign_scorecard.build_from_campaign(raw,canonical(state),{},expected_campaign_sha256=sha(raw),expected_identity=state['identity'])
  else:module.audit_campaign(raw,canonical(state),[],[],{},b'{}',expected_campaign_sha256=sha(raw),expected_identity=state['identity'])
