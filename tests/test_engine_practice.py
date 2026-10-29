"""The owner's practice-run command, product lane: the read-only model listing, the report, refusals and argument handling.

The full practice run against the scripted server runs in tests/test_engine_practice_run.py in the engine environment.
"""
import json
from pathlib import Path
import shutil
import pytest
from test_ai_models_interface import server,write_models
from compertum.ai.engine import practice
from compertum.ai.models import RoleModel
from compertum.runtime.errors import RuntimeRefused

PROJECT=Path(__file__).resolve().parents[1]


def test_models_listing_is_read_only_and_checks_the_address():
    with server() as (port,state):
        assert practice.list_models(RoleModel('director',f'http://127.0.0.1:{port}/v1','m'))==['synthetic-model'] and state['posts']==[] and state['gets']==1
    for bad in ('http://10.0.0.5:1234/v1','https://api.example.com/v1','not a url'):
        with pytest.raises(RuntimeRefused): practice.list_models(RoleModel('director',bad,'m'))
    with pytest.raises(RuntimeRefused,match='^LOCAL_COMPLETION_UNVERIFIED$'): practice.list_models(RoleModel('director','http://127.0.0.1:9/v1','m'),seconds=2)


def test_the_model_is_chosen_per_run_without_editing_files(tmp_path):
    # Owner direction, 26 October 2026: pick the model at run time. --model replaces every role's ID for that run only.
    with server() as (port,state):
        write_models(tmp_path,[(role,f'http://127.0.0.1:{port}/v1','file-model') for role in ('director','researcher','mathematician','engineer')])
        before=(tmp_path/'config'/'models.toml').read_bytes()
        assert {r['model'] for r in practice.models_report(tmp_path,'local','synthetic-model')['roles'].values()}=={'synthetic-model'}
        assert practice.models_report(tmp_path,'local','synthetic-model')['all_listed'] is True and practice.models_report(tmp_path)['all_listed'] is False
        assert (tmp_path/'config'/'models.toml').read_bytes()==before and state['posts']==[]
    for bad in ('',' padded','x'*300):
        with pytest.raises(RuntimeRefused,match='^MODEL_IDENTITY_UNVERIFIED$'): practice.chosen_roles(tmp_path,'local',bad)
    for bad in ('../x','Upper','a b'):
        with pytest.raises(RuntimeRefused,match='^UNKNOWN_CONFIG_FIELD$'): practice.model_file(tmp_path,bad)
    assert practice.model_file(tmp_path,'deepseek')==tmp_path/'config/models-deepseek.toml' and practice.model_file(tmp_path,'local')==tmp_path/'config/models.toml'


def test_models_report_says_whether_each_role_model_is_listed(tmp_path):
    with server() as (port,state):
        write_models(tmp_path,[(role,f'http://127.0.0.1:{port}/v1','synthetic-model' if role!='engineer' else 'SET_FROM_SERVER_MODEL_LIST') for role in ('director','researcher','mathematician','engineer')])
        report=practice.models_report(tmp_path)
        assert report['servers']=={f'http://127.0.0.1:{port}/v1':{'models':['synthetic-model'],'error':None}}
        assert report['roles']['director']['listed'] is True and report['roles']['engineer']['listed'] is False and report['all_listed'] is False
        assert state['posts']==[]  # no completion was sent
    # The committed models file points at LM Studio's default port. The owner's server may or may not be running there (it was,
    # with Flint, on 24 October 2026): the report is consistent either way and sends no completion.
    committed=practice.models_report(PROJECT)
    assert set(committed['roles'])=={'director','researcher','mathematician','engineer'}
    assert committed['all_listed']==all(r['listed'] for r in committed['roles'].values())
    assert all(s['error'] in ('LOCAL_COMPLETION_UNVERIFIED',None) and (s['error'] is None or s['models']==[]) for s in committed['servers'].values())


