"""Native independent owners and 1 GiB reserve. All account origins are invented."""
import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.runtime.supervisor import discover
from compertum.runtime.control import durable_request
from compertum.runtime.errors import RuntimeRefused

ROOT=Path(__file__).parents[2]


def control(root,action,payload=None,*,timeout=10):
    route=discover(root)
    command=dict(schema_version=1,request_id=str(uuid4()),target_role='supervisor',
        target_generation=route.registration.generation,action=action,payload=payload or {},actor=dict(kind='operator'))
    return durable_request(route,command,timeout=timeout)


def output(p):
    out=p._fixture_stdout.read_bytes();err=p._fixture_stderr.read_bytes()
    assert len(out)<=1024**2 and len(err)<=1024**2
    return out,err


def launch(root,mode):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    evidence=root.parent/'native-control-evidence';evidence.mkdir(exist_ok=True)
    token=str(uuid4());stdout=evidence/f'activity-supervisor-{token}.stdout';stderr=evidence/f'activity-supervisor-{token}.stderr'
    with stdout.open('xb') as out,stderr.open('xb') as err:
        p=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/paper_activity_supervisor.py'),str(root),mode],
            executable=sys._base_executable,env=env,stdout=out,stderr=err,creationflags=0x08000000)
    p._fixture_stdout=stdout;p._fixture_stderr=stderr
    until=time.monotonic()+20
    while time.monotonic()<until:
        if p.poll() is not None:pytest.fail(output(p)[1].decode())
        try:
            status=control(root,'status',timeout=2);w=status.get('watchdog',{});e=w.get('owners',{}).get('execution',{})
            if w.get('mutual',{}).get('verified') and e.get('mutual',{}).get('verified'):return p,status
        except (RuntimeRefused,OSError):pass
        time.sleep(.05)
    p.kill();p.wait(timeout=5);_,err=output(p);pytest.fail('NATIVE_ACTIVITY_START_TIMEOUT '+err.decode())


def stop(root,p):
    control(root,'shutdown');p.wait(timeout=10);out,err=output(p)
    assert p.returncode==0 and err==b'',err.decode()
    return json.loads(out)


def activity(root,op,**kw):return control(root,'paper_activity',dict(operation=op,**kw))


def account(root):
    pid=str(uuid4());p=control(root,'paper_read',dict(operation='prepare',packet_id=pid,account_alias='fixture'))
    for op in ('authorize','start'):control(root,'paper_read',dict(operation=op,packet_id=pid,plan_sha256=p['plan_sha256']))
    until=time.monotonic()+25
    while time.monotonic()<until:
        v=control(root,'paper_read',dict(operation='status',packet_id=pid))
        if v['publication']['state']=='PUBLISHED':break
        time.sleep(.025)
    assert v['publication']['state']=='PUBLISHED',v
    health=control(root,'status')
    assert health['watchdog']['status']=='HEALTHY',health['watchdog']
    proposal=control(root,'paper_read',dict(operation='account_propose',packet_id=pid))
    control(root,'paper_read',dict(operation='account_confirm',packet_id=pid,proposal_sha256=proposal['proposal_sha256'],acknowledgement=proposal['required_acknowledgement']))
    return pid


def fixture_root(tmp_path):
    # Explicit shared fixture allows source/installed runs to retain one allocated reserve.
    selected=os.environ.get('COMPERTUM_ACTIVITY_FIXTURE')
    root=Path(selected) if selected else tmp_path
    assert root.is_relative_to(ROOT/'.cache/test-runs') and root.is_dir()
    config=root/'config.toml'
    if config.exists():assert config.read_bytes()==(ROOT/'config/default.toml').read_bytes()
    else:shutil.copyfile(ROOT/'config/default.toml',config)
    lane='source' if str(Path(__import__('compertum').__file__)).startswith(str(ROOT/'src')) else 'installed'
    attempt=os.environ.get('COMPERTUM_ACTIVITY_ATTEMPT','')
    assert not attempt or attempt.isascii() and attempt.isalnum() and len(attempt)<=16
    return root,lane+attempt


def progress(root,lane,phase):
    evidence=root.parent/'native-control-evidence';evidence.mkdir(exist_ok=True)
    with (evidence/f'native-phase-{lane}.jsonl').open('a') as f:
        f.write(json.dumps(dict(phase=phase,monotonic_ns=time.monotonic_ns()))+'\n');f.flush()


