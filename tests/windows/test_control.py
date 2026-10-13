"""Native public control binds identity, generation and durable request IDs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import pytest
from compertum.runtime.bootstrap import _registration
from compertum.runtime.ipc import PipeDescriptor
from compertum.runtime.control import durable_request
from compertum.runtime.errors import RuntimeRefused

ROOT=Path(__file__).parents[2]

def test_native_control_duplicate_and_conflicting_request(tmp_path):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PYTHONPATH'}}
    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    child=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/control_holder.py'),str(tmp_path)],
        executable=sys._base_executable,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000)
    try:
        deadline=time.monotonic()+5
        while not (tmp_path/'route.json').exists() and child.poll() is None and time.monotonic()<deadline: time.sleep(.02)
        route=PipeDescriptor(_registration(json.loads((tmp_path/'route.json').read_text())))
        cmd={'schema_version':1,'request_id':str(uuid4()),'target_role':'supervisor','target_generation':route.registration.generation,
             'action':'pause_research','payload':{},'actor':{'kind':'operator'}}
        
        if child.poll() is not None:
            out,err=child.communicate();pytest.fail(err.decode())
        first=durable_request(route,cmd)
        assert first['confirmed'] and first['reason']=='RESEARCH_PAUSED'
        assert durable_request(route,cmd)==first
        with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):
            durable_request(route,{**cmd,'action':'resume_research'})
        status=durable_request(route,{**cmd,'request_id':str(uuid4()),'action':'status'})
        assert status['research_state']=='PAUSED' and status['order_admission']=='DISARMED'
        out,err=child.communicate(timeout=3)
        assert child.returncode==0 and not err
    finally:
        if child.poll() is None: child.kill();child.wait(timeout=3)

