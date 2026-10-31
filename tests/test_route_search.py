"""The model routing search tool (owner, 31 October 2026): candidate firms, one trip per batch, keep or discard at one cycle per market."""
import json
from pathlib import Path
import sys
import pytest

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import route_search as rs  # noqa: E402

PLAN='''batch = 2
keep_margin = 0.3
roles = ["mathematician", "engineer"]
[start]
director = "a"
researcher = "a"
mathematician = "a"
engineer = "a"
[[pool]]
name = "a"
file = "alpha"
model = "vendor/alpha"
input_per_million = 0.01
output_per_million = 0.1
[[pool]]
name = "b"
file = "beta"
model = "vendor/beta"
input_per_million = 1.0
output_per_million = 2.0
'''


def model_file(model,extra=''):
    return ''.join(f'[roles.{r}]\nbase_url = "https://openrouter.ai/api/v1"\nmodel = "{model}"\nmax_tokens = 4096\n{extra}\n' for r in rs.ROLES)


@pytest.fixture
def project(tmp_path):
    (tmp_path/'config').mkdir();(tmp_path/'config'/'route_search.toml').write_text(PLAN,encoding='utf-8')
    (tmp_path/'config'/'models-alpha.toml').write_text(model_file('vendor/alpha','reasoning_tokens = 2048\n'),encoding='utf-8')
    (tmp_path/'config'/'models-beta.toml').write_text(model_file('vendor/beta'),encoding='utf-8')
    return tmp_path


def test_the_plan_loads_and_the_committed_plan_names_real_files():
    plan=rs.load_plan(PROJECT)
    assert set(plan['start'])==set(rs.ROLES) and all(plan['start'][r] in plan['pool'] for r in rs.ROLES) and plan['keep_margin']==rs.Decimal('0.3')
    for entry in plan['pool'].values(): assert (PROJECT/'config'/f"models-{entry['file']}.toml").exists() and entry['output_per_million']>0


def test_next_batches_swap_one_role_at_a_time_from_the_incumbent(project,capsys):
    plan=rs.load_plan(project)
    assert rs.next_batch(plan,[])==[dict(director='a',researcher='a',mathematician='a',engineer='a'),dict(director='b',researcher='b',mathematician='b',engineer='b')]
    assert rs.do_next(project,plan)==0
    out=capsys.readouterr().out
    assert 'route-1' in out and 'route-2' in out and '-Model "route-1::,route-2::"' in out and '-CyclesPerMarket 1' in out
    one=(project/'config'/'models-route-1.toml').read_text(encoding='utf-8');two=(project/'config'/'models-route-2.toml').read_text(encoding='utf-8')
    assert one.count('model = "vendor/alpha"')==4 and 'reasoning_tokens = 2048' in one
    assert two.count('model = "vendor/beta"')==4 and 'reasoning_tokens' not in two  # the one-model firm on b, with b's file limits
    log=rs.read_log(project);assert [e['kind'] for e in log]==['planned','planned','batch'] and log[1]['firm']['mathematician']=='b' and 'balance_before' in log[2]
    # The next batch skips tried firms and swaps one role at a time, in role order.
    assert rs.next_batch(plan,log)==[dict(director='a',researcher='a',mathematician='b',engineer='a'),dict(director='a',researcher='a',mathematician='a',engineer='b')]
    three=rs.next_batch(plan,log)[0];rs.write_candidate(project,3,three,plan['pool'])
    text=(project/'config'/'models-route-3.toml').read_text(encoding='utf-8')
    assert text.count('model = "vendor/beta"')==1 and text.count('model = "vendor/alpha"')==3 and text.index('[roles.mathematician]')<text.index('model = "vendor/beta"')


