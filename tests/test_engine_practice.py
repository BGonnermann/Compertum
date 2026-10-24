"""The owner's practice-run command, product lane: the read-only model listing, the report, refusals and argument handling.

The full practice run against the scripted server runs in tests/test_engine_practice_run.py in the engine environment.
"""
import json
from pathlib import Path
import shutil
import pytest
from test_ai_models_interface import server,write_models
from compertum.ai.engine import practice
from compertum.runtime.errors import RuntimeRefused

PROJECT=Path(__file__).resolve().parents[1]


def test_models_listing_is_read_only_and_loopback_only():
    with server() as (port,state):
        assert practice.list_models(f'http://127.0.0.1:{port}/v1')==['synthetic-model'] and state['posts']==[] and state['gets']==1
    for bad in ('http://10.0.0.5:1234/v1','https://api.example.com/v1','not a url'):
        with pytest.raises(RuntimeRefused,match='^NON_LOOPBACK_DENIED$'): practice.list_models(bad)
    with pytest.raises(RuntimeRefused,match='^LOCAL_COMPLETION_UNVERIFIED$'): practice.list_models('http://127.0.0.1:9/v1',seconds=2)


def test_models_report_says_whether_each_role_model_is_listed(tmp_path):
    with server() as (port,state):
        write_models(tmp_path,[(role,f'http://127.0.0.1:{port}/v1','synthetic-model' if role!='engineer' else 'SET_FROM_SERVER_MODEL_LIST') for role in ('director','researcher','mathematician','engineer')])
        report=practice.models_report(tmp_path)
        assert report['servers']=={f'http://127.0.0.1:{port}/v1':{'models':['synthetic-model'],'error':None}}
        assert report['roles']['director']['listed'] is True and report['roles']['engineer']['listed'] is False and report['all_listed'] is False
        assert state['posts']==[]  # no completion was sent
    # The committed models file points at LM Studio's default port; with no server there the report says so and sends nothing.
    committed=practice.models_report(PROJECT)
    assert committed['all_listed'] is False and set(committed['roles'])=={'director','researcher','mathematician','engineer'}
    assert all(s['error'] in ('LOCAL_COMPLETION_UNVERIFIED',None) for s in committed['servers'].values())


def test_run_refuses_below_the_start_floor_before_taking_any_lease(tmp_path):
    shutil.copyfile(PROJECT/'config/default.toml',tmp_path/'config.toml');(tmp_path/'config').mkdir()
    shutil.copyfile(PROJECT/'config/models.toml',tmp_path/'config'/'models.toml')
    with pytest.raises(RuntimeRefused,match='^AVAILABLE_RAM_FLOOR$'):
        practice.run_practice(tmp_path,tmp_path/'config.toml',cycles=1,hours=None,requests=10,note='x',available_memory=lambda:practice.START_FLOOR-1)
    assert not (tmp_path/'state'/'locks').exists()  # no owner lease was taken
    assert practice.START_FLOOR==16*1024**3


def test_command_reports_json_and_exit_codes(tmp_path,capsys):
    with server() as (port,state):
        shutil.copyfile(PROJECT/'config/default.toml',tmp_path/'config.toml')
        write_models(tmp_path,[(role,f'http://127.0.0.1:{port}/v1','synthetic-model') for role in ('director','researcher','mathematician','engineer')])
        assert practice.main(['--project',str(tmp_path),'--config','config.toml','models'])==0
        out=json.loads(capsys.readouterr().out);assert out['all_listed'] is True and out['roles']['engineer']['model']=='synthetic-model'
    (tmp_path/'config'/'models.toml').write_text('[roles.director]\nbase_url = "http://127.0.0.1:1234/v1"\n',encoding='utf-8')
    assert practice.main(['--project',str(tmp_path),'--config','config.toml','models'])==2
    assert json.loads(capsys.readouterr().out)=={'refused':'UNKNOWN_CONFIG_FIELD'}
    with pytest.raises(SystemExit): practice.main(['--project',str(tmp_path),'run','--cycles','1'])  # --requests and --note are required
