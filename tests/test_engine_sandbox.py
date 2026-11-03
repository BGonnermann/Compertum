"""Stage E2: escape attempts from the AppContainer sandbox must fail. Positive controls must pass.

Every test here launches a real Windows AppContainer process. Nothing is simulated.
One probe run is shared by the control tests; each resource test launches its own job.
"""
from datetime import date
import json
from multiprocessing.connection import Listener
from pathlib import Path
import shutil
import socket
import threading
import time
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.sandbox import (CONTROLS,OBSERVATIONS,PROFILE_NAME,PROFILE_PREFIX,LoopbackWatcher,Profile,SandboxAPI,SandboxResult,
                                       controls_from,fixed_target_paths,observations_from,packages_folder,remove_stale_profile,require_verified,
                                       run_sandboxed,stale_profiles,verify_sandbox)

FLOOR=8*1024**3
MIB=1024**2
PROJECT=Path(__file__).resolve().parents[1]
# Real fixed parts (section 19): the rules and the fixed configuration. The ledger database is added when it exists.
FIXED_TARGETS=[PROJECT/'docs/BUILD_SPEC.md',PROJECT/'AGENTS.md',PROJECT/'config/default.toml']+[p for p in [PROJECT/'state/research.sqlite'] if p.is_file()]


@pytest.fixture(scope='module')
def root():
    folder=PROJECT/'.cache'/'test-runs'/f'e2-sandbox-{date.today():%Y%m%d}-{uuid4().hex[:8]}'
    folder.mkdir(parents=True)
    yield folder
    shutil.rmtree(folder,ignore_errors=True)


@pytest.fixture(scope='module')
def verification(root):
    # A live named pipe server stands in for the owner pipe. The probe must fail to open it.
    pipe=r'\\.\pipe\compertum-e2-'+uuid4().hex[:8]
    listener=Listener(pipe,'AF_PIPE')
    try: return verify_sandbox(root,memory_floor_bytes=FLOOR,fixed_targets=FIXED_TARGETS,pipe=pipe)
    finally: listener.close()


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


def test_appcontainer_probe(verification):
    control(verification,'appcontainer_token');control(verification,'low_integrity')
    assert verification['result']['exit_code'] in (0,0xC0000017,0xC000012D) or verification['report'].get('allocate',{}).get('ok') is False


def test_external_network(verification):
    control(verification,'external_network_denied')
    assert verification['report']['external_connect']['error']=='PermissionError'


def test_loopback_recorded(verification):
    # Owner decision, 23 October 2026 (option 1): loopback reachability is a documented limitation on this host.
    # The probe still tries loopback, the result is recorded with every verification, and it never passes or fails the gate.
    assert not any(name.startswith('loopback') for name in CONTROLS) and set(verification['observations'])==set(OBSERVATIONS)
    assert 'loopback_connect' in verification['report']
    observed=verification['observations']
    assert all(type(value) is bool for value in observed.values())
    assert observed['loopback_seen_by_listener']<=observed['loopback_connected'],observed  # the listener cannot see a connection the probe did not make
    assert observations_from({},listener_saw_connection=False)=={'loopback_connected':False,'loopback_seen_by_listener':False}
    assert observations_from({'loopback_connect':{'ok':True,'value':'CONNECTED'}},listener_saw_connection=True)=={'loopback_connected':True,'loopback_seen_by_listener':True}


def test_outside_read(verification):
    control(verification,'outside_read_denied')
    assert verification['report']['outside_read']['error']=='PermissionError'


def test_outside_write(verification):
    control(verification,'outside_write_denied');control(verification,'outside_file_absent')


def test_inside_write(verification):
    control(verification,'inside_write_allowed')


def test_fixed_unreadable(verification):
    # Section 19: the job cannot read the ledger or write the rules. The real files are the targets, not stand-ins.
    control(verification,'fixed_targets_read_denied');control(verification,'pipe_open_denied')
    assert verification['fixed_targets']==[str(p) for p in FIXED_TARGETS] and len(FIXED_TARGETS)>=3
    for index in range(len(FIXED_TARGETS)):
        assert verification['report'][f'fixed_read_{index}']['error']=='PermissionError'
    assert verification['report']['pipe_open']['error']=='PermissionError' and verification['pipe'].startswith(r'\\.\pipe\compertum-e2-')