def test_run_refuses_below_the_start_floor_before_taking_any_lease(tmp_path):
    shutil.copyfile(PROJECT/'config/default.toml',tmp_path/'config.toml');(tmp_path/'config').mkdir()
    shutil.copyfile(PROJECT/'config/models.toml',tmp_path/'config'/'models.toml')
    with pytest.raises(RuntimeRefused,match='^AVAILABLE_RAM_FLOOR$'):
        practice.run_practice(tmp_path,tmp_path/'config.toml',cycles=1,hours=None,requests=10,note='x',available_memory=lambda:practice.START_FLOOR-1)
    assert not (tmp_path/'state'/'locks').exists()  # no owner lease was taken
    assert practice.START_FLOOR==8*1024**3  # owner decision, 26 October 2026 (was 16 GiB)


def test_gepa_practice_record_is_built_from_the_run_result(tmp_path,monkeypatch):
    """The owner's `gepa` command: the same preamble as `run`, then run_gepa; the printed record summarizes the prompts folder."""
    from compertum.ai.engine import gepa_run
    shutil.copyfile(PROJECT/'config/default.toml',tmp_path/'config.toml')
    write_models(tmp_path,[(role,'http://127.0.0.1:1234/v1','synthetic-model') for role in ('director','researcher','mathematician','engineer')])
    shutil.copytree(PROJECT/'config'/'engine_prompts',tmp_path/'config'/'engine_prompts')  # the preflight check reads the run's prompts (25 October 2026)
    seen={}
    def fake_run_gepa(**kwargs):
        seen.update(kwargs)
        return {'run_id':'run-20261024-0123abcd','reason':'CYCLE_LIMIT','cycles':[{'cycle_index':1,'status':'COMPLETED','market':'seed 12','candidates':[{'hypothesis_id':'h1','status':'QUEUED','deflation':{'status':'PASS'},'audit':{'label':'VERIFIED_PASS'}}]}],
                'requests':9,'elapsed_seconds':12.5,'summary_path':str(tmp_path/'state'/'engine'/'summary.md'),'models':{'director':{'address':'http://127.0.0.1:1234/v1','model':'synthetic-model'}},
                'prompts':{'folder':str(tmp_path/'state'/'engine'/'prompts'/'run-20261024-0123abcd'),'best_index':1,'mean_scores':[0.7,1.0],'candidate_count':2,
                           'gepa':{'best_index_in_gepa_pool':1,'best_folder_index':1,'val_aggregate_scores':[0.7,1.0],'total_metric_calls':4}}}
    monkeypatch.setattr(gepa_run,'run_gepa',fake_run_gepa)
    record=practice.run_practice(tmp_path,tmp_path/'config.toml',cycles=4,hours=None,requests=50,note='GEPA fixture',gepa=True,available_memory=lambda:practice.START_FLOOR+1)
    assert record['kind']=='gepa' and record['reason']=='CYCLE_LIMIT' and record['cycles'][0]['candidates'][0]['audit']=='VERIFIED_PASS' and record['research_state_after']=='PAUSED'
    assert record['prompts']=={'folder':str(tmp_path/'state'/'engine'/'prompts'/'run-20261024-0123abcd'),'best_index':1,'mean_scores':[0.7,1.0],'candidate_count':2,
                               'gepa_best_folder_index':1,'gepa_val_aggregate_scores':[0.7,1.0],'gepa_total_metric_calls':4}
    train,validation=practice.gepa_markets(4096,0.004)
    assert [m['label'] for m in seen['markets']]==[m['label'] for m in train] and [m['label'] for m in seen['validation_markets']]==[m['label'] for m in validation]
    assert seen['markets'][0]['label']=='seed 200, 4096 sessions, momentum window 5, strength 0.004' and seen['validation_markets'][-1]['label']=='seed 223, 4096 sessions, no pattern'
    assert seen['limits'].cycle_limit==4 and record['preflight']['markets']==24 and record['vault_sessions_held_back']==24*820
    from compertum.ai.engine.market import market_csv,split_market_tiers,synthetic_market
    assert seen['validation_markets'][2]['validation_csv']==market_csv(split_market_tiers(synthetic_market(218,4096,planted={'kind':'reversal','window':3,'strength':0.004}))[1])
    assert all('vault' not in m for m in seen['markets']+seen['validation_markets']) and seen['owner_approval']=='GEPA fixture' and record['verification']['failed']==[]
    json.dumps(record)  # printable


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
