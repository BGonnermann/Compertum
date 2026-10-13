from uuid import uuid4
import pytest
from test_persistence import owned
from test_saved_runs import setup_run,control
from compertum.simulation import replay
from compertum.data.errors import DataError
from helpers.simulation_fixture import SECTORS


def test_begin_accept_matches_synchronous_checkpoint(owned):
    storage,runs,run,(chunks,start,end),created=setup_run(owned)
    control(runs,run,'resume')
    admission=runs.begin(run)
    assert admission['unit']==0 and admission['attempt']==1
    assert runs.summary(run)['state']=='RUNNING'
    with pytest.raises(DataError,match='RUN_NOT_READY'):runs.begin(run)
    raw=replay(chunks,SECTORS,start,end,1).content
    from compertum.simulation.worker_record import pack_result
    raw=pack_result(raw,admission['request_sha256'])
    state=runs._load(run)
    artifact=runs._publish(state,'unit-00-attempt-1.replay',raw)
    accepted=runs.accept(run,artifact)
    assert accepted['completed_units']==1 and accepted['state']=='READY'
    assert runs.status(run)['results'][0]['artifact']==artifact


def test_dispatch_interruption_keeps_attempt_limit(owned):
    storage,runs,run,args,created=setup_run(owned)
    for attempt in (1,2):
        control(runs,run,'resume');assert runs.begin(run)['attempt']==attempt
        assert runs.interrupt(run,'OPERATOR_PAUSE')['state']=='INTERRUPTED'
    control(runs,run,'resume')
    with pytest.raises(DataError,match='RUN_ATTEMPT_BOUND'):runs.begin(run)
    assert len(runs.summary(run)['attempts'])==2


def test_accept_refuses_unrelated_artifact_and_terminal_failure(owned):
    storage,runs,run,args,created=setup_run(owned)
    control(runs,run,'resume');runs.begin(run)
    with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):runs.accept(run,created['input_artifact'])
    assert runs.interrupt(run,'WORKER_FAILED',terminal=True)['state']=='FAILED'
    with pytest.raises(DataError,match='RUN_TERMINAL'):control(runs,run,'resume')


def test_summary_does_not_decode_bulk_input(owned,monkeypatch):
    storage,runs,run,args,created=setup_run(owned)
    monkeypatch.setattr(runs,'_read',lambda *a:pytest.fail('bulk artifact read in status'))
    assert runs.summary(run)['state']=='PAUSED'


@pytest.mark.parametrize('wrong',['malformed','horizon'])
def test_accept_rejects_bad_worker_record(owned,wrong):
    storage,runs,run,(chunks,start,end),created=setup_run(owned)
    control(runs,run,'resume');admission=runs.begin(run)
    from compertum.simulation.worker_record import pack_result
    raw=b'bad' if wrong=='malformed' else pack_result(replay(chunks,SECTORS,start,end,5).content,admission['request_sha256'])
    artifact=runs._publish(runs._load(run),'unit-00-attempt-1.replay',raw)
    with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):runs.accept(run,artifact)