def test_target_refusals(root):
    bad=[[Path('relative.txt')],[root/'absent.txt'],[root],[PROJECT/'AGENTS.md']*2,[PROJECT/'AGENTS.md']*17,'AGENTS.md',[42]]
    for targets in bad:
        with pytest.raises(RuntimeRefused,match='^SANDBOX_TARGETS_DENIED$'): fixed_target_paths(targets)
    assert fixed_target_paths(())==[] and fixed_target_paths([PROJECT/'AGENTS.md'])==[str(PROJECT/'AGENTS.md')]
    with pytest.raises(RuntimeRefused,match='^SANDBOX_TARGETS_DENIED$'): verify_sandbox(root,memory_floor_bytes=FLOOR,pipe='not-a-pipe')


def test_loopback_watcher(root):
    # Loopback is reachable on this host (owner decision, option 1). The watcher is the compensating control, so it must see it.
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(20);port=listener.getsockname()[1]
    def accept():
        try: connection,_=listener.accept();time.sleep(.3);connection.close()
        except OSError: pass
    waiter=threading.Thread(target=accept,daemon=True);waiter.start()
    source=f'import socket,time\ns=socket.socket()\ns.settimeout(5)\ntry:\n    s.connect(("127.0.0.1",{port}));time.sleep(.3);print("CONNECTED")\nexcept OSError as e: print("DENIED",e)\ns.close()\n'
    watcher=LoopbackWatcher()
    try: result=run(root,job(root,source),watcher=watcher)
    finally: listener.close();waiter.join(timeout=3)
    record=watcher.record()
    assert record['pid']==result.pid and record['verified'] is True and record['samples']>=2 and record['error'] is None
    if b'CONNECTED' in result.stdout:
        assert any(c['remote_port']==port and c['remote_address']=='127.0.0.1' for c in record['loopback_connections']),record
    else: assert record['loopback_connections']==[]  # a host that denies loopback has nothing to catch
    quiet=LoopbackWatcher();result=run(root,job(root,'print(1)\n'),watcher=quiet)
    assert result.exit_code==0 and quiet.record()['loopback_connections']==[] and quiet.record()['verified'] is True
    with pytest.raises(RuntimeRefused,match='^SANDBOX_WATCHER_DENIED$'): run(root,job(root,'print(1)\n'),watcher=object())
    for pid in (0,-1,'7',None):
        with pytest.raises(RuntimeRefused,match='^SANDBOX_WATCHER_DENIED$'): LoopbackWatcher().start(pid)
    started=LoopbackWatcher();started.start(1)
    try:
        with pytest.raises(RuntimeRefused,match='^SANDBOX_WATCHER_DENIED$'): started.start(1)
    finally: started.stop()
    with pytest.raises(RuntimeRefused,match='^SANDBOX_WATCHER_DENIED$'): LoopbackWatcher(interval=0)
    # Classification: IPv4, IPv6 and IPv4-mapped loopback count; a listener or a closed row does not; another host does not.
    crafted=LoopbackWatcher();rows={('ipv4','127.0.0.1',5000,'127.0.0.1',41343):[5],('ipv6','::1',5001,'::1',80):[5],('ipv6','::ffff:127.0.0.1',5002,'::ffff:127.0.0.1',81):[5],
                                    ('ipv4','0.0.0.0',5003,'0.0.0.0',0):[2],('ipv4','127.0.0.1',5004,'127.0.0.1',82):[1],('ipv4','192.168.1.5',5005,'10.0.0.1',443):[5]}
    crafted.connections={k:{'family':k[0],'local_address':k[1],'local_port':k[2],'remote_address':k[3],'remote_port':k[4],'states':v} for k,v in rows.items()}
    assert sorted(c['remote_port'] for c in crafted.loopback_connections())==[80,81,41343]


