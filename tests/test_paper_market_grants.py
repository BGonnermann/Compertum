"""Inert market-grant contracts; no credentials, owner or transport authority."""
import importlib
from copy import deepcopy
import pytest
from compertum.data.encoding import canonical
from compertum.paper_market_inputs import prepare_market_plan
from compertum.runtime.errors import RuntimeRefused

PROJECT='a'*64
JOB='11111111-1111-4111-8111-111111111111'
TASK='22222222-2222-4222-8222-222222222222'
RESERVATION='33333333-3333-4333-8333-333333333333'
INSTANCE='44444444-4444-4444-8444-444444444444'


def values():
 plan=prepare_market_plan(project_id=PROJECT,account_alias='fixture',symbol='MSFT',
                          session_date='2023-11-24',created_at='2023-11-24T14:00:00+00:00')
 return dict(job_id=JOB,task_id=TASK,reservation_id=RESERVATION,project_id=PROJECT,
             owner_instance=INSTANCE,owner_generation=1,subject_key='b'*64,
             credential_sha256='c'*64,mode='HISTORY',plan=plan,history=None,
             created_at='2023-11-24T14:00:00+00:00',prepared_mono=100.)


def test_complete_grant_binds_identity_plan_mode_and_fixed_routes():
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 inputs=values();grant=module.build_grant(**inputs);p=grant.to_payload()
 assert p['job_id']==JOB and p['task_id']==TASK and p['reservation_id']==RESERVATION
 assert p['owner_instance']==INSTANCE and p['owner_generation']==1 and p['subject_key']=='b'*64
 assert p['credential_sha256']=='c'*64 and p['mode']=='HISTORY' and p['history'] is None
 assert canonical(p['plan'])==inputs['plan'].content and p['plan_sha256']==inputs['plan'].sha256
 assert p['start_expires_at']=='2023-11-24T14:01:00+00:00'
 assert p['routes']==[dict(operation='HISTORY',origin='https://data.alpaca.markets',method='GET',path='/v2/stocks/bars')]
 assert p['transport_authorized'] is False and p['financial_accepted'] is False
 assert module.MarketGrant(grant.content).sha256==grant.sha256
 record=module.initial_record(grant)
 assert record['state']=='PREPARED' and record['consumed'] is False and record['grant_sha256']==grant.sha256
 assert module.validate_record(record)==record


def history_reference():
 job='55555555-5555-4555-8555-555555555555';task='66666666-6666-4666-8666-666666666666'
 return dict(job_id=job,task_id=task,grant_sha256='d'*64,
             manifest=dict(artifact_id='77777777-7777-4777-8777-777777777777',task_id=task,
                           path=f'artifacts/runs/{task}/market-collection-{job}.bin',size_bytes=128,sha256='e'*64))


def fresh_values():
 return dict(values(),mode='FRESH',reservation_id=None,history=history_reference(),
             created_at='2023-11-24T14:30:00+00:00',prepared_mono=1900.)


def test_fresh_has_own_lifetime_around_unchanged_published_history_plan():
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 inputs=fresh_values();grant=module.build_grant(**inputs);p=grant.to_payload()
 assert p['plan']==inputs['plan'].to_payload() and p['history']==inputs['history']
 assert p['created_at']=='2023-11-24T14:30:00+00:00' and p['start_expires_at']=='2023-11-24T14:31:00+00:00'
 assert p['reservation_id'] is None
 assert p['routes']==[dict(operation='ASSET',origin='https://paper-api.alpaca.markets',method='GET',path='/v2/assets/MSFT'),
                      dict(operation='QUOTE',origin='https://data.alpaca.markets',method='GET',path='/v2/stocks/quotes/latest')]
 inputs['history']['manifest']['sha256']='f'*64
 assert grant.to_payload()['history']['manifest']['sha256']=='e'*64


def test_current_actions_has_only_its_fixed_data_route():
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 p=module.build_grant(**dict(values(),mode='CURRENT_ACTIONS')).to_payload()
 assert p['routes']==[dict(operation='CURRENT_ACTIONS',origin='https://data.alpaca.markets',method='GET',path='/v1/corporate-actions')]


@pytest.mark.parametrize('field',['job_id','task_id','reservation_id','owner_instance','owner_generation','subject_key','credential_sha256','prepared_mono','created_at'])
def test_record_binding_detects_grant_substitution(field):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**values()))
 record['grant'][field]=dict(job_id=TASK,task_id=JOB,reservation_id=INSTANCE,owner_instance=RESERVATION,
                            owner_generation=2,subject_key='f'*64,credential_sha256='f'*64,
                            prepared_mono=101.,created_at='2023-11-24T14:00:01+00:00')[field]
 with pytest.raises(RuntimeRefused):module.validate_record(record)


