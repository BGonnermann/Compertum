"""Stage E2: escape attempts from the AppContainer sandbox must fail. Positive controls must pass.

Every test here launches a real Windows AppContainer process. Nothing is simulated.
One probe run is shared by the control tests; each resource test launches its own job.
"""
from datetime import date
import json
from pathlib import Path
import shutil
import time
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.sandbox import (CONTROLS,PROFILE_NAME,PROFILE_PREFIX,Profile,SandboxAPI,SandboxResult,controls_from,packages_folder,
                                       remove_stale_profile,require_verified,run_sandboxed,stale_profiles,verify_sandbox)

FLOOR=8*1024**3
MIB=1024**2
PROJECT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def root():
    folder=PROJECT/'.cache'/'test-runs'/f'e2-sandbox-{date.today():%Y%m%d}-{uuid4().hex[:8]}'
    folder.mkdir(parents=True)
    yield folder
    shutil.rmtree(folder,ignore_errors=True)


@pytest.fixture(scope='module')
def verification(root):
    return verify_sandbox(root,memory_floor_bytes=FLOOR)


def job(root,source,**files):
    folder=root/f'job-{uuid4().hex[:8]}';folder.mkdir()
    (folder/'main.py').write_text(source,encoding='utf-8')
    for name,text in files.items(): (folder/name).write_text(text,encoding='utf-8')
    return folder


def run(root,folder,*,seconds=30,memory=128*MIB,**kw):
    return run_sandboxed(root,folder,['main.py'],seconds=seconds,memory_bytes=memory,memory_floor_bytes=FLOOR,**kw)


def control(verification,name):
    assert name in CONTROLS
    assert verification['controls'][name],json.dumps({'control':name,'report':verification['report'],'result':verification['result']},indent=1)


def test_probe_runs_in_an_appcontainer_at_low_integrity(verification):
    control(verification,'appcontainer_token');control(verification,'low_integrity')
    assert verification['result']['exit_code'] in (0,0xC0000017,0xC000012D) or verification['report'].get('allocate',{}).get('ok') is False


def test_external_network_is_denied(verification):
    control(verification,'external_network_denied')
    assert verification['report']['external_connect']['error']=='PermissionError'


def test_loopback_network_is_denied(verification):
    # Section 19: the job has no network access. Loopback reaches the model server, so it must be denied too.
    control(verification,'loopback_denied');control(verification,'loopback_unseen_by_listener')


def test_read_outside_the_job_folder_is_denied(verification):
    control(verification,'outside_read_denied')
    assert verification['report']['outside_read']['error']=='PermissionError'


def test_write_outside_the_job_folder_is_denied(verification):
    control(verification,'outside_write_denied');control(verification,'outside_file_absent')


def test_write_inside_the_job_folder_is_allowed(verification):
    control(verification,'inside_write_allowed')


def test_an_earlier_job_folder_is_not_readable_by_the_next_job(verification,root):
    # The identity is the same for every job, so the grant on a finished job folder must be gone.
    control(verification,'previous_job_read_denied')
    first=job(root,"open('inside.txt','w').write('first')\n")
    assert run(root,first).exit_code==0
    second=job(root,'import json\nwith open("targets.json") as s: target=json.load(s)["path"]\nopen(target).read()\n',**{'targets.json':json.dumps({'path':str(first/'inside.txt')})})
    result=run(root,second)
    assert result.exit_code==1 and b'PermissionError' in result.stderr,result.stderr
    assert (first/'inside.txt').read_text()=='first'


def test_controls_do_not_pass_on_the_wrong_error():
    done=SandboxResult('j','S-1-15-2-1',1,0,False,.1,1,1,0,False,b'',b'')
    good={'token':{'ok':True,'value':{'is_appcontainer':1,'integrity_level':4096}},
          'external_connect':{'ok':False,'error':'PermissionError','detail':'10013'},'loopback_connect':{'ok':False,'error':'PermissionError','detail':'10013'},
          'outside_read':{'ok':False,'error':'PermissionError','detail':''},'outside_write':{'ok':False,'error':'PermissionError','detail':''},
          'previous_read':{'ok':False,'error':'PermissionError','detail':''},'inside_write':{'ok':True,'value':2},
          'child_process':{'ok':False,'error':'OSError','detail':'[WinError 1816] Not enough quota'},'allocate':{'ok':False,'error':'MemoryError','detail':''}}
    all_true=controls_from(good,done,listener_saw_connection=False,escape_exists=False,inside_written=True)
    assert set(all_true)==set(CONTROLS) and all(all_true.values())
    wrong={**good,'external_connect':{'ok':False,'error':'TimeoutError','detail':''},'outside_read':{'ok':False,'error':'FileNotFoundError','detail':''},
           'child_process':{'ok':False,'error':'FileNotFoundError','detail':''},'loopback_connect':{'ok':False,'error':'ConnectionRefusedError','detail':''}}
    bad=controls_from(wrong,done,listener_saw_connection=True,escape_exists=True,inside_written=False)
    assert sorted(k for k,v in bad.items() if not v)==['child_process_denied','external_network_denied','inside_write_allowed','loopback_denied',
                                                        'loopback_unseen_by_listener','outside_file_absent','outside_read_denied']
    killed={k:v for k,v in good.items() if k!='allocate'}
    assert controls_from(killed,SandboxResult('j','S',1,0xC0000017,False,.1,1,1,0,False,b'',b''),listener_saw_connection=False,escape_exists=False,inside_written=True)['memory_limit_enforced']
    assert not controls_from(killed,SandboxResult('j','S',1,124,True,.1,1,1,0,False,b'',b''),listener_saw_connection=False,escape_exists=False,inside_written=True)['memory_limit_enforced']
    assert not controls_from(killed,done,listener_saw_connection=False,escape_exists=False,inside_written=True)['memory_limit_enforced']