def test_earlier_folder(verification,root):
    # The identity is the same for every job, so the grant on a finished job folder must be gone.
    control(verification,'previous_job_read_denied')
    first=job(root,"open('inside.txt','w').write('first')\n")
    assert run(root,first).exit_code==0
    second=job(root,'import json\nwith open("targets.json") as s: target=json.load(s)["path"]\nopen(target).read()\n',**{'targets.json':json.dumps({'path':str(first/'inside.txt')})})
    result=run(root,second)
    assert result.exit_code==1 and b'PermissionError' in result.stderr,result.stderr
    assert (first/'inside.txt').read_text()=='first'


def test_wrong_error():
    done=SandboxResult('j','S-1-15-2-1',1,0,False,.1,1,1,0,False,b'',b'')
    good={'token':{'ok':True,'value':{'is_appcontainer':1,'integrity_level':4096}},
          'external_connect':{'ok':False,'error':'PermissionError','detail':'10013'},'loopback_connect':{'ok':False,'error':'PermissionError','detail':'10013'},
          'outside_read':{'ok':False,'error':'PermissionError','detail':''},'outside_write':{'ok':False,'error':'PermissionError','detail':''},
          'previous_read':{'ok':False,'error':'PermissionError','detail':''},'inside_write':{'ok':True,'value':2},
          'child_process':{'ok':False,'error':'OSError','detail':'[WinError 1816] Not enough quota'},'allocate':{'ok':False,'error':'MemoryError','detail':''},
          'fixed_read_0':{'ok':False,'error':'PermissionError','detail':''},'fixed_read_1':{'ok':False,'error':'PermissionError','detail':''},
          'pipe_open':{'ok':False,'error':'PermissionError','detail':''}}
    ok=dict(escape_exists=False,inside_written=True,fixed_count=2,pipe_given=True)
    all_true=controls_from(good,done,**ok)
    assert set(all_true)==set(CONTROLS) and len(CONTROLS)==12 and all(all_true.values())
    wrong={**good,'external_connect':{'ok':False,'error':'TimeoutError','detail':''},'outside_read':{'ok':False,'error':'FileNotFoundError','detail':''},
           'child_process':{'ok':False,'error':'FileNotFoundError','detail':''},'fixed_read_1':{'ok':False,'error':'FileNotFoundError','detail':''},
           'pipe_open':{'ok':False,'error':'FileNotFoundError','detail':''}}
    bad=controls_from(wrong,done,escape_exists=True,inside_written=False,fixed_count=2,pipe_given=True)
    assert sorted(k for k,v in bad.items() if not v)==['child_process_denied','external_network_denied','fixed_targets_read_denied','inside_write_allowed',
                                                        'outside_file_absent','outside_read_denied','pipe_open_denied']
    # No targets and no pipe prove nothing, so those two controls fail even on a perfect report.
    empty=controls_from(good,done,escape_exists=False,inside_written=True,fixed_count=0,pipe_given=False)
    assert sorted(k for k,v in empty.items() if not v)==['fixed_targets_read_denied','pipe_open_denied']
    assert not controls_from(good,done,escape_exists=False,inside_written=True,fixed_count=3,pipe_given=True)['fixed_targets_read_denied']  # a missing third target
    assert set(controls_from({**good,'loopback_connect':{'ok':True,'value':'CONNECTED'}},done,**ok).values())=={True}
    killed={k:v for k,v in good.items() if k!='allocate'}
    assert controls_from(killed,SandboxResult('j','S',1,0xC0000017,False,.1,1,1,0,False,b'',b''),**ok)['memory_limit_enforced']
    assert not controls_from(killed,SandboxResult('j','S',1,124,True,.1,1,1,0,False,b'',b''),**ok)['memory_limit_enforced']
    assert not controls_from(killed,done,**ok)['memory_limit_enforced']


def test_child_process(verification):
    control(verification,'child_process_denied')


def test_memory_limit(verification):
    control(verification,'memory_limit_enforced')


def test_failed_controls(verification):
    passing={'controls':{name:True for name in CONTROLS},'failed':[]}
    assert require_verified(passing) is True
    failing={'controls':{name:name not in ('child_process_denied','outside_read_denied') for name in CONTROLS},'failed':['child_process_denied','outside_read_denied']}
    with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED:child_process_denied,outside_read_denied$'): require_verified(failing)
    for bad in ({},{'controls':{},'failed':[]},{'controls':passing['controls']},None):
        with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED$'): require_verified(bad)
    stale={'controls':{**passing['controls'],'loopback_denied':True},'failed':[]}  # a verification from before the owner decision does not fit the gate
    with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED$'): require_verified(stale)
    disagreeing={'controls':{name:name!='outside_read_denied' for name in CONTROLS},'failed':[]}
    with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED:outside_read_denied$'): require_verified(disagreeing)
    assert verification['failed']==[],verification['failed']
    assert require_verified(verification) is True


