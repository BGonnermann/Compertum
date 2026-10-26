"""The preflight content check (25 October 2026), product lane: no model, no sandbox, no engine library.

Practice runs 5 to 10 sent the Engineer the literal text "{specification}" because one string had no f prefix. These tests show that the
check finds that class of error, and the other ways a task can be incomplete, before a run takes the lease or sends a request.
"""
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest
from compertum.ai.engine import practice,preflight,tasks
from compertum.runtime.errors import RuntimeRefused

PROJECT=Path(__file__).resolve().parents[1]


def markets():
    return [practice.practice_market(12,500,0.004)[0]]+[practice.practice_market(12+o,500,0.004,k,w)[0] for k,w,o in practice.GEPA_MARKETS]


def test_every_task_of_every_practice_market_and_the_committed_prompts_pass():
    assert preflight.preflight(PROJECT,markets())=={'markets':5,'tasks_per_market':9,'prompts':4}
    assert preflight.check_prompts(PROJECT)==[]


def test_the_cycle_builds_its_tasks_with_the_checked_builders():
    """The check is only worth something if the cycle uses the same code. cycle.py imports every builder from tasks.py. Engine lane: cycle.py needs the engine library."""
    pytest.importorskip('langchain_core')
    from compertum.ai.engine import cycle
    for name in ('market_brief','pick_task','memo_task','approve_task','specify_task','review_task','agenda_task','retry_task','engineer_task','clip_bytes'):
        assert getattr(cycle,name) is getattr(tasks,name),name
    assert cycle.STARTER_MAIN is tasks.STARTER_MAIN


def test_task_text_is_pinned():
    """The move from cycle.py to tasks.py kept every task byte-identical. A change to any task text changes this hash on purpose only."""
    m=practice.practice_market(12,500,0.004)[0];e=SimpleNamespace(train_csv=m['train_csv'],validation_rows=m['validation_rows'],max_hypotheses=3)
    b=tasks.market_brief(e);s={'a':1}
    parts=[b,tasks.pick_task(3,7,b,s),tasks.memo_task(b,{'id':'h1','title':'T','idea':'I'}),tasks.approve_task('h1','M'),tasks.specify_task(b,'M'),
           tasks.review_task('S',{'/main.py':'x'}),tasks.agenda_task(b,s),tasks.retry_task('T','E','R'),tasks.engineer_task(e,'S')[0],
           tasks.engineer_task(e,'S',previous_reply='R')[0],tasks.STARTER_MAIN]
    assert hashlib.sha256('\x00'.join(parts).encode()).hexdigest()=='8ff608f36424268f119d28838ed17be9aa0a454409632d11a9eb99045e892235'


def failed(monkeypatch,name,replacement):
    monkeypatch.setattr(preflight,name,replacement)
    with pytest.raises(preflight.PreflightFailed) as error: preflight.preflight(PROJECT,markets()[:1])
    assert error.value.code=='ENGINE_PREFLIGHT_FAILED' and isinstance(error.value,RuntimeRefused)
    return error.value.problems


def test_the_practice_run_5_to_10_bug_is_found(monkeypatch):
    """The real bug: the second half of the Engineer task had no f prefix."""
    def broken(engine,specification,*,previous_reply=None):
        task,files=tasks.engineer_task(engine,specification,previous_reply=previous_reply)
        return task.split('SPECIFICATION\n')[0]+'SPECIFICATION\n{specification}',files
    problems=failed(monkeypatch,'engineer_task',broken)
    assert any('engineer build: unfilled placeholder {specification}' in p for p in problems)
    assert any('engineer build: the task does not hold the specification' in p for p in problems)


