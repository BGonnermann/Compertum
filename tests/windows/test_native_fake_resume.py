"""Authenticated resume with actual owners, lost reply and allocated1GiBreserve."""
import json,shutil,sqlite3,time
from contextlib import closing
from pathlib import Path
from uuid import uuid4
import compertum
import pytest
from test_execution_authority import profile
from test_fake_operator_control import launch,stop,call,ROOT,provision
from compertum.deterministic_broker import DeterministicBroker
from compertum.runtime.errors import RuntimeRefused


def stored(root):
    with closing(sqlite3.connect((root/'state/execution.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
        return {k:json.loads(v) for k,v in db.execute('SELECT key,value FROM state')}


def test_public_resume_lost_reply_halt_and_restart_stay_disarmed(tmp_path):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');opening=provision(tmp_path)
    p,status=launch(tmp_path,'drop_resume_reply')
    try:
        reserve=status['watchdog']['owners']['execution']['reserve']
        assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and not reserve['sparse']
        call(tmp_path,'open_session',session_id=str(uuid4()),profile=profile());call(tmp_path,'supervise')
        saved=call(tmp_path,'prepare_plan',kind='CLOSE_LONG');args=dict(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
        call(tmp_path,'approve_plan',**args);call(tmp_path,'start_plan',**args)
        unapproved=call(tmp_path,'prepare_plan',kind='CLOSE_LONG');approve_args=dict(plan_id=unapproved['plan_id'],plan_sha256=unapproved['plan_sha256'])
        unstarted=call(tmp_path,'prepare_plan',kind='CLOSE_LONG');start_args=dict(plan_id=unstarted['plan_id'],plan_sha256=unstarted['plan_sha256'])
        call(tmp_path,'approve_plan',**start_args)
        plan=call(tmp_path,'inspect_plan',plan_id=saved['plan_id']);before=stored(tmp_path)
        request=str(uuid4());result=call(tmp_path,'resume',request_id=request)
        assert result['admission']=='DISARMED' and not result['halted'] and not result['armed'] and not result['effects_enabled']
        assert result['financial_accepted'] is False and call(tmp_path,'resume',request_id=request)==result
        after=stored(tmp_path)
        assert after['fake_plan_epoch']==before['fake_plan_epoch']+1 and after['admission']=='DISARMED' and after['approved_plan'] is None
        assert after['fake_operator_state']['ack_mono']==before['fake_operator_state']['ack_mono'] and after['fake_operator_state']['ack_utc']==before['fake_operator_state']['ack_utc']
        assert call(tmp_path,'inspect_plan',plan_id=saved['plan_id'])==plan
        for operation,old_args in (('approve_plan',approve_args),('start_plan',start_args),('advance_plan',args)):
            with pytest.raises(RuntimeRefused,match='PLAN_CONTEXT_CHANGED'):call(tmp_path,operation,**old_args)
        with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):call(tmp_path,'resume',health=True)
        with closing(sqlite3.connect((tmp_path/'state/execution.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
            assert db.execute('SELECT count(*) FROM fake_operator_requests WHERE request_id=?',(request,)).fetchone()==(1,)
        call(tmp_path,'halt');halted=stored(tmp_path)
        assert call(tmp_path,'resume',request_id=request)==result and stored(tmp_path)==halted
        with pytest.raises(RuntimeRefused,match='SUPERVISION_REQUIRED'):call(tmp_path,'resume')
        assert call(tmp_path,'status')['halted']
        call(tmp_path,'supervise');call(tmp_path,'resume');assert not call(tmp_path,'status')['halted']
        receipt=stop(tmp_path,p)
        assert receipt['barrier_checked'] and receipt['disconnected_after_execution_commit']==[result]
        assert Path(receipt['execution_origin']['package_root']).resolve()==Path(compertum.__file__).resolve().parent
        p,restarted=launch(tmp_path,'normal');assert restarted['supervisor_generation']>status['supervisor_generation']
        state=call(tmp_path,'status');assert state['halted'] and not state['armed'] and not state['supervised']
        before_retry=stored(tmp_path)
        with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):call(tmp_path,'resume',request_id=request)
        assert stored(tmp_path)==before_retry
        with pytest.raises(RuntimeRefused,match='SESSION_RESTARTED'):call(tmp_path,'resume')
        assert call(tmp_path,'inspect_plan',plan_id=saved['plan_id'])==plan
        call(tmp_path,'open_session',session_id=str(uuid4()),profile=profile());call(tmp_path,'supervise')
        fresh=call(tmp_path,'resume');assert fresh['admission']=='DISARMED' and fresh['generation']>result['generation']
        with pytest.raises(RuntimeRefused,match='PLAN_CONTEXT_CHANGED'):call(tmp_path,'advance_plan',**args)
        began=time.monotonic();current=call(tmp_path,'status');elapsed=time.monotonic()-began
        assert elapsed<5 and not current['armed'] and not current['halted']
        final_receipt=stop(tmp_path,p)
        assert Path(final_receipt['execution_origin']['package_root']).resolve()==Path(compertum.__file__).resolve().parent
        b=DeterministicBroker(tmp_path/'state/fake-broker',create=False)
        try:
            snapshot=b.snapshot();assert snapshot['cash']=='5500' and snapshot['positions']=={'AAPL':45} and snapshot['calls']==[] and snapshot['orders']==[]
        finally:b.close()
        (tmp_path/'resume-receipt.json').write_text(json.dumps(dict(public_pipe=True,actual_reserve=reserve,opening=opening,first_execution_origin=receipt['execution_origin'],restart_execution_origin=final_receipt['execution_origin'],lost_reply=True,checkpoint_exclusion=True,epoch_advanced_once=True,supervision_unchanged=True,replay_after_halt_inert=True,restart_invalidates=True,old_plan_inspectable_unusable=True,broker_unchanged=True,status_seconds=elapsed,financial_accepted=False,effects_enabled=False)),encoding='utf-8')
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=5)