def test_native_activity_collection_and_lost_ack(tmp_path):
    root,lane=fixture_root(tmp_path);progress(root,lane,'COLLECTION_LAUNCH')
    p,initial=launch(root,'complete');progress(root,lane,'COLLECTION_HEALTHY')
    receipt=root/f'native-activity-{lane}-collection.json';assert not receipt.exists()
    try:
        reserve=initial['watchdog']['owners']['execution']['reserve']
        assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
        packet=account(root);progress(root,lane,'ACCOUNT_CONFIRMED');aid=str(uuid4());prepared=activity(root,'prepare',activity_id=aid,packet_id=packet)
        for op in ('authorize','start'):activity(root,op,activity_id=aid,plan_sha256=prepared['plan_sha256'])
        until=time.monotonic()+25
        while time.monotonic()<until:
            v=activity(root,'status',activity_id=aid)
            if v['publication']['state'] in {'ACK_UNCONFIRMED','FAILED'}:break
            time.sleep(.025)
        progress(root,lane,'COLLECTION_OBSERVED')
        assert v['state']=='PUBLISHED' and v['publication']['state']=='ACK_UNCONFIRMED',v
        assert v['summary']['pages']==2 and v['summary']['traversal_complete'] and v['summary']['native_closed']
        assert v['summary']['status']=='BLOCKED' and not v['summary']['financial_accepted']
        m=v['manifest'];artifact=root/m['path'];assert hashlib.sha256(artifact.read_bytes()).hexdigest()==m['sha256']
        progress(root,lane,'DUPLICATE_START_BEGIN');activity(root,'start',activity_id=aid,plan_sha256=prepared['plan_sha256'])
        progress(root,lane,'DUPLICATE_START_DONE')
        first=stop(root,p);assert len(first['requests'])==8 and first['lost_start_receipts']==first['lost_activity_acks']==1
        progress(root,lane,'COLLECTION_STOPPED')
        with receipt.open('x') as f:json.dump(dict(complete=first,reserve=reserve,manifest=m,activity_id=aid,packet_id=packet,
            actual_broker_actions=0,account_origin='INVENTED_TEST_ONLY',activity_origin='LOOPBACK_FIXTURE'),f,indent=2)
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=5)


def test_native_activity_restart_ack_without_get(tmp_path):
    root,lane=fixture_root(tmp_path);prior=json.loads((root/f'native-activity-{lane}-collection.json').read_text())
    aid=prior['activity_id'];m=prior['manifest'];progress(root,lane,'RESTART_LAUNCH');p,_=launch(root,'restart')
    try:
        until=time.monotonic()+10
        while time.monotonic()<until:
            restored=activity(root,'status',activity_id=aid)
            if restored['publication']['state']=='PUBLISHED':break
            time.sleep(.025)
        assert restored['publication']['state']=='PUBLISHED' and restored['manifest']==m
        second=stop(root,p);assert second['requests']==[]
        progress(root,lane,'RESTART_STOPPED')
        with (root/f'native-activity-{lane}-restart.json').open('x') as f:json.dump(second,f,indent=2)
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=5)


def test_native_activity_pending_cancellation(tmp_path):
    root,lane=fixture_root(tmp_path);progress(root,lane,'CANCEL_LAUNCH');p,_=launch(root,'cancel')
    try:
        packet2=account(root);cancel_id=str(uuid4())
        c=activity(root,'prepare',activity_id=cancel_id,packet_id=packet2)
        for op in ('authorize','start'):activity(root,op,activity_id=cancel_id,plan_sha256=c['plan_sha256'])
        until=time.monotonic()+5
        while time.monotonic()<until:
            if any(x.startswith('/v2/account/activities') for x in control(root,'status')['fixture_requests']):break
            time.sleep(.025)
        canceled=activity(root,'cancel',activity_id=cancel_id);assert canceled['state']=='CANCELED' and canceled['summary']['native_closed']
        with pytest.raises(RuntimeRefused):activity(root,'start',activity_id=cancel_id,plan_sha256=c['plan_sha256'])
        until=time.monotonic()+10
        while time.monotonic()<until:
            retained=activity(root,'status',activity_id=cancel_id)
            if retained['publication']['state']=='PUBLISHED':break
            time.sleep(.025)
        assert retained['publication']['state']=='PUBLISHED' and retained['summary']['native_closed']
        assert control(root,'status')['watchdog']['status']=='HEALTHY'
        third=stop(root,p);assert len(third['requests'])==7
        progress(root,lane,'CANCEL_STOPPED')
        with (root/f'native-activity-{lane}-cancel.json').open('x') as f:json.dump(dict(cancel=third,activity_id=cancel_id),f,indent=2)
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=5)


def test_native_activity_historical_reopening(tmp_path):
    root,lane=fixture_root(tmp_path);prior=json.loads((root/f'native-activity-{lane}-collection.json').read_text())
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.runtime.paper_activity_evidence import open_activity_evidence
    lease=acquire_owner(resolve_project(root),'execution')
    try:
        with open_activity_evidence(lease,'fixture',prior['activity_id'],prior['manifest']) as opened:
            history=opened.snapshot();assert history['freshness']=='NOT_RESTORED' and history['collection']['provenance']=='LOOPBACK_FIXTURE'
            assert history['collection']['summary']['status']=='BLOCKED'
    finally:release_owner(lease)
