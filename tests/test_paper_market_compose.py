"""Private same-plan composition; native local invented data only."""
from uuid import uuid4,UUID
import json,pickle
import pytest
from compertum.data.encoding import canonical
from compertum.paper_market_inputs import prepare_market_plan
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import acquire_owner,release_owner,_LEASES
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_market_evidence import protect_market_evidence,publish_market_evidence,open_market_evidence,_OpenedMarketEvidence
from compertum.runtime.paper_market_compose import compose_market_inputs
from test_winhttp_get import owner
from test_paper_market_qualification import credentials
from test_persistence import owned
from test_storage import manager
import test_paper_market_collection as f
import test_paper_market_fresh as g


def history(e,credential,*,missing=False,padding=False):
 pp=f.plan(e).to_payload();rows=[dict(t=t,o=100,h=102,l=99,c=100.125,v=20000) for t in pp['daily_labels']]
 if missing:rows=rows[:-1]
 n=8 if padding else 3;bodies=[]
 for i in range(n):
  span=32 if padding else 100
  b=json.loads(f.body('HISTORY',str(i+1) if i<n-1 else None,rows[i*span:(i+1)*span]))
  if padding:b['unknown_padding']='\\"'*14000
  bodies.append(canonical(b))
 with f.pages(bodies) as (port,_):c=f.collection(e,credential,port);f.run(c)
 assert c.status()['state']=='PAGINATION_COMPLETE'
 return c


def fresh(e,credential,*,plan=None,padding=False):
 from test_winhttp_get import warm_budget
 warm_budget(e)
 bodies=[g.asset(),g.quote()]
 if padding:
  bodies=[canonical(dict(json.loads(raw),unknown_padding='\\"'*14000)) for raw in bodies]
 clock=f.Clock();clock.at=g.AT
 with f.pages(bodies) as (port,_):
  p=g._MarketFresh(e,plan or f.plan(e),credential,pair_id=f.CID,_test_port=port,_test_clock=clock.now,_test_monotonic=clock.monotonic);g.run(p)
 assert p.status()['state']=='PAIR_COMPLETE'
 return p,clock


def test_live_composition_uses_original_math_and_keeps_all_authority_false(owner,credentials):
 c=history(owner,credentials);p,clock=fresh(owner,credentials);original=c.private_snapshot().content
 v=compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot());out=v.to_payload();d=out['diagnostic']
 assert d['observed_conditions_met'] and d['history']['observed_sessions']==252 and d['history']['mean_dollar_volume']=='2002500'
 assert d['quote']['bid']=='100.125' and d['history']['intent_notional_cap']=='2000'
 assert d['status']=='BLOCKED' and {'FEED_ENTITLEMENT_UNVERIFIED','ACTION_HALT_COVERAGE_UNVERIFIED','OWNERSHIP_RECONCILIATION_UNVERIFIED'}<=set(d['deficiencies'])
 assert all(out[k] is False for k in ('financial_accepted','transport_authorized','research_eligible'))
 assert c.private_snapshot().content==original and 'body_utf8' not in json.dumps(out) and len(v.content)<=131072
 assert out['history']['provenance']=='LIVE_OWNER_ASSERTION' and out['fresh']['provenance']==['LOOPBACK_FIXTURE','LOOPBACK_FIXTURE']
 assert f.KEY not in repr(v)
 with pytest.raises(RuntimeRefused):pickle.dumps(v)


def test_missing_history_session_is_not_filled_by_current_quote(owner,credentials):
 c=history(owner,credentials,missing=True);p,_=fresh(owner,credentials)
 d=compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot()).to_payload()['diagnostic']
 assert not d['observed_conditions_met'] and not d['history']['complete'] and 'HISTORY_ROWS_MISSING' in d['deficiencies']


def test_published_history_preserves_math_and_historical_labels(owned):
 _,leases=owned;e=leases['execution'];m=manager(owned);credential=seal_paper_credentials(e,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))
 c=history(e,credential);p,_=fresh(e,credential);v=compose_market_inputs(e,c.private_snapshot(),p.private_snapshot());live=v.to_payload();v.close()
 protected=protect_market_evidence(e,c.private_snapshot(),task_id=str(uuid4()));grant=m.reserve_bytes(protected.task_id,'records',len(protected.ciphertext));receipt=publish_market_evidence(m,grant,protected);c.close()
 with open_market_evidence(e,'paper-primary',protected.collection_id,receipt) as opened:
  out=compose_market_inputs(e,opened,p.private_snapshot()).to_payload()
  assert out['diagnostic']==live['diagnostic']
  assert out['history']['provenance']=='HISTORICAL_PRODUCER_ASSERTION' and out['history']['freshness']=='NOT_RESTORED'
  assert not out['transport_authorized']