def test_child_process_is_denied(verification):
    control(verification,'child_process_denied')


def test_memory_limit_is_enforced(verification):
    control(verification,'memory_limit_enforced')


def test_require_verified_names_every_failed_control(verification):
    passing={'controls':{name:True for name in CONTROLS},'failed':[]}
    assert require_verified(passing) is True
    failing={'controls':{name:name not in ('loopback_denied','outside_read_denied') for name in CONTROLS},'failed':['loopback_denied','outside_read_denied']}
    with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED:loopback_denied,outside_read_denied$'): require_verified(failing)
    for bad in ({},{'controls':{},'failed':[]},{'controls':passing['controls']},None):
        with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED$'): require_verified(bad)
    disagreeing={'controls':{name:name!='outside_read_denied' for name in CONTROLS},'failed':[]}
    with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED:outside_read_denied$'): require_verified(disagreeing)
    if verification['failed']:
        with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED:'): require_verified(verification)
    else: assert require_verified(verification) is True


def test_deadline_terminates_the_job(root):
    folder=job(root,'import time\ntime.sleep(60)\n')
    started=time.monotonic();result=run(root,folder,seconds=2)
    assert result.timed_out is True and result.exit_code==124 and time.monotonic()-started<15


def test_disk_overrun_is_flagged_and_normal_use_is_not(root):
    folder=job(root,"open('big.bin','wb').write(b'x'*(3*1024*1024))\n")
    result=run(root,folder,disk_bytes=MIB)
    assert result.exit_code==0 and result.disk_overrun is True and result.job_folder_bytes>=3*MIB
    folder=job(root,"open('small.bin','wb').write(b'x'*1024)\n")
    result=run(root,folder,disk_bytes=MIB)
    assert result.exit_code==0 and result.disk_overrun is False


def test_environment_holds_three_windows_variables_and_nothing_inherited(root):
    folder=job(root,'import json,os,sys\nprint(json.dumps({"env":sorted(os.environ),"argv":sys.argv,"isolated":sys.flags.isolated,"cwd":os.getcwd()}))\n')
    result=run(root,folder)
    assert result.exit_code==0,result.stderr
    seen=json.loads(result.stdout)
    assert seen['env']==sorted(['SYSTEMROOT','WINDIR','LOCALAPPDATA','TEMP','TMP','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','PYTHONIOENCODING'])
    assert seen['isolated']==1 and Path(seen['cwd'])==folder.resolve() and seen['argv']==['main.py']


def test_stderr_and_exit_code_are_captured(root):
    result=run(root,job(root,'raise SystemExit(7)\n'))
    assert result.exit_code==7
    result=run(root,job(root,'open("missing.txt")\n'))
    assert result.exit_code==1 and b'Traceback' in result.stderr and b'FileNotFoundError' in result.stderr


def test_each_job_gets_a_fresh_profile_with_the_same_identity_and_no_state_survives(root):
    package=packages_folder()/PROFILE_NAME
    # Inside the container Windows points LOCALAPPDATA at the package's own AC folder, which the container may write.
    listing='import os\nfolder=os.environ["LOCALAPPDATA"]\nassert folder.lower().endswith(r"packages\\%s\\ac"),folder\n'%PROFILE_NAME.lower()
    first=run(root,job(root,listing+'open(os.path.join(folder,"persist.txt"),"w").write("x"*2048)\nprint(sorted(os.listdir(folder)))\n'))
    assert first.exit_code==0,first.stderr
    assert first.sid.startswith('S-1-15-2-') and first.package_folder_bytes>=2048 and b'persist.txt' in first.stdout
    assert not package.exists() and PROFILE_NAME.lower() not in stale_profiles()
    second=run(root,job(root,listing+'print(sorted(os.listdir(folder)))\n'))
    assert second.exit_code==0,second.stderr
    assert second.sid==first.sid and second.job_id!=first.job_id and b'persist.txt' not in second.stdout and second.package_folder_bytes<2048
    assert not package.exists()