def test_job_deadline(root):
    folder=job(root,'import time\ntime.sleep(60)\n')
    started=time.monotonic();result=run(root,folder,seconds=2)
    assert result.timed_out is True and result.exit_code==124 and time.monotonic()-started<15


def test_disk_overrun(root):
    folder=job(root,"open('big.bin','wb').write(b'x'*(3*1024*1024))\n")
    result=run(root,folder,disk_bytes=MIB)
    assert result.exit_code==0 and result.disk_overrun is True and result.job_folder_bytes>=3*MIB
    folder=job(root,"open('small.bin','wb').write(b'x'*1024)\n")
    result=run(root,folder,disk_bytes=MIB)
    assert result.exit_code==0 and result.disk_overrun is False


def test_job_environment(root):
    folder=job(root,'import json,os,sys\nprint(json.dumps({"env":sorted(os.environ),"argv":sys.argv,"isolated":sys.flags.isolated,"cwd":os.getcwd()}))\n')
    result=run(root,folder)
    assert result.exit_code==0,result.stderr
    seen=json.loads(result.stdout)
    assert seen['env']==sorted(['SYSTEMROOT','WINDIR','LOCALAPPDATA','TEMP','TMP','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','PYTHONIOENCODING'])
    assert seen['isolated']==1 and Path(seen['cwd'])==folder.resolve() and seen['argv']==['main.py']


def test_stderr_capture(root):
    result=run(root,job(root,'raise SystemExit(7)\n'))
    assert result.exit_code==7
    result=run(root,job(root,'open("missing.txt")\n'))
    assert result.exit_code==1 and b'Traceback' in result.stderr and b'FileNotFoundError' in result.stderr


def test_fresh_profile(root):
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


def test_job_record(root):
    record=run(root,job(root,'print("x"*10)\n')).record()
    assert set(record)=={'job_id','sid','pid','exit_code','timed_out','elapsed_seconds','peak_process_bytes','job_folder_bytes','package_folder_bytes','disk_overrun','stdout_bytes','stderr_bytes'}
    assert record['stdout_bytes']==12 and record['peak_process_bytes']>0 and json.loads(json.dumps(record))==record


def test_output_bounds(root):
    result=run(root,job(root,'import sys\nsys.stdout.write("y"*200000)\n'))
    assert result.exit_code==0 and len(result.stdout)==65536
    folder=job(root,'import subprocess\n')
    (folder/'main.py').write_text('print("junction")\n',encoding='utf-8')
    import _winapi
    _winapi.CreateJunction(str(Path(__import__('os').environ['WINDIR'])),str(folder/'escape-junction'))
    assert (folder/'escape-junction').is_junction()
    result=run(root,folder,disk_bytes=MIB)
    assert result.exit_code==0 and result.disk_overrun is False and result.job_folder_bytes<MIB


def test_early_refusals(root):
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


def test_stale_profiles():
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


def test_heavy_slot(tmp_path):
    # Section 19: one heavy job at a time. The engine takes the same slot as the campaign launcher.
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.jobs import hold_job_slot,job_slot_busy
    from compertum.runtime.owners import acquire_owner,release_owner
    lease=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        assert job_slot_busy(lease) is False
        with hold_job_slot(lease,'e3-engineer-job') as hold:
            assert job_slot_busy(lease) is True and hold.purpose=='e3-engineer-job'
            with pytest.raises(RuntimeRefused,match='^JOB_SLOT_BUSY$'):
                with hold_job_slot(lease,'second'): pass
            assert job_slot_busy(lease) is True
        assert job_slot_busy(lease) is False
        for purpose in ('',None,'x'*129):
            with pytest.raises(RuntimeRefused,match='^JOB_ADMISSION_DENIED$'):
                with hold_job_slot(lease,purpose): pass
        try:
            with hold_job_slot(lease,'failing'): raise KeyError('inside')
        except KeyError: pass
        assert job_slot_busy(lease) is False
    finally: release_owner(lease)


