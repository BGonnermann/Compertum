"""Native-produced evidence enters one durable aggregate registration."""
from uuid import uuid4
import pytest
from test_native_seals import state
from test_native_campaign_review import finished_source
from compertum.auditor import AuditorController
from compertum.campaign_review import CampaignReviewController
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused


def evidence(state,*,with_authority=False):
    controller,run,seal,remote=finished_source(state);auditor=AuditorController(controller.coordinator,controller.storage);review=CampaignReviewController(controller.coordinator,controller.storage)
    try:
        task=str(uuid4());auditor.runs.register(task,run,0);auditor.step(task);assert auditor.active[2].wait()['exit_code']==0;auditor.tick();assert auditor.runs.status(task)['state']=='COMPLETED'
        card=str(uuid4());review.runs.register(card,run,'scorecard');review.step(card);assert review.active[2].wait()['exit_code']==0;review.tick();assert review.runs.status(card)['state']=='COMPLETED'
        return (controller,run,review,card,seal,remote) if with_authority else (controller,run,review,card)
    finally:auditor.pause();review.pause();controller.pause()


def test_aggregate_registration_retains_complete_metered_exports(state):
    controller,run,review,card=evidence(state);task=str(uuid4());result=review.runs.register(task,run,'aggregate')
    assert result['state']=='READY' and result['kind']=='aggregate' and len(result['preparation_artifacts'])==1
    assert result['request_sha256']!=result['registration_sha256']
    header=review.runs.current(result);assert [r['kind'] for r in header['records']]==['campaign','frame','unit_audit','audit_history','scorecard']
    assert header['records'][-1]['artifact']['task_id']==card
    assert review.runs.register(task,run,'aggregate')==result
    with pytest.raises(DataError):review.runs.register(str(uuid4()),run,'aggregate')
    path=controller.storage.root/result['preparation_artifacts'][0]['path'];raw=path.read_bytes();path.write_bytes(raw[:-1]+b' ')
    with pytest.raises(DataError):review.runs.current(result)


def test_aggregate_known_capacity_retry_keeps_intent_and_published_export(state,monkeypatch):
    controller,run,review,card=evidence(state);task=str(uuid4());publish=review.runs._publish
    def no_request(task,path,raw):
        if path.endswith('/request.review'):raise RuntimeRefused('STORAGE_CAPACITY')
        return publish(task,path,raw)
    monkeypatch.setattr(review.runs,'_publish',no_request)
    with pytest.raises(RuntimeRefused,match='STORAGE_CAPACITY'):review.runs.register(task,run,'aggregate')
    first=review.runs.status(task);assert first['state']=='INTERRUPTED' and len(first['preparation_artifacts'])==1
    monkeypatch.setattr(review.runs,'_publish',publish);result=review.runs.register(task,run,'aggregate')
    assert result['state']=='READY' and result['preparation_artifacts']==first['preparation_artifacts'] and result['registration_sha256']==first['registration_sha256']


def test_aggregate_unknown_export_publication_remains_blocked(state,monkeypatch):
    controller,run,review,card=evidence(state);task=str(uuid4());publish=review.runs._publish
    def uncertain(task,path,raw):
        result=publish(task,path,raw)
        if path.endswith('/unit-audits-0.json'):raise OSError('INJECTED_UNKNOWN_PUBLICATION')
        return result
    monkeypatch.setattr(review.runs,'_publish',uncertain)
    with pytest.raises(OSError):review.runs.register(task,run,'aggregate')
    result=review.runs.status(task);assert result['state']=='BLOCKED' and result['preparation_artifacts']==[] and result['request_sha256'] is None
    assert (controller.storage.root/f'artifacts/runs/{task}/review/input/unit-audits-0.json').is_file()
    monkeypatch.setattr(review.runs,'_publish',publish);assert review.runs.register(task,run,'aggregate')==result
    with pytest.raises(DataError):review.runs.register(str(uuid4()),run,'aggregate')


@pytest.mark.parametrize('boundary,code,recorded,bound',[('unrecorded',81,0,False),('recorded',82,1,False),('bound',83,1,True)])
def test_actual_registration_owner_death_never_adopts_exports(tmp_path,boundary,code,recorded,bound):
    import shutil
    from pathlib import Path
    from test_review_restart import child
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml');run,task=str(uuid4()),str(uuid4())
    assert child(tmp_path,run,task,'create_aggregate')['state']=='EVIDENCE_READY'
    child(tmp_path,run,task,'registration_crash_'+boundary,code)
    result=child(tmp_path,run,task,'status')
    assert result['state']=='BLOCKED' and result['attempts']==[] and len(result['preparation_artifacts'])==recorded
    assert (result['request_sha256'] is not None)==bound and result['request_artifact'] is None
    assert (tmp_path/f'artifacts/runs/{task}/review/input/unit-audits-0.json').is_file()
    assert child(tmp_path,run,task,'status')==result