@pytest.mark.parametrize('change',['unknown','purpose','version_bool','origin','method','path','expiry','plan_hash','authority','financial','project','history','reservation'])
def test_canonical_grant_rejects_invalid_contract(change):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 p=module.build_grant(**values()).to_payload()
 if change=='unknown':p['priority']=0
 elif change=='purpose':p['purpose']='ACCOUNT_READ_GRANT'
 elif change=='version_bool':p['version']=True
 elif change=='origin':p['routes'][0]['origin']='https://api.alpaca.markets'
 elif change=='method':p['routes'][0]['method']='POST'
 elif change=='path':p['routes'][0]['path']='/v2/account'
 elif change=='expiry':p['start_expires_at']='2023-11-24T14:01:01+00:00'
 elif change=='plan_hash':p['plan_sha256']='f'*64
 elif change=='authority':p['transport_authorized']=True
 elif change=='financial':p['financial_accepted']=True
 elif change=='project':p['project_id']='f'*64
 elif change=='history':p['history']=history_reference()
 else:p['reservation_id']=None
 with pytest.raises(RuntimeRefused):module.MarketGrant(canonical(p))


@pytest.mark.parametrize('at',['2023-11-24T14:25:00+00:00','2023-11-24T14:25:01+00:00','2023-11-27T14:00:00+00:00'])
def test_collection_grant_cannot_outlive_original_session_or_cutoff(at):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 with pytest.raises(RuntimeRefused):module.build_grant(**dict(values(),created_at=at))


@pytest.mark.parametrize('value',[True,0,-1,'1'])
def test_invalid_owner_generation_refuses(value):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 with pytest.raises(RuntimeRefused):module.build_grant(**dict(values(),owner_generation=value))


@pytest.mark.parametrize('value',[True,-1,float('nan'),float('inf'),'100'])
def test_invalid_monotonic_anchor_refuses(value):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 with pytest.raises(RuntimeRefused):module.build_grant(**dict(values(),prepared_mono=value))


@pytest.mark.parametrize('change',['missing','extra','same_job','wrong_path','wrong_task','wrong_size','grant_hash','fabricated_reservation'])
def test_fresh_requires_exact_distinct_history_reference(change):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 p=fresh_values()
 if change=='missing':p['history']=None
 elif change=='extra':p['history']['plan_override']={}
 elif change=='same_job':p['history']['job_id']=JOB
 elif change=='wrong_path':p['history']['manifest']['path']='artifacts/latest.bin'
 elif change=='wrong_task':p['history']['manifest']['task_id']=TASK
 elif change=='wrong_size':p['history']['manifest']['size_bytes']=True
 elif change=='grant_hash':p['history']['grant_sha256']='bad'
 else:p['reservation_id']=RESERVATION
 with pytest.raises(RuntimeRefused):module.build_grant(**p)


@pytest.mark.parametrize('state,consumed',[('PREPARED',True),('GRANTED',True),('RUNNING',False),('EVIDENCE_READY',False),('PUBLISHED',False),('COMPLETE',False)])
def test_record_state_never_claims_work_without_consumption(state,consumed):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**values()));record.update(state=state,consumed=consumed)
 with pytest.raises(RuntimeRefused):module.validate_record(record)


@pytest.mark.parametrize('change',['extra','purpose','reason','attempt_bool','attempt_limit','response_limit','evidence_size','manifest_without_evidence','fresh_evidence'])
def test_record_rejects_unbounded_or_inconsistent_mutable_state(change):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**(fresh_values() if change=='fresh_evidence' else values())))
 record.update(state='RUNNING',consumed=True)
 if change=='extra':record['url']='https://example.invalid'
 elif change=='purpose':record['purpose']='paper_read_owner_version'
 elif change=='reason':record['reason']='private response body'
 elif change in {'attempt_bool','attempt_limit','response_limit'}:
  record['summary']=dict(state='READY',reason=None,attempts=True if change=='attempt_bool' else 9 if change=='attempt_limit' else 1,responses=2 if change=='response_limit' else 0)
 elif change=='manifest_without_evidence':record['manifest']=history_reference()['manifest']
 else:record['evidence']=dict(size_bytes=3*1024**2+1 if change=='evidence_size' else 128,sha256='e'*64)
 with pytest.raises(RuntimeRefused):module.validate_record(record)