def test_slot_names():
    """Slot 0 keeps the original profile name; each slot gets its own profile and its own CPU from the affinity mask."""
    from compertum.runtime.sandbox import SLOTS,slot_core,slot_profile
    assert SLOTS==3 and slot_profile(0)==PROFILE_NAME and slot_profile(1)==PROFILE_NAME+'.s1' and slot_profile(2)==PROFILE_NAME+'.s2'
    for bad in (-1,3,'0',None,True):
        with pytest.raises(RuntimeRefused,match='^SANDBOX_SLOT_DENIED$'): slot_profile(bad)
    assert [slot_core(0b1011,s) for s in range(3)]==[0b1,0b1000,0b10] and [slot_core(0b110,s) for s in range(3)]==[0b10,0b10,0b10]
    assert [slot_core((1<<16)-1,s) for s in range(3)]==[0b1,0b100,0b10000]
    with pytest.raises(RuntimeRefused,match='^JOB_LIMITS_UNVERIFIED$'): slot_core(0,0)


SLOT_JOB='''import ctypes,json,os,time
with open('targets.json',encoding='utf-8') as f: others=json.load(f)
time.sleep(2)
reads=[]
for path in others:
    try:
        with open(path,encoding='utf-8') as f: reads.append(f.read())
    except OSError as error: reads.append(type(error).__name__)
mask=ctypes.c_size_t();system=ctypes.c_size_t();kernel=ctypes.windll.kernel32
kernel.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
kernel.GetProcessAffinityMask(ctypes.c_void_p(-1),ctypes.byref(mask),ctypes.byref(system))
with open('report.json','w',encoding='utf-8') as f: json.dump({'reads':reads,'local':os.environ['LOCALAPPDATA'],'mask':mask.value},f)
'''


def test_concurrent_slots(root):
    """Three jobs run at the same time in three slots: each finishes, each has its own profile and CPU, and none can read another's folder."""
    import threading,time
    from compertum.runtime.sandbox import SLOTS,slot_profile
    folders=[job(root,SLOT_JOB) for _ in range(SLOTS)]
    for folder in folders: (folder/'secret.txt').write_text('secret of '+folder.name,encoding='utf-8')
    for i,folder in enumerate(folders): (folder/'targets.json').write_text(json.dumps([str(f/'secret.txt') for j,f in enumerate(folders) if j!=i]),encoding='utf-8')
    results=[None]*SLOTS
    def work(i): results[i]=run(root,folders[i],seconds=30,slot=i)
    started=time.monotonic();threads=[threading.Thread(target=work,args=(i,)) for i in range(SLOTS)]
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed=time.monotonic()-started
    assert all(r is not None and r.exit_code==0 and not r.timed_out for r in results),[None if r is None else r.stderr for r in results]
    assert elapsed<5.5,elapsed
    reports=[json.loads((f/'report.json').read_text(encoding='utf-8')) for f in folders]
    assert all(read=='PermissionError' for r in reports for read in r['reads']),reports
    assert [r['local'].lower().endswith('packages\\%s\\ac'%slot_profile(i).lower()) for i,r in enumerate(reports)]==[True]*SLOTS,reports
    assert len({r['mask'] for r in reports})==SLOTS and all(bin(r['mask']).count('1')==1 for r in reports)
    assert not any(slot_profile(i).lower() in stale_profiles() for i in range(SLOTS))


def test_verify_slots(root):
    """Every slot is verified at run start; the merged result fails when any slot fails."""
    from compertum.runtime.sandbox import SLOTS,verify_slots
    pipe=r'\\.\pipe\compertum-slots-'+uuid4().hex[:8];listener=Listener(pipe,'AF_PIPE')
    try: merged=verify_slots(root,memory_floor_bytes=FLOOR,fixed_targets=FIXED_TARGETS,pipe=pipe)
    finally: listener.close()
    assert merged['failed']==[] and set(merged['controls'])==set(CONTROLS) and all(merged['controls'].values()),merged['failed']
    assert [s['slot'] for s in merged['slots']]==list(range(SLOTS)) and all(s['failed']==[] for s in merged['slots'])
    require_verified(merged)


