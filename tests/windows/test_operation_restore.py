"""One actual full reserve, older pending snapshot, newer attempt and fills."""
import json
from pathlib import Path
from test_recovery import invoke


def test_old_pending_snapshot_keeps_later_acceptance_and_reconciles_after_expiry(tmp_path):
    prepared=invoke(tmp_path,'prepare',fake_operation=True)
    reserve=prepared['actual_reserve']
    assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and not reserve['sparse']
    args=dict(manifest=prepared['before'],seal_id=prepared['seal_id'],evaluation_id=prepared['evaluation_id'],pending_event=prepared['pending_event'])
    first=invoke(tmp_path,'restore',**args)
    assert first['status']=='RESTORED' and first['execution_state']=='VERIFIED' and first['admission']=='HALTED'
    assert first['seal_state']=='CONSUMED' and first['safe_delivery_count']==1 and first['broker_pending']>=1
    outcomes=[]
    for run in range(2):
        if run:
            invoke(tmp_path,'interrupt_restore',manifest=prepared['before'],_expected_exit=17)
            assert invoke(tmp_path,'probe_blocked')['status']=='RESTORE_RECOVERY_REQUIRED'
            assert invoke(tmp_path,'recover_interruption')['status']=='ABORTED'
            again=invoke(tmp_path,'restore',**args)
            assert again['status']=='RESTORED' and again['execution_state']=='VERIFIED' and again['safe_delivery_count']==1
        result=invoke(tmp_path,'reconcile_operation');outcomes.append(result)
        assert result['result']['intent_status']=='FILLED' and result['result']['filled_quantity']==19
        assert result['final']['status']=='RECONCILED' and result['acceptances']==result['submissions']==1 and result['lookups']==0
        assert result['positions']=={'AAPL':26} and result['cash']=='7400' and result['armed'] is False
        assert result['after_incident']==result['before_incident']+[0]
        assert result['original_retry']['status']=='PENDING_UNCONFIRMED'
    assert invoke(tmp_path,'attempt_consume',seal_id=prepared['seal_id'])['status']=='DENIED'
    (tmp_path/'operation-restore-receipt.json').write_text(json.dumps(dict(actual_reserve=reserve,outcomes=outcomes,financial_accepted=False)),encoding='utf-8')
