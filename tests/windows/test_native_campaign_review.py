import hashlib,json
from uuid import uuid4
import pytest
from test_native_seals import state
from test_native_development_seals import setup,invalidate
from test_campaign_job import finish_unit
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.data.encoding import canonical
from compertum.campaign_review import CampaignReviewController
from compertum.simulation.campaign_runs import interrupt


def finished_source(state):
    controller,run,seal,remote,_=setup(state)
    finish_unit(controller,run)
    # The fixture explicitly records deterministic failures in every other slot.
    while controller.runs.summary(run)['state']!='COMPLETED':
        controller.runs.begin_campaign(run,controller.runs.prepare_campaign(run));interrupt(controller.runs,run,'MISSING_REFERENCE',terminal=True)
    return controller,run,seal,remote


def test_native_scorecard_keeps_all_trials_and_streams_acceptance(state,monkeypatch):
    controller,run,seal,remote=finished_source(state)
    import ctypes as c
    import compertum.runtime.jobs as jobs
    from compertum.runtime._windows import DWORD
    create=jobs.create_suspended;seen=[]
    def inspect(api,argv,env,cwd,inherited=()):
        if argv[3]=='compertum.runtime.campaign_worker' and argv[4]=='scorecard':
            for h in inherited[1:]:
                count=DWORD();buf=c.create_string_buffer(b'X')
                assert not api.WriteFile(h,buf,1,c.byref(count),None) and c.get_last_error()==5
            seen.append(len(inherited)-1)
        return create(api,argv,env,cwd,inherited)
    monkeypatch.setattr(jobs,'create_suspended',inspect)
    review=CampaignReviewController(controller.coordinator,controller.storage);task=str(uuid4())
    try:
        review.runs.register(task,run,'scorecard');review.step(task)
        job=review.active[2];assert job.api.limits(job.job).basic.active_limit==1
        receipt=job.wait();assert receipt['exit_code']==0
        review.tick();s=review.runs.status(task);assert s['state']=='COMPLETED'
        assert seen==[3] and s['financial_accepted'] is False
        raw=(controller.storage.root/s['artifact']['path']).read_bytes();header,payload=raw.split(b'\n',1);card=json.loads(payload)
        assert card['counts']=={'completed':1,'failed':35,'pending':0} and len(card['search_history'])==36 and card['shortlist']==[]
        assert s['payload_sha256']==hashlib.sha256(payload).hexdigest()
        assert json.loads(header)['worker_pid']==receipt['pid']
        assert s['attempts'][-1]['native_execution']==receipt['execution_identity']
        assert review.step(task)==s and review.active is None
    finally:review.pause();controller.pause()


def test_scorecard_requires_completed_source(state):
    controller,run,seal,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    review=CampaignReviewController(controller.coordinator,controller.storage)
    try:
        with pytest.raises(DataError):review.runs.register(str(uuid4()),run,'scorecard')
    finally:controller.pause()


@pytest.mark.parametrize('boundary',['prepare','resume','accept','reuse'])
def test_scorecard_rechecks_seal_at_each_boundary(state,monkeypatch,boundary):
    controller,run,seal,remote=finished_source(state);review=CampaignReviewController(controller.coordinator,controller.storage);task=str(uuid4());review.runs.register(task,run,'scorecard')
    try:
        if boundary=='prepare':
            invalidate(state,remote,seal)
            with pytest.raises((DataError,RuntimeRefused),match='SEAL_INVALIDATED'):review.step(task)
        elif boundary=='resume':
            begin=review.runs.begin
            def changed(*a,**kw):
                result=begin(*a,**kw);invalidate(state,remote,seal);return result
            monkeypatch.setattr(review.runs,'begin',changed)
            with pytest.raises((DataError,RuntimeRefused),match='SEAL_INVALIDATED'):review.step(task)
            assert review.active is None
        else:
            review.step(task);assert review.active[2].wait()['exit_code']==0
            if boundary=='accept':invalidate(state,remote,seal)
            review.tick()
            if boundary=='accept':assert review.runs.status(task)['state']=='BLOCKED'
            else:
                assert review.runs.status(task)['state']=='COMPLETED';invalidate(state,remote,seal)
                with pytest.raises((DataError,RuntimeRefused),match='SEAL_INVALIDATED'):review.step(task)
    finally:review.pause();controller.pause()


def test_scorecard_pause_and_retry_keep_orphan_and_fixed_request(state):
    controller,run,seal,remote=finished_source(state);review=CampaignReviewController(controller.coordinator,controller.storage);task=str(uuid4());review.runs.register(task,run,'scorecard')
    try:
        review.step(task);first=review.active[1].path;review.pause()
        assert first.exists() and review.runs.status(task)['state']=='INTERRUPTED'
        with pytest.raises(DataError):review.runs.register(str(uuid4()),run,'scorecard')
        review.runs.resume(task);review.step(task);assert review.active[2].wait()['exit_code']==0;review.tick()
        result=review.runs.completed(task)
        assert len(result['attempts'])==2 and result['attempts'][0]['status']=='INTERRUPTED' and first.exists()
    finally:review.pause();controller.pause()