@pytest.mark.parametrize('name,replacement,expected',[
    ('memo_task',lambda brief,hypothesis:f'Write the memo for this hypothesis.\n\n{brief}','researcher memo: the task does not hold the hypothesis'),
    ('approve_task',lambda hid,memo:'Approve or reject this memo for hypothesis {hypothesis["id"]}.\n\n'+memo,'director approve: unfilled placeholder {hypothesis["id"]}'),
    ('specify_task',lambda brief,memo:'Write the specification.\\n\\n'+brief+memo,'mathematician specify: the task holds a literal backslash-n'),
    ('review_task',lambda spec,code:'x'*(preflight.TASK_BYTES+1)+spec+json.dumps(code,sort_keys=True),f'mathematician review: the task is {preflight.TASK_BYTES+1+len(preflight.SPEC)+len(json.dumps(preflight.CODE,sort_keys=True))} bytes'),
    ('agenda_task',lambda brief,summary:'','director agenda: the task is empty'),
    ('retry_task',lambda task,code,previous:task+code,'retry: the task does not hold the previous reply'),
    ('market_brief',lambda engine:'MARKET\nno counts','the market brief gives the wrong session counts'),
])
def test_each_kind_of_incomplete_task_is_found(monkeypatch,name,replacement,expected):
    assert any(expected in p for p in failed(monkeypatch,name,replacement))


def test_the_engineer_never_sees_a_validation_row_and_gets_the_right_files(monkeypatch):
    shown='\n'.join(markets()[0]['validation_csv'].splitlines()[1:4])  # three validation rows of the market that failed() checks

    def leak(engine,specification,*,previous_reply=None):
        task,_=tasks.engineer_task(engine,specification,previous_reply=previous_reply)
        return task+'\n'+shown,{'/main.py':'other','/spec.md':'other','/extra.txt':''}
    problems=failed(monkeypatch,'engineer_task',leak)
    assert any('engineer build: the task shows a validation row' in p for p in problems)
    assert any('/spec.md does not equal the specification' in p for p in problems) and any('/main.py is not the starter program' in p for p in problems)
    assert any("the start files are ['/extra.txt', '/main.py', '/spec.md']" in p for p in problems)


def test_prompts_are_checked(tmp_path):
    shutil.copytree(PROJECT/'config'/'engine_prompts',tmp_path/'config'/'engine_prompts')
    assert preflight.check_prompts(tmp_path)==[]
    (tmp_path/'config'/'engine_prompts'/'director.md').write_text('ROLE: director\nPick hypotheses for {cycle_index} and reply with JSON only, please.\n',encoding='utf-8',newline='\n')
    (tmp_path/'config'/'engine_prompts'/'engineer.md').unlink()
    assert preflight.check_prompts(tmp_path)==['prompt director: unfilled placeholder {cycle_index}','prompt engineer: ENGINE_PROMPT_UNAVAILABLE']


def test_a_failed_preflight_stops_the_run_before_the_lease_and_prints_the_problems(tmp_path,capsys):
    shutil.copyfile(PROJECT/'config/default.toml',tmp_path/'config.toml')
    (tmp_path/'config'/'engine_prompts').mkdir(parents=True)  # no prompts: the preflight refuses
    with pytest.raises(preflight.PreflightFailed) as error:
        practice.run_practice(tmp_path,tmp_path/'config.toml',cycles=1,hours=None,requests=10,note='x',available_memory=lambda:practice.START_FLOOR+1)
    assert error.value.problems==[f'prompt {r}: ENGINE_PROMPT_UNAVAILABLE' for r in ('director','researcher','mathematician','engineer')]
    assert not (tmp_path/'state').exists()  # no owner lease, no store, no request
    assert practice.main(['--project',str(tmp_path),'--config','config.toml','run','--cycles','1','--requests','10','--note','x'])==2
    out=json.loads(capsys.readouterr().out)
    assert out['refused']=='ENGINE_PREFLIGHT_FAILED' and len(out['problems'])==4
    # The memory floor still comes first.
    with pytest.raises(RuntimeRefused,match='^AVAILABLE_RAM_FLOOR$'):
        practice.run_practice(tmp_path,tmp_path/'config.toml',cycles=1,hours=None,requests=10,note='x',available_memory=lambda:practice.START_FLOOR-1)


def test_the_problem_list_is_bounded():
    assert len(preflight.PreflightFailed([f'p{i}' for i in range(500)]).problems)==preflight.MAX_PROBLEMS
