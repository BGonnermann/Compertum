from uuid import uuid4
import json,hashlib
import pytest
from test_persistence import owned
from test_storage import manager
from test_saved_runs import control
from helpers.simulation_fixture import fixture,SECTORS
from compertum.simulation.runs import SavedRuns
from compertum.simulation.prediction import score_predictions
from compertum.data.errors import DataError

CUTOFF='2026-10-09T00:00:00+00:00'

def create(owned,**kwargs):
    storage=manager(owned);runs=SavedRuns(storage);run=str(uuid4());chunks,start,end,_=fixture(scored=26)
    result=runs.create(run,chunks,SECTORS,start,end,scoring_as_of=CUTOFF,**kwargs)
    return storage,runs,run,(chunks,start,end),result


def test_frozen_cutoff_and_nine_units_complete_without_duplicate_reports(owned):
    storage,runs,run,(chunks,start,end),created=create(owned)
    assert created['total_units']==9 and created['scoring_as_of']==CUTOFF
    assert runs.create(run,chunks,SECTORS,start,end,scoring_as_of='2026-10-09T00:00:00Z')==created
    with pytest.raises(DataError,match='RUN_CONFLICT'):
        runs.create(run,chunks,SECTORS,start,end,scoring_as_of='2026-10-10T00:00:00Z')
    control(runs,run,'resume')
    for _ in range(9):state=runs.step(run)
    assert state['state']=='COMPLETED' and state['completed_units']==9
    reports=[r for r in state['results'] if r['cost_bps'] is None]
    assert [r['horizon'] for r in reports]==[1,5,21]
    for row in reports:
        expected=score_predictions(chunks,SECTORS,start,end,row['horizon'],scoring_as_of=CUTOFF)
        assert (storage.root/row['artifact']['path']).read_bytes()==expected.content


@pytest.mark.parametrize('change',['cutoff','horizon','input'])
def test_prediction_record_refuses_wrong_binding(owned,change):
    storage,runs,run,(chunks,start,end),created=create(owned)
    from compertum.simulation.worker_record import pack_result,verify_result
    expected=score_predictions(chunks,SECTORS,start,end,1,scoring_as_of=CUTOFF)
    raw=pack_result(expected.content,created['request_sha256'])
    assert verify_result(raw,created['request_sha256'],1,None,scoring_as_of=CUTOFF)==expected.content
    with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):
        verify_result(raw,'f'*64 if change=='input' else created['request_sha256'],5 if change=='horizon' else 1,None,
            scoring_as_of='2026-10-10T00:00:00+00:00' if change=='cutoff' else CUTOFF)


def test_legacy_schedule_remains_six_and_new_attempt_clock_fits(owned):
    from compertum.simulation.runs import unit_schedule,attempt_seconds
    storage,runs,run,args,created=create(owned)
    assert len(unit_schedule({}))==6 and len(unit_schedule({'scoring_as_of':CUTOFF}))==9
    assert attempt_seconds({})==120 and attempt_seconds({'scoring_as_of':CUTOFF})==90
    assert 9*2*(attempt_seconds({'scoring_as_of':CUTOFF})+6)<=1800