def test_published_collection_requires_matching_exact_manifest_and_is_detached():
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**values()))
 manifest=dict(artifact_id='77777777-7777-4777-8777-777777777777',task_id=TASK,path=f'artifacts/runs/{TASK}/market-collection-{JOB}.bin',size_bytes=128,sha256='e'*64)
 record.update(state='PUBLISHED',consumed=True,evidence=dict(size_bytes=128,sha256='e'*64),manifest=manifest,
               summary=dict(state='PAGINATION_COMPLETE',reason=None,attempts=3,responses=3))
 assert module.validate_record(record)==record
 bad=deepcopy(record);bad['manifest']['sha256']='f'*64
 with pytest.raises(RuntimeRefused):module.validate_record(bad)


@pytest.mark.parametrize('change',['missing','incomplete','zero_pair','one_pair','failed_pair','collection_summary'])
def test_fresh_completion_requires_successful_two_response_pair(change):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**fresh_values()))
 record.update(state='COMPLETE',consumed=True,summary=dict(state='PAIR_COMPLETE',reason=None,attempts=2,responses=2))
 if change=='missing':record['summary']=None
 elif change=='incomplete':record['summary']['state']='INCOMPLETE'
 elif change=='collection_summary':record['summary']['state']='PAGINATION_COMPLETE'
 elif change=='failed_pair':record['summary']['reason']='HTTP_FAILED'
 else:record['summary'].update(attempts=0 if change=='zero_pair' else 1,responses=0 if change=='zero_pair' else 1)
 with pytest.raises(RuntimeRefused):module.validate_record(record)


@pytest.mark.parametrize('state',['EVIDENCE_READY','PUBLISHED'])
@pytest.mark.parametrize('summary_state',[None,'READY','PENDING','WAITING','PAIR_COMPLETE'])
def test_collection_evidence_requires_collection_terminal_summary(state,summary_state):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**values()))
 record.update(state=state,consumed=True,evidence=dict(size_bytes=128,sha256='e'*64))
 if state=='PUBLISHED':
  record['manifest']=dict(artifact_id='77777777-7777-4777-8777-777777777777',task_id=TASK,
                          path=f'artifacts/runs/{TASK}/market-collection-{JOB}.bin',size_bytes=128,sha256='e'*64)
 if summary_state is not None:record['summary']=dict(state=summary_state,reason=None,attempts=2,responses=2)
 with pytest.raises(RuntimeRefused):module.validate_record(record)


@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
@pytest.mark.parametrize('state',['EVIDENCE_READY','PUBLISHED'])
@pytest.mark.parametrize('reason',['COLLECTION_CANCELED','HTTP_FAILED'])
def test_zero_response_incomplete_collection_evidence_remains_publishable(mode,state,reason):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**dict(values(),mode=mode)))
 record.update(state=state,consumed=True,evidence=dict(size_bytes=128,sha256='e'*64),
               summary=dict(state='INCOMPLETE',reason=reason,attempts=0,responses=0))
 if state=='PUBLISHED':
  record['manifest']=dict(artifact_id='77777777-7777-4777-8777-777777777777',task_id=TASK,
                          path=f'artifacts/runs/{TASK}/market-collection-{JOB}.bin',size_bytes=128,sha256='e'*64)
 assert module.validate_record(record)==record


def test_successful_fresh_pair_is_complete():
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**fresh_values()))
 record.update(state='COMPLETE',consumed=True,summary=dict(state='PAIR_COMPLETE',reason=None,attempts=2,responses=2))
 assert module.validate_record(record)==record


@pytest.mark.parametrize('change',['empty_pagination','failed_pagination','unexplained_collection_failure','unexplained_fresh_failure'])
def test_terminal_producer_summary_matches_actual_success_or_failure(change):
 module=importlib.import_module('compertum.runtime.paper_market_grants')
 record=module.initial_record(module.build_grant(**(fresh_values() if change=='unexplained_fresh_failure' else values())))
 record.update(state='RUNNING',consumed=True,summary=dict(state='PAGINATION_COMPLETE',reason=None,attempts=1,responses=1))
 if change=='empty_pagination':record['summary'].update(attempts=0,responses=0)
 elif change=='failed_pagination':record['summary']['reason']='HTTP_FAILED'
 else:record['summary'].update(state='INCOMPLETE',attempts=0,responses=0)
 with pytest.raises(RuntimeRefused):module.validate_record(record)
