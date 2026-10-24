"""The owner's practice-run command, engine environment lane: one full run as a separate process against the scripted loopback server.

The run takes the coordinator owner lease of a temporary project, verifies the sandbox with the fixed-part probe targets,
sets the research state to RUNNING for the run and back to PAUSED afterwards, and prints the record as JSON.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
deepagents=pytest.importorskip('deepagents')
from test_ai_models_interface import write_models  # noqa: E402
from test_engine_roles import role_server  # noqa: E402

PROJECT=Path(__file__).resolve().parents[1]


def test_practice_run_as_a_separate_process(tmp_path):
    shutil.copyfile(PROJECT/'config/default.toml',tmp_path/'config.toml')
    shutil.copytree(PROJECT/'config'/'engine_prompts',tmp_path/'config'/'engine_prompts')
    (tmp_path/'config'/'engine.toml').write_text('[run]\nrequest_hard_maximum = 450\n',encoding='utf-8')
    with role_server() as (port,state):
        write_models(tmp_path,[(role,f'http://127.0.0.1:{port}/v1','synthetic-model') for role in ('director','researcher','mathematician','engineer')])
        done=subprocess.run([sys.executable,'-m','compertum.ai.engine.practice','--project',str(tmp_path),'--config','config.toml','run','--cycles','1','--requests','80',
                             '--note','Owner practice run (fixture)'],capture_output=True,text=True,timeout=600,cwd=str(tmp_path))
        assert done.returncode==0,done.stderr[-2000:]
        result=json.loads(done.stdout.strip().splitlines()[-1])
        assert result['reason']=='CYCLE_LIMIT' and len(result['cycles'])==1 and result['requests']==len(state['posts'])<=80
        candidate=result['cycles'][0]['candidates'][0];assert candidate['status']=='QUEUED' and candidate['audit']=='VERIFIED_PASS'
        assert result['research_state_after']=='PAUSED' and result['verification']['failed']==[] and result['vault_sessions_held_back']==100
        assert Path(result['summary_path']).is_relative_to(tmp_path/'state'/'engine') and Path(result['sandbox_root']).is_relative_to(tmp_path/'.cache'/'test-runs')
        assert result['models']['engineer']['model']=='synthetic-model' and result['free_memory_bytes_at_start']>=16*1024**3
        # A second run refuses while the owner's stop file exists, as a separate process too.
        stop=tmp_path/'state'/'engine'/'STOP';stop.write_text('owner stop',encoding='utf-8')
        again=subprocess.run([sys.executable,'-m','compertum.ai.engine.practice','--project',str(tmp_path),'--config','config.toml','run','--cycles','1','--requests','10',
                              '--note','x'],capture_output=True,text=True,timeout=600,cwd=str(tmp_path))
        assert again.returncode==2 and json.loads(again.stdout.strip().splitlines()[-1])=={'refused':'ENGINE_STOP_FILE_PRESENT'}
    shutil.rmtree(result['sandbox_root'],ignore_errors=True)