def test_engine_slots(tmp_path,monkeypatch):
    """Up to SLOTS Engineer jobs at once; tool, Auditor and vault jobs alone; the engine holds the one heavy-job slot while any job runs;
    an outside holder or another lease is refused, and every refusal returns the slot."""
    import threading,time
    from compertum.ai.engine import execution
    from compertum.ai.engine.execution import engine_slot
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.jobs import hold_job_slot,job_slot_busy
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.runtime.sandbox import SLOTS
    def until(check,seconds=5):
        end=time.monotonic()+seconds
        while not check():
            assert time.monotonic()<end,'timed out'
            time.sleep(0.01)
    lease=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        assert execution.FREE==list(range(SLOTS)) and job_slot_busy(lease) is False
        gate=threading.Event();taken=[];events=[]
        def engineer():
            with engine_slot(lease,'engineer') as slot:
                taken.append(slot);gate.wait(5)
        def alone(name):
            with engine_slot(lease,'audit') as slot: events.append((name,slot,len(execution.FREE)))
        threads=[threading.Thread(target=engineer) for _ in range(SLOTS)]
        for thread in threads: thread.start()
        until(lambda:len(taken)==SLOTS)
        assert sorted(taken)==list(range(SLOTS)) and execution.FREE==[] and job_slot_busy(lease) is True
        audit=threading.Thread(target=alone,args=('audit',));audit.start()
        time.sleep(0.2);assert events==[]
        gate.set()
        for thread in threads: thread.join(5)
        audit.join(5);assert events==[('audit',0,0)]
        assert execution.FREE==list(range(SLOTS)) and job_slot_busy(lease) is False
        hold=threading.Event();release=threading.Event();late=[]
        def tool():
            with engine_slot(lease,'tool'): hold.set();release.wait(5)
        first=threading.Thread(target=tool);first.start();until(hold.is_set)
        def engineer_late():
            with engine_slot(lease,'engineer'): late.append(True)
        second=threading.Thread(target=engineer_late);second.start()
        time.sleep(0.2);assert late==[]
        release.set();first.join(5);second.join(5);assert late==[True]
        with hold_job_slot(lease,'campaign'):
            with pytest.raises(RuntimeRefused,match='^JOB_SLOT_BUSY$'):
                with engine_slot(lease,'engineer'): pass
        assert execution.FREE==list(range(SLOTS)) and job_slot_busy(lease) is False
        busy=threading.Event();stop=threading.Event()
        def keep():
            with engine_slot(lease,'engineer'): busy.set();stop.wait(5)
        holder=threading.Thread(target=keep);holder.start();until(busy.is_set)
        stranger=type('Lease',(),{'project_id':lease.project_id})()
        monkeypatch.setattr(execution,'require_live_owner',lambda lease,role=None: None)
        with pytest.raises(RuntimeRefused,match='^JOB_SLOT_BUSY$'):
            with engine_slot(stranger,'engineer'): pass
        monkeypatch.undo()
        stop.set();holder.join(5)
        assert execution.FREE==list(range(SLOTS)) and job_slot_busy(lease) is False
    finally: release_owner(lease)


def test_slot_merge(monkeypatch):
    """The merged verification fails when any one slot fails, and keeps each slot's observations."""
    from compertum.runtime import sandbox
    def fake(root,*,slot=0,**kw):
        controls={k:not(slot==2 and k=='outside_read_denied') for k in CONTROLS}
        return {'controls':controls,'failed':[k for k,v in controls.items() if not v],'observations':{k:slot==1 for k in OBSERVATIONS},'report':{},'result':{'slot':slot}}
    monkeypatch.setattr(sandbox,'verify_sandbox',fake)
    merged=sandbox.verify_slots('.',memory_floor_bytes=1)
    assert merged['failed']==['outside_read_denied'] and merged['controls']['outside_read_denied'] is False
    assert merged['slots'][2]['failed']==['outside_read_denied'] and merged['slots'][0]['failed']==[]
    assert all(merged['observations'].values()) and merged['slots'][1]['observations']==dict.fromkeys(OBSERVATIONS,True)
    with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED:outside_read_denied$'): require_verified(merged)