def test_reopened_prior_generation_does_not_restore_authority(tmp_path):
 import os,subprocess
 from compertum.runtime.identity import resolve_project
 from compertum.runtime.paper_credential_slot import load_paper_slot
 from test_fixture_processes import fixture_module
 code="""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('tests').resolve()))
from uuid import uuid4
import test_paper_market_compose as f
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_credential_slot import provision_paper_slot
from compertum.runtime.paper_market_evidence import protect_market_evidence,publish_market_evidence
from compertum.config import load_config
from compertum.storage import StorageManager,reserve_runtime_paths
root=Path(sys.argv[1]);project=resolve_project(root);c=acquire_owner(project,'coordinator');e=acquire_owner(project,'execution')
try:
 config=root/'config.toml';config.write_bytes(Path('config/default.toml').read_bytes());m=StorageManager(c,load_config(config,root));reserve_runtime_paths(m)
 credential=seal_paper_credentials(e,'paper-primary',bytearray(f.f.KEY.encode()),bytearray(f.f.SECRET.encode()));provision_paper_slot(e,credential)
 collection=f.history(e,credential);sealed=protect_market_evidence(e,collection.private_snapshot(),task_id=str(uuid4()))
 grant=m.reserve_bytes(sealed.task_id,'records',len(sealed.ciphertext));r=publish_market_evidence(m,grant,sealed)
 print(json.dumps(dict(collection_id=sealed.collection_id,manifest=r,producer_generation=e.generation)))
finally:release_owner(e);release_owner(c)
"""
 child=fixture_module().python_process(['-B','-c',code,str(tmp_path)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:out,err=child.communicate(timeout=20)
 except subprocess.TimeoutExpired:child.kill();child.communicate();raise
 assert child.returncode==0,err
 assert all(k not in out for k in (f.KEY,f.SECRET))
 result=json.loads(out);e=acquire_owner(resolve_project(tmp_path),'execution')
 try:
  credential=load_paper_slot(e,'paper-primary');p,_=fresh(e,credential)
  with open_market_evidence(e,'paper-primary',result['collection_id'],result['manifest']) as opened:
   value=compose_market_inputs(e,opened,p.private_snapshot()).to_payload()
   assert value['history']['producer_generation']==result['producer_generation']==1 and value['execution_generation']==e.generation==2
   assert not value['transport_authorized'] and not value['financial_accepted']
 finally:release_owner(e)


@pytest.mark.parametrize('fault',['plan','credential','dict','unregistered'])
def test_mismatched_or_forged_sources_refused(owner,credentials,fault):
 c=history(owner,credentials);credential=credentials;plan=None
 if fault=='plan':plan=prepare_market_plan(project_id=owner.project_id,account_alias='paper-primary',symbol='AAPL',session_date='2026-10-09',created_at='2026-10-09T13:19:00Z')
 elif fault=='credential':credential=seal_paper_credentials(owner,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))
 p,_=fresh(owner,credential,plan=plan);source=c.private_snapshot()
 if fault=='dict':source=source.to_payload()
 elif fault=='unregistered':source=_OpenedMarketEvidence(owner,bytearray(),b'',(),_LEASES[owner])
 with pytest.raises(RuntimeRefused):compose_market_inputs(owner,source,p.private_snapshot())


@pytest.mark.parametrize('mode',['CURRENT_ACTIONS','INCOMPLETE'])
def test_nonfrozen_history_never_becomes_combined_input(owner,credentials,mode):
 with f.pages([f.body('CURRENT_ACTIONS')]) as (port,_):
  c=f.collection(owner,credentials,port,'CURRENT_ACTIONS' if mode=='CURRENT_ACTIONS' else 'HISTORY')
  if mode=='INCOMPLETE':c.cancel()
  else:f.run(c)
 p,_=fresh(owner,credentials)
 with pytest.raises(RuntimeRefused):compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot())


@pytest.mark.parametrize('late',[False,True])
def test_validation_cutoff_exact_nanosecond(owner,credentials,monkeypatch,late):
 import compertum.runtime.paper_market_collection as module
 clock=f.Clock();clock.at='2026-10-09T13:24:59Z';original=module.qualify_market_inputs
 def validate(*a,**kw):
  v=original(*a,**kw);clock.at='2026-10-09T13:25:00.000000001Z' if late else '2026-10-09T13:25:00Z';return v
 with monkeypatch.context() as patch:
  patch.setattr(module,'qualify_market_inputs',validate)
  with f.pages([f.body('HISTORY')]) as (port,_):c=f.collection(owner,credentials,port,clock=clock);f.run(c)
 p,_=fresh(owner,credentials)
 if late:
  with pytest.raises(RuntimeRefused):compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot())
 else:assert 'HISTORY_ROWS_MISSING' in compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot()).to_payload()['diagnostic']['deficiencies']


