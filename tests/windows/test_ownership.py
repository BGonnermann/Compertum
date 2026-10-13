import importlib
import subprocess
import sys
import time
import pytest

def api():
    try: return importlib.import_module('compertum.runtime.owners')
    except ImportError: pytest.fail('native ownership missing')

def test_exclusive_handle_blocks_same_process_and_live_thread_takeover(tmp_path):
    m=api(); project=m.resolve_project(tmp_path)
    owner=m.acquire_owner(project,'execution')
    try:
        with pytest.raises(m.OwnerError): m.acquire_owner(project,'execution')
    finally: owner.close()
    with pytest.raises(m.OwnerError): m.acquire_owner(project,'execution')

def test_case_alias_is_same_kernel_identity(tmp_path):
    m=api(); a=m.resolve_project(tmp_path); b=m.resolve_project(str(tmp_path).upper())
    assert a.project_id==b.project_id

def test_two_processes_cannot_initialize_owner_and_dead_process_recovers(tmp_path):
    m=api(); project=m.resolve_project(tmp_path)
    code="from pathlib import Path; from compertum.runtime.owners import *; import time; o=acquire_owner(resolve_project(Path(__import__('sys').argv[1])),'execution'); print(o.generation,flush=True); time.sleep(1)"
    p=subprocess.Popen([sys.executable,'-u','-c',code,str(tmp_path)],stdout=subprocess.PIPE,text=True)
    generation=p.stdout.readline().strip(); assert generation
    try:
        with pytest.raises(m.OwnerError): m.acquire_owner(project,'execution')
    finally:
        p.wait(timeout=5); p.stdout.close()
    owner=m.acquire_owner(project,'execution')
    assert owner.generation!=generation
    owner.close()

def test_simultaneous_start_only_one_owner(tmp_path):
    m=api()
    code="from pathlib import Path; from compertum.runtime.owners import *; import sys,time; r=Path(sys.argv[1]); (r/('ready'+sys.argv[2])).write_text('ready');\nwhile not (r/'go').exists(): time.sleep(.01)\ntry:\n o=acquire_owner(resolve_project(r),'execution'); print('OWNER',flush=True);time.sleep(1)\nexcept OwnerError: print('BUSY',flush=True)"
    ps=[subprocess.Popen([sys.executable,'-u','-c',code,str(tmp_path),str(i)],stdout=subprocess.PIPE,text=True) for i in range(2)]
    deadline=time.monotonic()+8
    while not all((tmp_path/('ready'+str(i))).exists() for i in range(2)) and time.monotonic()<deadline: time.sleep(.02)
    assert all((tmp_path/('ready'+str(i))).exists() for i in range(2))
    (tmp_path/'go').write_text('go')
    answers=[p.communicate(timeout=5)[0].strip() for p in ps]
    assert sorted(answers)==['BUSY','OWNER']

def test_junction_alias_cannot_bypass_owner(tmp_path):
    m=api(); target=tmp_path/'target';target.mkdir();alias=tmp_path/'alias'
    result=subprocess.run(['cmd','/c','mklink','/J',str(alias),str(target)],capture_output=True,text=True,timeout=5)
    assert result.returncode==0, 'native junction capability unavailable'
    p=m.resolve_project(target); a=m.resolve_project(alias);assert p.project_id==a.project_id
    try:
        with m.acquire_owner(p,'execution'):
            with pytest.raises(m.OwnerError): m.acquire_owner(a,'execution')
    finally:alias.rmdir()
