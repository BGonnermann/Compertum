"""Actual public execution progression, full reserve and independent fake fills."""
import json,shutil,sqlite3,time
from uuid import uuid4
import pytest
from test_execution_authority import profile
from test_fake_operator_control import launch,stop,call,ROOT,provision
from compertum.deterministic_broker import DeterministicBroker
from compertum.runtime.errors import RuntimeRefused


def test_public_serial_effects_lost_reply_and_restart_keep_one_acceptance(tmp_path):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml')
    provision(tmp_path)
    p,status=launch(tmp_path,'drop_step_reply');durations=[]
    try:
        reserve=status['watchdog']['owners']['execution']['reserve'];assert reserve['allocated_bytes']>=1024**3 and not reserve['sparse']
        call(tmp_path,'open_session',session_id=str(uuid4()),profile=profile());call(tmp_path,'supervise')
        saved=call(tmp_path,'prepare_plan',kind='CLOSE_LONG');args=dict(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
        call(tmp_path,'approve_plan',**args);call(tmp_path,'start_plan',**args)
        request=str(uuid4());first=call(tmp_path,'advance_plan',request_id=request,**args)
        assert first['status']=='PENDING' and first['quantity']==19 and call(tmp_path,'advance_plan',request_id=request,**args)==first
        receipt=stop(tmp_path,p);assert receipt['barrier_checked'] and receipt['disconnected_after_execution_commit']==[first]
        # Restart with an accepted open order. It may be reconciled, but the old
        # operation never gains permission to submit its remaining children.
        p,after=launch(tmp_path,'normal');assert after['supervisor_generation']>status['supervisor_generation']
        stored=call(tmp_path,'operation_status',plan_id=saved['plan_id'])
        assert stored['intents'][0]['status']=='ACKNOWLEDGED' and not stored['fresh_reconciliation']
        call(tmp_path,'open_session',session_id=str(uuid4()),profile=profile());call(tmp_path,'supervise')
        with pytest.raises(RuntimeRefused,match='PLAN_CONTEXT_CHANGED'):call(tmp_path,'advance_plan',**args)
        b=DeterministicBroker(tmp_path/'state/fake-broker',create=False)
        try:b.fill(first['order_id'],19,'100')
        finally:b.close()
        reconciled=call(tmp_path,'reconcile_plan',**args);assert reconciled['intent_status']=='FILLED'
        saved=call(tmp_path,'prepare_plan',kind='CLOSE_LONG');args=dict(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
        call(tmp_path,'approve_plan',**args);call(tmp_path,'start_plan',**args)
        for qty in (19,7):
            request=str(uuid4());started=time.monotonic();result=call(tmp_path,'advance_plan',request_id=request,**args);durations.append(time.monotonic()-started)
            assert result['status']=='PENDING' and result['quantity']==qty
            assert call(tmp_path,'advance_plan',request_id=request,**args)==result
            b=DeterministicBroker(tmp_path/'state/fake-broker',create=False)
            try:b.fill(result['order_id'],qty,'100')
            finally:b.close()
            polled=call(tmp_path,'advance_plan',**args);assert polled['intent_status']=='FILLED'
        complete=call(tmp_path,'advance_plan',**args);assert complete['status']=='COMPLETE' and complete['remaining_positions']==[]
        stop(tmp_path,p)
        b=DeterministicBroker(tmp_path/'state/fake-broker',create=False)
        try:
            s=b.snapshot();assert s['cash']=='10000' and s['positions']=={} and len(s['orders'])==3
            assert sum(v['kind']=='SUBMIT' for v in s['calls'])==3
        finally:b.close()
        (tmp_path/'progression-receipt.json').write_text(json.dumps(dict(actual_reserve=reserve,public_lost_reply=True,identical_retry=True,serial_quantities=[19,19,7],broker_acceptances=3,fresh_flat=True,restart_invalidates=True,dispatch_call_seconds=durations,financial_accepted=False)),encoding='utf-8')
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=5)