ENGINE_SITE=PROJECT/'.cache'/'engine-env'/'Lib'/'site-packages'


@pytest.fixture(scope='module')
def library(root):
    from compertum.ai.engine.libraries import build_library,check_library,library_folder
    base=root/f'library-root-{uuid4().hex[:8]}';base.mkdir()
    build_library(base,ENGINE_SITE);check_library(base)
    return library_folder(base)


def container_entries(folder):
    import subprocess
    return [line for line in subprocess.run(['icacls',str(folder)],capture_output=True,text=True).stdout.splitlines() if 'S-1-15-2-' in line]


def test_library_job(root,library):
    """A job imports NumPy from the read-only library, keeps its own argv, runs on one BLAS thread, and cannot write into the library.
    The read grant ends with the job."""
    source=('import json,os,sys\nimport numpy as np\nout={"argv":sys.argv,"version":np.__version__,"sum":float(np.linalg.solve(np.eye(2)*4,np.ones(2)).sum()),'
            '"threads":os.environ.get("OPENBLAS_NUM_THREADS")}\n'
            'try:\n    open(os.path.join(open("lib.txt").read(),"escape.txt"),"w").write("x");out["write"]="ok"\nexcept PermissionError: out["write"]="denied"\n'
            'open("out.json","w").write(json.dumps(out))\n')
    folder=job(root,source,**{'lib.txt':str(library)})
    result=run_sandboxed(root,folder,['main.py','x'],seconds=60,memory_bytes=256*MIB,memory_floor_bytes=FLOOR,library=library)
    assert result.exit_code==0,result.stderr
    out=json.loads((folder/'out.json').read_text())
    assert out=={'argv':['main.py','x'],'version':'2.5.4','sum':0.5,'threads':'1','write':'denied'}
    assert not (library/'escape.txt').exists() and container_entries(library)==[] and container_entries(library/'numpy'/'__init__.py')==[]
    plain=job(root,'import numpy\n');result=run(root,plain)
    assert result.exit_code!=0 and b'ModuleNotFoundError' in result.stderr


def test_library_denied(root,library,tmp_path):
    """The library must be an existing, absolute, real folder outside the job folder; refusals happen before any process exists."""
    import subprocess
    folder=job(root,'print(1)\n');link=root/f'link-{uuid4().hex[:8]}'
    subprocess.run(['cmd','/c','mklink','/J',str(link),str(library)],capture_output=True,check=True)
    try:
        for bad in ('relative',library/'numpy'/'__init__.py',folder,root,link,tmp_path/'absent',7):
            with pytest.raises(RuntimeRefused,match='^SANDBOX_LIBRARY_DENIED$'): run(root,folder,library=bad)
    finally: link.rmdir()
    assert container_entries(library)==[]


def test_library_slots(root,library):
    """Slot verification with a library adds three controls in every slot; a wrong version or an empty folder fails the import control."""
    from compertum.runtime.sandbox import LIBRARY_CONTROLS,SLOTS,verify_library,verify_slots
    pipe=r'\\.\pipe\compertum-libslots-'+uuid4().hex[:8];listener=Listener(pipe,'AF_PIPE')
    try: merged=verify_slots(root,memory_floor_bytes=FLOOR,fixed_targets=FIXED_TARGETS,pipe=pipe,library=library,library_version='2.5.4')
    finally: listener.close()
    assert merged['failed']==[] and merged['library']['path']==str(library) and set(merged['library']['controls'])==set(LIBRARY_CONTROLS)
    assert all(merged['library']['controls'].values()) and [s['slot'] for s in merged['library']['slots']]==list(range(SLOTS))
    require_verified(merged)
    wrong=verify_library(root,library=library,memory_floor_bytes=FLOOR,version='9.9.9')
    assert wrong['failed']==['library_import_allowed']
    empty=root/f'empty-lib-{uuid4().hex[:8]}';empty.mkdir()
    assert verify_library(root,library=empty,memory_floor_bytes=FLOOR)['failed']==['library_import_allowed']