def test_scoring_keeps_better_firms_and_discards_false_discoveries(project,capsys):
    plan=rs.load_plan(project);rs.do_next(project,plan);capsys.readouterr()
    def run(run_id,mean,found,false,verdict='MEASURED',faults=0,levels=None):
        markets=[{'levels':[l]} for l in (levels or [int(float(mean))]*16)]
        return {'run_id':run_id,'reason':'CYCLE_LIMIT','requests':100,'elapsed_seconds':600.0,
                'cycles':[{'faults':[{'code':'AI_RESPONSE_TRUNCATED'}]*faults}],
                'report':{'verdict':verdict,'mean_level':mean,'patterns_found':found,'false_discoveries':false,'candidates_total':40,'markets':markets}}
    transcripts=project/'state'/'engine'/'transcripts';transcripts.mkdir(parents=True)
    for run_id,model in (('run-1','vendor/alpha'),('run-2','vendor/beta')):
        (transcripts/f'{run_id}.jsonl').write_text(json.dumps({'model_requested':model,'role':'mathematician','elapsed_seconds':30.0,'status':'COMPLETED',
                                                                 'usage':{'prompt_tokens':1000000,'completion_tokens':1000000}})+'\n'
                                                      +json.dumps({'model_requested':model,'role':'engineer','elapsed_seconds':6.0,'status':'REFUSED_AI_RESPONSE_TRUNCATED','usage':None})+'\n',encoding='utf-8')
    record=project/'record.json'
    record.write_text('﻿noise\n'+json.dumps({'runs':{'route-1::':run('run-1','7.00',2,0),'route-2::':run('run-2','7.20',3,0,faults=2)}}),encoding='utf-8')
    assert rs.do_score(project,plan,str(record))==0
    log=[e for e in rs.read_log(project) if e['kind']=='scored']
    assert [e['decision'] for e in log]==['keep','keep'] and log[0]['metrics']['cost']==0.11 and log[1]['metrics']['cost']==3.0 and log[1]['metrics']['faults']==2
    firm,best=rs.incumbent(rs.read_log(project),plan['start']);assert firm['mathematician']=='b' and best['mean_level']=='7.20'
    roles=log[0]['metrics']['roles'];assert roles['mathematician']=={'calls':1,'seconds':30.0,'output_tokens':1000000,'faults':0,'model':'vendor/alpha'} and roles['engineer']['faults']==1
    assert rs.main(['--project',str(project),'roles'])==0 and 'route-2 | engineer | vendor/beta | 1 | 0.1 | 0 | 1' in capsys.readouterr().out
    # A later batch (the one-model firm on b is the incumbent; its swaps back to a come next): a refusal is logged as a discard, and a UTF-16 record reads too.
    rs.do_next(project,plan);capsys.readouterr()
    names=[e['name'] for e in rs.read_log(project) if e['kind']=='planned'][2:];assert len(names)==2
    record.write_text(json.dumps({'runs':{f'{names[0]}::':{'refused':'ENGINE_STOPPED'},f'{names[1]}::':run('run-4','6.00',1,0),'route-99::':run('run-9','9.00',9,0)}}),encoding='utf-16')
    rs.do_score(project,plan,str(record));out=capsys.readouterr().out
    scored=[e for e in rs.read_log(project) if e['kind']=='scored']
    assert [e['decision'] for e in scored[2:]]==['discard','discard'] and 'refused: ENGINE_STOPPED' in scored[2]['why'] and 'incumbent: ' in out and 'route-99::: not a planned candidate' in out
    assert rs.decide({'verdict':'MEASURED','mean_level':'8.00','found':6,'false':1},{'mean_level':'7.20','found':3},rs.Decimal('0.3'))==('discard','false discovery or incomplete')
    assert rs.decide({'verdict':'MEASURED','mean_level':'7.70','found':1,'false':0},{'mean_level':'7.50','found':3},rs.Decimal('0.3'))[0]=='discard'
    assert rs.decide({'verdict':'INCOMPLETE: a market has no finished cycle','mean_level':'9.00','found':9,'false':0},None,rs.Decimal('0.3'))[0]=='discard'
    batches=[e for e in rs.read_log(project) if e['kind'] in ('batch','batch_end')]
    assert [e['kind'] for e in batches]==['batch','batch_end','batch','batch_end'] and all('balance_before' in e for e in batches[::2])  # None without a key


def test_a_narrow_win_is_retested_and_the_two_passes_are_averaged(project,capsys):
    """A win under the incumbent's half-spread is measured again; the average of both passes decides, and the retest comes first in the next batch."""
    plan=rs.load_plan(project);rs.do_next(project,plan);capsys.readouterr()
    def run(run_id,mean,levels,found=2):
        return {'run_id':run_id,'reason':'CYCLE_LIMIT','requests':100,'elapsed_seconds':600.0,'cycles':[{'faults':[]}],
                'report':{'verdict':'MEASURED','mean_level':mean,'patterns_found':found,'false_discoveries':0,'candidates_total':40,'markets':[{'levels':[l]} for l in levels]}}
    record=project/'record.json'
    # The incumbent's halves are 8.0 and 6.0 (spread 2.0); the challenger wins by 0.5, under that spread: retest.
    record.write_text(json.dumps({'runs':{'route-1::':run('run-1','7.00',[8]*8+[6]*8),'route-2::':run('run-2','7.50',[7,8]*8,found=3)}}),encoding='utf-8')
    # route-2 is the one-model firm on b here; its narrow win over the start firm is retested.
    rs.do_score(project,plan,str(record))
    scored=[e for e in rs.read_log(project) if e['kind']=='scored']
    assert scored[0]['metrics']['halves']=={'first':8.0,'second':6.0,'spread':2.0} and scored[1]['decision']=='retest' and 'half-spread 2.0' in scored[1]['why']
    firm,_=rs.incumbent(rs.read_log(project),plan['start']);assert firm['mathematician']=='a'  # not kept yet
    assert rs.next_batch(plan,rs.read_log(project))[0]==dict(director='b',researcher='b',mathematician='b',engineer='b')
    rs.do_next(project,plan);out=capsys.readouterr().out;assert 'route-3' in out
    planned=[e for e in rs.read_log(project) if e['kind']=='planned'];assert planned[2]['pass']==2 and planned[2]['key']==scored[1]['key']
    record.write_text(json.dumps({'runs':{'route-3::':run('run-3','7.70',[8,7]*8,found=4),'route-4::':run('run-4','6.00',[6]*16)}}),encoding='utf-8')
    rs.do_score(project,plan,str(record))
    scored=[e for e in rs.read_log(project) if e['kind']=='scored']
    assert scored[2]['decision']=='keep' and scored[2]['metrics']['mean_level']=='7.60' and scored[2]['metrics']['found']==7 and scored[2]['metrics']['passes']==2
    firm,best=rs.incumbent(rs.read_log(project),plan['start']);assert firm==dict(director='b',researcher='b',mathematician='b',engineer='b') and best['mean_level']=='7.60'
    assert rs.decide({'verdict':'MEASURED','mean_level':'7.60','found':9,'false':0,'halves':None},{'mean_level':'7.50','found':3,'halves':{'spread':0.1}},rs.Decimal('0.3'))[0]=='keep'


def test_the_command_line_reports_status(project,capsys):
    assert rs.main(['--project',str(project),'status'])==0 and 'not measured yet' in capsys.readouterr().out
