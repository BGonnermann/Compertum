"""Separate bounded evaluation owner records and invalidates synthetic seals."""
import json
import shutil
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.config import load_config
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.managed import launch_owner
from compertum.runtime.owner_rpc import call_owner
from compertum.runtime.errors import RuntimeRefused
from compertum.storage import StorageManager,reserve_runtime_paths
from compertum.evaluation_seals import reserve_seal_append
from compertum.evaluation_protocol import build_protocol
from compertum.runtime.identity_pins import runtime_identity


@pytest.fixture
def state(tmp_path):
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml')
    project=resolve_project(tmp_path);supervisor=acquire_owner(project,'supervisor');coordinator=acquire_owner(project,'coordinator')
    jobs=[]
    try:
        storage=StorageManager(coordinator,load_config(tmp_path/'config.toml',tmp_path));reserve_runtime_paths(storage)
        yield project,supervisor,storage,jobs
    finally:
        for job in jobs:job.close()
        release_owner(coordinator);release_owner(supervisor)


def start(state,role='evaluation'):
    if role=='execution':
        import subprocess,sys,os
        from fixture_processes import python_process
        code="from pathlib import Path; import sys; from compertum.runtime.identity import resolve_project; from compertum.runtime.owners import acquire_owner,release_owner; from compertum.storage import create_journal_reserve; lease=acquire_owner(resolve_project(Path(sys.argv[1])),'execution'); create_journal_reserve(lease,65536); release_owner(lease)"
        child=python_process(['-B','-c',code,str(state[0].root_path)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        out,err=child.communicate(timeout=10)
        assert child.returncode==0,(out,err)
    job,remote=launch_owner(state[1],role);state[3].append(job);return job,remote


def request():
    p=build_protocol(development_run_id=str(uuid4()),development_sha256='a'*64,data_manifest_sha256='b'*64,holdout_manifest_sha256='c'*64,runtime=runtime_identity())
    return {'operation':'create','seal_id':str(uuid4()),'protocol_utf8':p.content.decode(),'protocol_sha256':p.sha256}


def test_native_protocol_rpc_restart_barrier_and_limits(state):
    job,remote=start(state);limits=job.api.limits(job.job)
    assert limits.job_memory==256*1024**2 and limits.basic.active_limit==1 and limits.basic.affinity.bit_count()==1
    payload=request();reserve_seal_append(state[2]);first=call_owner(remote,'synthetic_protocol',payload)
    assert first==call_owner(remote,'synthetic_protocol',payload) and first['status']=='SEALED' and not first['development_admitted']
    barrier=str(uuid4())
    call_owner(remote,'checkpoint',{'operation':'snapshot','barrier_id':barrier,'destination':'backups/fixture.sqlite','maximum_bytes':1024**2})
    with pytest.raises(RuntimeRefused,match='BARRIER_HELD'):call_owner(remote,'synthetic_protocol',payload)
    call_owner(remote,'checkpoint',{'operation':'end','barrier_id':barrier})
    assert call_owner(remote,'synthetic_protocol',{'operation':'inspect','seal_id':payload['seal_id']})==first
    remote.close();job.close();job2,remote2=start(state)
    assert remote2.descriptor.registration.generation>remote.descriptor.registration.generation
    assert call_owner(remote2,'synthetic_protocol',payload)==first
    reserve_seal_append(state[2]);invalid={'operation':'invalidate','seal_id':payload['seal_id'],'reason':'POLICY_CHANGED'}
    result=call_owner(remote2,'synthetic_protocol',invalid)
    assert result['status']=='INVALIDATED' and call_owner(remote2,'synthetic_protocol',invalid)==result
    with pytest.raises(RuntimeRefused,match='SEAL_INVALIDATED'):call_owner(remote2,'synthetic_protocol',payload)


def test_native_wrong_role_and_malformed_payload_do_not_gain_authority(state):
    job,remote=start(state);reserve_seal_append(state[2])
    with pytest.raises(RuntimeRefused):call_owner(remote,'synthetic_protocol',{'operation':'create','seal_id':'bad','protocol_utf8':'{}','protocol_sha256':'a'*64})
    assert call_owner(remote,'status',{})['status']=='HEALTHY'
    other,execution=start(state,'execution')
    with pytest.raises(RuntimeRefused,match='COMMAND_DENIED'):call_owner(execution,'synthetic_protocol',request())


def test_unreserved_append_denied_before_event_is_written(state):
    job,remote=start(state);payload=request()
    with pytest.raises(RuntimeRefused,match='SEAL_STORAGE_UNRESERVED'):call_owner(remote,'synthetic_protocol',payload)
    assert not (state[0].root_path/'state/evaluation-seals/00000001.json').exists()
    reserve_seal_append(state[2]);assert call_owner(remote,'synthetic_protocol',payload)['status']=='SEALED'


def test_reserved_seal_growth_does_not_trip_independent_watchdog(state):
    job,remote=start(state);watch,monitor=start(state,'watchdog')
    assert call_owner(monitor,'status',{})['status']=='HEALTHY'
    reserve_seal_append(state[2]);payload=request();call_owner(remote,'synthetic_protocol',payload)
    # Actual status call triggers initial/elapsed scan; explicit second live scan follows.
    import time
    deadline=time.monotonic()+5
    initial=call_owner(monitor,'status',{})
    while time.monotonic()<deadline:
        result=call_owner(monitor,'status',{})
        if result['observed_monotonic']>initial['observed_monotonic']:break
        time.sleep(.1)
    assert result['observed_monotonic']>initial['observed_monotonic'] and result['status']=='HEALTHY'


def test_malformed_native_reply_still_retires_channel(state,monkeypatch):
    import compertum.runtime.owner_rpc as rpc
    job,remote=start(state);actual=rpc._record
    def corrupt(raw,fields,maximum):
        value=actual(raw,fields,maximum);value['sequence']+=1;return value
    monkeypatch.setattr(rpc,'_record',corrupt)
    with pytest.raises(RuntimeRefused,match='OWNER_CHANNEL_DENIED'):call_owner(remote,'status',{})
    assert remote.closed
