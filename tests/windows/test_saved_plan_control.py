"""Public saved fake plans with actual native owners and the allocated1GiBreserve."""
import json,shutil,sqlite3
from uuid import uuid4
import pytest
from test_execution_authority import profile
from test_fake_operator_control import launch,stop,call,ROOT,provision
from compertum.deterministic_broker import DeterministicBroker
from compertum.runtime.errors import RuntimeRefused


def test_saved_plans_public_disconnect_checkpoint_restart_and_no_effects(tmp_path):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml')
    # Independently initialize invented account state once, outside execution
    # snapshots. The runtime observation reader cannot create or reset it.
    provision(tmp_path)
    p,status=launch(tmp_path,'drop_plan_reply')
    try:
        reserve=status['watchdog']['owners']['execution']['reserve']
        assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and not reserve['sparse']
        sid=str(uuid4());frozen=profile();call(tmp_path,'open_session',session_id=sid,profile=frozen);call(tmp_path,'supervise')
        saved=call(tmp_path,'prepare_plan',kind='CLOSE_LONG');plan=call(tmp_path,'inspect_plan',plan_id=saved['plan_id'])
        assert [v['maximum_quantity'] for v in plan['plan']['children']]==[19,19,7]
        research=(tmp_path/'state/research.sqlite').as_uri()+'?mode=ro'
        with sqlite3.connect(research,uri=True) as db:before=db.execute('SELECT count(*) FROM operator_requests').fetchone()[0]
        assert call(tmp_path,'inspect_plan',plan_id=saved['plan_id'])==plan
        with sqlite3.connect(research,uri=True) as db:assert db.execute('SELECT count(*) FROM operator_requests').fetchone()[0]==before
        request=str(uuid4());args=dict(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
        approval=call(tmp_path,'approve_plan',request_id=request,**args)
        assert call(tmp_path,'approve_plan',request_id=request,**args)==approval
        start_id=str(uuid4());started=call(tmp_path,'start_plan',request_id=start_id,**args)
        assert started['status']=='STARTED_NO_DISPATCH' and not started['effects_enabled'] and call(tmp_path,'start_plan',request_id=start_id,**args)==started
        retained=call(tmp_path,'prepare_plan',kind='CLOSE_LONG');later_args=dict(plan_id=retained['plan_id'],plan_sha256=retained['plan_sha256'])
        call(tmp_path,'approve_plan',**later_args)
        with sqlite3.connect((tmp_path/'state/execution.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            assert db.execute('SELECT count(*) FROM fake_saved_plans').fetchone()==(2,)
            assert db.execute('SELECT count(*) FROM fake_saved_plan_phases').fetchone()==(3,)
            assert db.execute('SELECT count(*) FROM fake_operator_requests WHERE request_id=?',(request,)).fetchone()==(1,)
        receipt=stop(tmp_path,p);assert receipt['barrier_checked'] and receipt['disconnected_after_execution_commit']==[approval]
        p,after=launch(tmp_path,'normal');assert after['supervisor_generation']==status['supervisor_generation']+1
        assert not call(tmp_path,'status')['supervised'] and not call(tmp_path,'status')['armed']
        assert call(tmp_path,'inspect_plan',plan_id=saved['plan_id'])==plan
        call(tmp_path,'open_session',session_id=str(uuid4()),profile=frozen);call(tmp_path,'supervise')
        with pytest.raises(RuntimeRefused,match='PLAN_CONTEXT_CHANGED'):call(tmp_path,'start_plan',**later_args)
        with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):call(tmp_path,'start_plan',request_id=start_id,**args)
        with sqlite3.connect((tmp_path/'state/execution.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            assert json.loads(db.execute('SELECT result FROM fake_operator_requests WHERE request_id=?',(start_id,)).fetchone()[0])==started
        fresh=call(tmp_path,'prepare_plan',kind='CLOSE_LONG');assert fresh['context']['generation']>saved['context']['generation']
        assert not call(tmp_path,'status')['armed']
        stop(tmp_path,p)
        b=DeterministicBroker(tmp_path/'state/fake-broker',create=False)
        try:
            snapshot=b.snapshot();assert snapshot['cash']=='5500' and snapshot['positions']=={'AAPL':45} and snapshot['calls']==[] and snapshot['orders']==[]
        finally:b.close()
        (tmp_path/'saved-plan-receipt.json').write_text(json.dumps(dict(public_pipe=True,checkpoint_exclusion=True,execution_commit_before_disconnect=True,identical_retry_receipt=True,restart_invalidates_continuation=True,cross_generation_request_refused=True,independent_broker_unchanged=True,actual_reserve=reserve,financial_accepted=False,effects_enabled=False)),encoding='utf-8')
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=5)