@pytest.mark.parametrize('boundary',['accept','reuse'])
def test_scorecard_retained_launch_spec_is_checked(state,boundary):
    controller,run,seal,remote=finished_source(state);review=CampaignReviewController(controller.coordinator,controller.storage);task=str(uuid4());review.runs.register(task,run,'scorecard')
    try:
        review.step(task);assert review.active[2].wait()['exit_code']==0
        if boundary=='reuse':review.tick();assert review.runs.status(task)['state']=='COMPLETED'
        s=review.runs.status(task);path=controller.storage.root/s['attempts'][-1]['task_artifact']['path']
        path.write_bytes(path.read_bytes()+b' ')
        if boundary=='accept':review.tick();assert review.runs.status(task)['state']=='BLOCKED'
        else:
            with pytest.raises(DataError):review.runs.completed(task)
    finally:review.pause();controller.pause()


def test_prechild_capacity_refusal_can_use_second_attempt(state,monkeypatch):
    controller,run,seal,remote=finished_source(state);review=CampaignReviewController(controller.coordinator,controller.storage);task=str(uuid4());review.runs.register(task,run,'scorecard')
    reserve=review.storage.reserve_bytes;fail=[True]
    def capacity(owner,category,size):
        if owner==task and size==16*1024**2 and fail[0]:fail[0]=False;raise RuntimeRefused('STORAGE_CAPACITY')
        return reserve(owner,category,size)
    monkeypatch.setattr(review.storage,'reserve_bytes',capacity)
    try:
        with pytest.raises(RuntimeRefused,match='STORAGE_CAPACITY'):review.step(task)
        s=review.runs.status(task);assert s['state']=='INTERRUPTED' and s['attempts'][0]['native_execution'] is None
        assert (review.storage.root/s['attempts'][0]['task_artifact']['path']).is_file()
        review.runs.resume(task);review.step(task);assert review.active[2].wait()['exit_code']==0;review.tick()
        s=review.runs.completed(task);assert len(s['attempts'])==2
    finally:review.pause();controller.pause()


def test_registration_capacity_refusal_reuses_exact_request(state,monkeypatch):
    controller,run,seal,remote=finished_source(state);review=CampaignReviewController(controller.coordinator,controller.storage);task=str(uuid4())
    reserve=review.storage.reserve_bytes;fail=[True]
    def capacity(owner,category,size):
        if owner==task and fail[0]:fail[0]=False;raise RuntimeRefused('STORAGE_CAPACITY')
        return reserve(owner,category,size)
    monkeypatch.setattr(review.storage,'reserve_bytes',capacity)
    try:
        with pytest.raises(RuntimeRefused,match='STORAGE_CAPACITY'):review.runs.register(task,run,'scorecard')
        first=review.runs.status(task);assert first['state']=='INTERRUPTED' and first['request_artifact'] is None and first['attempts']==[]
        with pytest.raises(DataError):review.runs.register(str(uuid4()),run,'scorecard')
        result=review.runs.register(task,run,'scorecard')
        assert result['state']=='READY' and result['request_sha256']==first['request_sha256']
    finally:review.pause();controller.pause()


@pytest.mark.parametrize('case',['erase_attempts','reset_terminal'])
def test_rehashed_history_cannot_erase_dispatched_attempts(state,case):
    controller,run,seal,remote=finished_source(state);review=CampaignReviewController(controller.coordinator,controller.storage);task=str(uuid4());review.runs.register(task,run,'scorecard')
    try:
        review.step(task);review.pause();review.runs.resume(task);review.step(task);review.pause()
        s=review.runs.status(task);assert s['state']=='FAILED' and len(s['attempts'])==2
        s.update(state='READY',last_transition='RESUMED')
        if case=='erase_attempts':s['attempts']=[]
        raw=canonical(s);db=review.runs.store.conn
        with db:
            db.execute('UPDATE campaign_reviews SET body=? WHERE task_id=?',(raw.decode(),task))
            db.execute('UPDATE campaign_review_history SET body=?,sha256=? WHERE task_id=? AND seq=(SELECT max(seq) FROM campaign_review_history WHERE task_id=?)',(raw.decode(),hashlib.sha256(raw).hexdigest(),task,task))
        with pytest.raises(DataError):review.runs.status(task)
    finally:review.pause();controller.pause()


def test_pause_after_worker_integrity_failure_does_not_grant_retry(state,monkeypatch):
    controller,run,seal,remote=finished_source(state);review=CampaignReviewController(controller.coordinator,controller.storage);task=str(uuid4());review.runs.register(task,run,'scorecard')
    import compertum.runtime.jobs as jobs
    create=jobs.create_suspended
    def changed(api,argv,*args,**kwargs):
        if argv[3]=='compertum.runtime.campaign_worker' and argv[4]=='scorecard':
            argv=list(argv);argv[8]='0'*64
        return create(api,argv,*args,**kwargs)
    monkeypatch.setattr(jobs,'create_suspended',changed)
    try:
        review.step(task);assert review.active[2].wait()['exit_code']==6
        review.pause();assert review.runs.status(task)['state']=='BLOCKED'
        with pytest.raises(DataError):review.runs.resume(task)
    finally:review.pause();controller.pause()