@pytest.mark.parametrize('target',['history','fresh','owner','combined'])
def test_source_or_owner_close_revokes_composition(owner,credentials,target):
 c=history(owner,credentials);p,_=fresh(owner,credentials);v=compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot())
 {'history':c.close,'fresh':p.close,'owner':lambda:release_owner(owner),'combined':v.close}[target]()
 with pytest.raises(RuntimeRefused):v.to_payload()


def test_current_age_recomputed_without_revising_frozen_history(owner,credentials):
 c=history(owner,credentials);p,clock=fresh(owner,credentials);v=compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot());before=c.private_snapshot().content
 clock.at='2026-10-09T13:35:30Z';clock.mono=30;assert v.to_payload()['diagnostic']['quote']['valid']
 clock.at='2026-10-09T13:35:30.000000001Z';clock.mono=30.000000001;assert not v.to_payload()['diagnostic']['quote']['valid']
 assert c.private_snapshot().content==before


@pytest.mark.parametrize('stage',['calculation','scan'])
@pytest.mark.parametrize('target',['history','fresh'])
def test_mutation_during_composition_refused(owner,credentials,monkeypatch,stage,target):
 import compertum.runtime.paper_market_compose as module
 c=history(owner,credentials);p,_=fresh(owner,credentials);v=compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot())
 name='qualify_market_inputs' if stage=='calculation' else '_scan_generated';original=getattr(module,name)
 def mutate(*a,**kw):
  result=original(*a,**kw);(c if target=='history' else p)._records.clear();return result
 monkeypatch.setattr(module,name,mutate)
 with pytest.raises(RuntimeRefused):v.to_payload()


def test_only_one_composition_is_retained_per_owner(owner,credentials):
 c=history(owner,credentials);p,_=fresh(owner,credentials);h=c.private_snapshot();q=p.private_snapshot();v=compose_market_inputs(owner,h,q)
 with pytest.raises(RuntimeRefused):compose_market_inputs(owner,h,q)
 v.close();assert compose_market_inputs(owner,h,q).to_payload()['diagnostic']['observed_conditions_met']


def test_generated_composition_secret_never_exposed(owner):
 credential=seal_paper_credentials(owner,'paper-primary',bytearray(b'PrivateCombinedMarketInputs'),bytearray(f.SECRET.encode()))
 c=history(owner,credential);p,_=fresh(owner,credential)
 with pytest.raises(RuntimeRefused):compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot()).to_payload()


def test_cross_source_duplicate_request_id_refused(owner,credentials,monkeypatch):
 import compertum.runtime.paper_market_collection as hm
 import compertum.runtime.paper_market_fresh as qm
 ids=iter([1,3,4]);monkeypatch.setattr(hm,'uuid4',lambda:UUID(int=next(ids)));c=history(owner,credentials)
 ids2=iter([1,2]);monkeypatch.setattr(qm,'uuid4',lambda:UUID(int=next(ids2)));p,_=fresh(owner,credentials)
 with pytest.raises(RuntimeRefused):compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot()).to_payload()


def test_combined_original_envelope_limit_is_unchanged(owner,credentials):
 c=history(owner,credentials,padding=True);p,_=fresh(owner,credentials,padding=True)
 assert c.status()['state']=='PAGINATION_COMPLETE' and p.status()['state']=='PAIR_COMPLETE'
 with pytest.raises(RuntimeRefused):compose_market_inputs(owner,c.private_snapshot(),p.private_snapshot()).to_payload()


def test_review_forged_live_source_cannot_revive_closed_history(owner,credentials):
 from types import SimpleNamespace
 from hashlib import sha256
 c=history(owner,credentials);snapshot=c.private_snapshot();raw=snapshot.content;value=json.loads(raw);p,_=fresh(owner,credentials)
 c.close()
 fake=SimpleNamespace(_lease=owner,_context=lambda:None,_snapshot=snapshot,_wire_records=lambda:value['records'],
  _state=value['state'],_complete_by_cutoff=True,_validated_at=value['validated_at'],_plan=f.plan(owner),
  _protected=credentials,_collection_id=value['collection_id'],_generation=owner.generation,_credential_sha=sha256(credentials.ciphertext).hexdigest())
 fake.private_snapshot=lambda:snapshot
 object.__setattr__(snapshot,'_collection',fake);object.__setattr__(snapshot,'_content',raw)
 with pytest.raises(RuntimeRefused):compose_market_inputs(owner,snapshot,p.private_snapshot())


def test_review_live_summary_cannot_upgrade_fixture_provenance(owner,credentials):
 from hashlib import sha256
 c=history(owner,credentials);snapshot=c.private_snapshot();value=snapshot.to_payload();p,_=fresh(owner,credentials)
 value['native_provenance']='DATA_TLS';value['clock_basis']='LOCAL_CLOCK';raw=canonical(value)
 object.__setattr__(snapshot,'_content',raw);object.__setattr__(snapshot,'_sha256',sha256(raw).hexdigest())
 with pytest.raises(RuntimeRefused):compose_market_inputs(owner,snapshot,p.private_snapshot())
