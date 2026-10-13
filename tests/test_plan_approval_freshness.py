"""Approval preserves reviewed evidence while checking actual current conditions."""
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4
import pytest
from compertum.domain import ExecutionObservation,ContractError
from compertum.execution_contracts import instant
from compertum.execution_plans import build_plan,authorize_fake_plan
from compertum.execution_risk import snapshot_sha256
from test_execution_plans import setup,refresh
from test_execution_risk import NOW,calendar,order


def context(seconds=30):
    original=ExecutionObservation(setup())
    plan=build_plan(original,kind='CLOSE_LONG',now=NOW,calendar=calendar())
    at=(instant(NOW)+timedelta(seconds=seconds)).isoformat()
    current=original.to_payload();refresh(current,at)
    return original,plan,current,at


@pytest.mark.parametrize('seconds',[30,59])
def test_delayed_approval_uses_fresh_health_and_retains_reviewed_snapshot(seconds):
    original,plan,current,at=context(seconds);before=plan.to_payload()
    result=authorize_fake_plan(plan,original,now=at,calendar=calendar(),current_observation=ExecutionObservation(current)).to_payload()
    assert result['authorized_at']==at
    assert result['snapshot_sha256']==snapshot_sha256(original)
    assert result['economic_sha256']==before['economic_sha256']
    assert result['start_expires_at']==before['start_expires_at']
    assert plan.to_payload()==before


def test_default_still_rejects_stale_evidence_without_backdating():
    original,plan,current,at=context()
    with pytest.raises(ContractError,match='HEARTBEAT_STALE'):
        authorize_fake_plan(plan,original,now=at,calendar=calendar())


@pytest.mark.parametrize('value',[{},False,0,''])
def test_only_none_falls_back_to_original(value):
    original,plan,current,at=context(0)
    with pytest.raises(ContractError,match='INVALID_EXECUTION_RECORD'):
        authorize_fake_plan(plan,original,now=at,calendar=calendar(),current_observation=value)


@pytest.mark.parametrize('path,value,reason',[
    ('account.sleeve_cash','5501','PLAN_SNAPSHOT_CHANGED'),
    ('account.broker_cash','5501','PLAN_SNAPSHOT_CHANGED'),
    ('generation',2,'PLAN_BINDING_CHANGED'),
    ('account_alias','fake-other','PLAN_BINDING_CHANGED'),
    ('clock.calendar_sha256','0'*64,'CALENDAR_CHANGED'),
    ('authority.halted',False,'PLAN_BINDING_CHANGED'),
    ('health.connected',False,'OFFLINE'),
    ('authority.unknown_intents',True,'UNKNOWN_INTENT'),
    ('authority.foreign_activity',True,'OWNERSHIP_UNVERIFIED'),
    ('health.watchdog_at',NOW,'HEARTBEAT_STALE'),
    ('health.supervision_at','2023-10-17T13:20:00+00:00','SUPERVISION_EXPIRED'),
    ('account.reconciled_at','2023-10-17T13:34:00+00:00','RECONCILIATION_STALE')])
def test_current_conditions_cannot_reuse_old_authority(path,value,reason):
    original,plan,current,at=context();parts=path.split('.');target=current
    for key in parts[:-1]:target=target[key]
    target[parts[-1]]=value
    with pytest.raises(ContractError,match=reason):
        authorize_fake_plan(plan,original,now=at,calendar=calendar(),current_observation=ExecutionObservation(current))


@pytest.mark.parametrize('change',['holding','order'])
def test_current_economics_must_still_match_reviewed_plan(change):
    original,plan,current,at=context()
    if change=='holding':current['positions'][0].update(owned_quantity=44,quantity='44')
    else:current['orders']=[order(filled=0,status='ACKNOWLEDGED')]
    with pytest.raises(ContractError,match='PLAN_SNAPSHOT_CHANGED'):
        authorize_fake_plan(plan,original,now=at,calendar=calendar(),current_observation=ExecutionObservation(current))


def test_original_observation_cannot_be_replaced_by_new_snapshot():
    original,plan,current,at=context();changed=original.to_payload();changed['observation_id']=str(uuid4())
    with pytest.raises(ContractError,match='PLAN_SNAPSHOT_CHANGED'):
        authorize_fake_plan(plan,ExecutionObservation(changed),now=at,calendar=calendar(),current_observation=ExecutionObservation(current))


def test_current_quotes_do_not_enlarge_reviewed_children():
    original,plan,current,at=context();current['quotes'][0].update(bid='50',ask='50');before=deepcopy(plan.to_payload())
    result=authorize_fake_plan(plan,original,now=at,calendar=calendar(),current_observation=ExecutionObservation(current))
    assert result.to_payload()['snapshot_sha256']==before['snapshot_sha256']
    assert [x['maximum_quantity'] for x in plan.to_payload()['children']]==[19,19,7]
    assert plan.to_payload()==before


def test_current_evidence_does_not_extend_exact_start_expiry():
    original,plan,current,at=context(60)
    with pytest.raises(ContractError,match='PLAN_EXPIRED'):
        authorize_fake_plan(plan,original,now=at,calendar=calendar(),current_observation=ExecutionObservation(current))