def test_record_is_plain_json_with_fixed_fields(root):
    record=run(root,job(root,'print("x"*10)\n')).record()
    assert set(record)=={'job_id','sid','pid','exit_code','timed_out','elapsed_seconds','peak_process_bytes','job_folder_bytes','package_folder_bytes','disk_overrun','stdout_bytes','stderr_bytes'}
    assert record['stdout_bytes']==12 and record['peak_process_bytes']>0 and json.loads(json.dumps(record))==record


def test_output_capture_is_bounded_and_a_junction_in_the_job_folder_is_not_followed(root):
    result=run(root,job(root,'import sys\nsys.stdout.write("y"*200000)\n'))
    assert result.exit_code==0 and len(result.stdout)==65536
    folder=job(root,'import subprocess\n')
    (folder/'main.py').write_text('print("junction")\n',encoding='utf-8')
    import _winapi
    _winapi.CreateJunction(str(Path(__import__('os').environ['WINDIR'])),str(folder/'escape-junction'))
    assert (folder/'escape-junction').is_junction()
    result=run(root,folder,disk_bytes=MIB)
    assert result.exit_code==0 and result.disk_overrun is False and result.job_folder_bytes<MIB


def test_refusals_happen_before_any_process_exists(root):
    folder=job(root,'print(1)\n');nested=folder/'inner';nested.mkdir();(nested/'main.py').write_text('print(1)\n',encoding='utf-8')
    before=set(stale_profiles())
    cases=[(dict(root=root,job_dir=root.parent,argv=['main.py']),'SANDBOX_FOLDER_DENIED'),
           (dict(root=root,job_dir=nested,argv=['main.py']),'SANDBOX_FOLDER_DENIED'),
           (dict(root=root,job_dir=root/'absent',argv=['main.py']),'SANDBOX_FOLDER_DENIED'),
           (dict(root=root,job_dir=folder,argv=[str(folder/'main.py')]),'SANDBOX_ARGV_DENIED'),
           (dict(root=root,job_dir=folder,argv=['../main.py']),'SANDBOX_ARGV_DENIED'),
           (dict(root=root,job_dir=folder,argv=['-c','pass']),'SANDBOX_ARGV_DENIED'),
           (dict(root=root,job_dir=folder,argv=['absent.py']),'SANDBOX_ARGV_DENIED'),
           (dict(root=root,job_dir=folder,argv=['inner/main.py']),'SANDBOX_ARGV_DENIED'),
           (dict(root=root,job_dir=folder,argv=[]),'SANDBOX_ARGV_DENIED'),
           (dict(root=root,job_dir=folder,argv=['main.py'],seconds=0),'SANDBOX_DEADLINE_DENIED'),
           (dict(root=root,job_dir=folder,argv=['main.py'],memory_bytes=MIB),'SANDBOX_MEMORY_DENIED'),
           (dict(root=root,job_dir=folder,argv=['main.py'],disk_bytes=0),'SANDBOX_DISK_DENIED'),
           (dict(root=root,job_dir=folder,argv=['main.py'],available_memory=lambda:FLOOR-1),'AVAILABLE_RAM_FLOOR')]
    for overrides,code in cases:
        kw=dict(seconds=30,memory_bytes=128*MIB,memory_floor_bytes=FLOOR);kw.update(overrides)
        with pytest.raises(RuntimeRefused,match=f'^{code}$'): run_sandboxed(**kw)
    assert set(stale_profiles())==before


def test_profile_names_are_fixed_and_stale_profiles_are_listed_then_removed():
    api=SandboxAPI()
    for name in ('Other.Name','',PROFILE_PREFIX+'.bad/name',PROFILE_PREFIX+'.'+'x'*80,None):
        with pytest.raises(RuntimeRefused,match='^SANDBOX_PROFILE_NAME_DENIED$'): Profile(api,name)
    name=f'{PROFILE_PREFIX}.stale{uuid4().hex[:6]}'
    profile=Profile(api,name)
    try:
        assert profile.folder.is_dir() and name.lower() in stale_profiles()
        with pytest.raises(RuntimeRefused,match='^SANDBOX_PROFILE_EXISTS$'): Profile(api,name)
    finally:
        api.FreeSid(profile.sid);profile.sid=None
    remove_stale_profile(api,name)
    assert name.lower() not in stale_profiles() and not profile.folder.exists()
    with pytest.raises(RuntimeRefused,match='^SANDBOX_PROFILE_UNKNOWN$'): remove_stale_profile(api,name)
    with pytest.raises(RuntimeRefused,match='^SANDBOX_PROFILE_UNKNOWN$'): remove_stale_profile(api,None)
