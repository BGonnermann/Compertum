"""Stage E5, product lane: the owner's hard maximum, run limits, the run gate, run rows, the daily summary and the owner commands.

No Deep Agents needed. The bounded run itself (with real cycles) is tested in tests/test_engine_run.py in the engine environment.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from test_ai_manual import bridge  # noqa: F401  (fixture)
from compertum.ai.engine import control
from compertum.ai.engine.ledger import EngineLedger
from compertum.ai.engine.limits import (HARD_MAXIMUM_CEILING,MAX_CYCLES,MAX_HOURS,RunGate,RunLimits,check_limits,load_run_settings,stop_reason,
                                        summary_text,write_summary)
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused

PROJECT=Path(__file__).resolve().parents[1]


def set_research_state(store,value):
    with store._live(),store.conn: store.conn.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('research_state',canonical(value).decode()))


def settings_file(root,text):
    (root/'config').mkdir(exist_ok=True);(root/'config'/'engine.toml').write_text(text,encoding='utf-8')


def test_hard_maximum_comes_only_from_the_owner_file(tmp_path):
    # The committed file holds 0: unset. No run can start until the owner sets a value through a reviewed commit.
    assert load_run_settings(PROJECT)=={'request_hard_maximum':0,'path':'config/engine.toml'}
    settings_file(tmp_path,'[run]\nrequest_hard_maximum = 500\n');assert load_run_settings(tmp_path)['request_hard_maximum']==500
    for text,code in (('[run]\nrequest_hard_maximum = 10001\n','INVALID_CONFIG'),('[run]\nrequest_hard_maximum = -1\n','INVALID_CONFIG'),
                      ('[run]\nrequest_hard_maximum = "500"\n','INVALID_CONFIG'),('[run]\nrequest_hard_maximum = 5\nextra = 1\n','UNKNOWN_CONFIG_FIELD'),
                      ('[other]\nx = 1\n','UNKNOWN_CONFIG_FIELD'),('not toml [[[','INVALID_CONFIG'),('[run]\nrequest_hard_maximum = 5\n'+'#'*20000,'CONFIG_TOO_LARGE')):
        settings_file(tmp_path,text)
        with pytest.raises(RuntimeRefused,match=f'^{code}$'): load_run_settings(tmp_path)
    (tmp_path/'config'/'engine.toml').unlink()
    with pytest.raises(RuntimeRefused,match='^CONFIG_UNAVAILABLE$'): load_run_settings(tmp_path)
    with pytest.raises(RuntimeRefused): load_run_settings(tmp_path,'../engine.toml')
    assert HARD_MAXIMUM_CEILING==10000


def test_run_limits_need_one_bound_and_stay_under_the_hard_maximum():
    assert check_limits(RunLimits(request_limit=40,cycle_limit=3),100)=={'cycle_limit':3,'hour_limit':None,'request_limit':40,'request_hard_maximum':100}
    assert check_limits(RunLimits(request_limit=100,hour_limit=1.5),100)['hour_limit']==1.5
    assert check_limits(RunLimits(request_limit=1,cycle_limit=MAX_CYCLES,hour_limit=MAX_HOURS),1)['cycle_limit']==1000
    with pytest.raises(RuntimeRefused,match='^ENGINE_HARD_MAXIMUM_UNSET$'): check_limits(RunLimits(request_limit=1,cycle_limit=1),0)
    for limits in (RunLimits(request_limit=10),RunLimits(request_limit=10,cycle_limit=0),RunLimits(request_limit=10,cycle_limit=1001),
                   RunLimits(request_limit=10,cycle_limit=True),RunLimits(request_limit=10,hour_limit=0),RunLimits(request_limit=10,hour_limit=169),
                   RunLimits(request_limit=10,hour_limit='1'),'limits'):
        with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_LIMITS_DENIED$'): check_limits(limits,100)
    for requests in (0,101,'5',5.0,None):
        with pytest.raises(RuntimeRefused,match='^ENGINE_REQUEST_LIMIT_DENIED$'): check_limits(RunLimits(request_limit=requests,cycle_limit=1),100)
    with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_LIMITS_DENIED$'): check_limits(RunLimits(request_limit=1,cycle_limit=1),-1)
    assert stop_reason('AI_REQUEST_BUDGET')=='REQUEST_LIMIT' and stop_reason('ENGINE_STOPPED')=='KILL_SWITCH' and stop_reason('ENGINE_HOUR_LIMIT')=='HOUR_LIMIT'
    assert stop_reason('ENGINE_FROZEN')=='FROZEN' and stop_reason('AVAILABLE_RAM_FLOOR')=='STOPPED_AVAILABLE_RAM_FLOOR'


def test_run_gate_stops_on_stop_file_pause_hour_limit_and_freeze(bridge,tmp_path):
    b,_=bridge;store=b.store;ledger=EngineLedger(store);ticks=[0.0]
    gate=RunGate(store,ledger,project_root=tmp_path,hour_limit=1,clock=lambda:ticks[0])
    with pytest.raises(RuntimeRefused,match='^ENGINE_STOPPED$'): gate()  # every store starts paused
    assert gate.trigger=='RESEARCH_STATE'
    set_research_state(store,'RUNNING');assert gate() is True and gate.checks==2 and gate.last_refusal=='ENGINE_STOPPED'
    # The stop file needs no lease: the owner creates it while the run holds the coordinator owner lease.
    stop=tmp_path/'state'/'engine'/'STOP';stop.parent.mkdir(parents=True);stop.write_text('owner stop (fixture)',encoding='utf-8')
    assert gate.stop_file==stop and gate.stop_requested() is True
    with pytest.raises(RuntimeRefused,match='^ENGINE_STOPPED$'): gate()
    assert gate.trigger=='STOP_FILE'
    stop.unlink();assert gate() is True
    set_research_state(store,'PAUSED')
    with pytest.raises(RuntimeRefused,match='^ENGINE_STOPPED$'): gate()
    set_research_state(store,'STOPPED')
    with pytest.raises(RuntimeRefused,match='^ENGINE_STOPPED$'): gate()
    set_research_state(store,'RUNNING');ticks[0]=3599.9;assert gate() is True
    ticks[0]=3600.0
    with pytest.raises(RuntimeRefused,match='^ENGINE_HOUR_LIMIT$'): gate()
    assert gate.elapsed_seconds()==3600.0
    ticks[0]=10.0;frozen=ledger.freeze('AUDITOR_FAILED',{'fixture':True})
    with pytest.raises(RuntimeRefused,match='^ENGINE_FROZEN$'): gate()
    ledger.clear_freeze(frozen['freeze_id'],'owner cleared (fixture)');assert gate() is True
    assert RunGate(store,ledger,project_root=tmp_path).hour_limit is None and RunGate(store,ledger,project_root=tmp_path)() is True
    with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_LIMITS_DENIED$'): RunGate(store,ledger,project_root=tmp_path,hour_limit=0)


def test_run_rows_are_insert_only_and_open_runs_are_visible(bridge):
    b,_=bridge;ledger=EngineLedger(b.store)
    assert ledger.open_runs()==[]
    start=ledger.record_run_phase('run-20261024-0123abcd','START',{'limits':{'cycle_limit':2}})
    assert start['phase']=='START' and [r['run_id'] for r in ledger.open_runs()]==['run-20261024-0123abcd']
    with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_DUPLICATE$'): ledger.record_run_phase('run-20261024-0123abcd','START',{})
    for run_id,phase in (('run-x','START'),('run-20261024-0123abcd','MIDDLE'),(None,'START')):
        with pytest.raises(RuntimeRefused,match='^ENGINE_RECORD_DENIED$'): ledger.record_run_phase(run_id,phase,{})
    with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_UNKNOWN$'): ledger.close_run('run-20261024-ffffffff',{'reason':'x'})
    end=ledger.close_run('run-20261024-0123abcd',{'reason':'CYCLE_LIMIT'})
    assert end['phase']=='END' and ledger.open_runs()==[] and [r['phase'] for r in ledger.run_rows('run-20261024-0123abcd')]==['START','END']
    with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_DUPLICATE$'): ledger.close_run('run-20261024-0123abcd',{'reason':'again'})


def test_daily_summary_is_plain_text_bounded_and_private(bridge,tmp_path):
    b,_=bridge;ledger=EngineLedger(b.store)
    ledger.record_cycle('cycle-0001-aaaaaaaa',1,'END',{'status':'COMPLETED'})
    ledger.record_run('cycle-0001-aaaaaaaa',{'run_id':'job-1','status':'TIMED_OUT'})
    frozen=ledger.freeze('LOOPBACK_CONNECTION',{'fixture':True})
    run={'run_id':'run-20261024-0123abcd','started_at':'2026-10-24T10:00:00+00:00','limits':{'cycle_limit':5,'hour_limit':None,'request_limit':40,'request_hard_maximum':100},
         'owner_approval':'Owner OK: 40 requests (fixture)','models':{'director':{'address':'http://127.0.0.1:1234/v1','model':'synthetic-model'}},
         'cycles':[{'cycle_index':1,'cycle_id':'cycle-0001-aaaaaaaa','status':'COMPLETED','stop_code':None,
                    'hypotheses':[{'id':'h1','title':'Five-session momentum','idea':'x'},{'id':'h2','title':'Mean reversion','idea':'y'}],
                    'candidates':[{'candidate_id':'cycle-0001-aaaaaaaa:h1','hypothesis_id':'h1','status':'REJECTED_DEFLATED','deflation':{'trials':13,'deflated_sharpe':'0.61000000','status':'FAIL'}}]},
                   {'cycle_index':2,'cycle_id':'cycle-0002-bbbbbbbb','status':'STOPPED_AI_REQUEST_BUDGET','stop_code':'AI_REQUEST_BUDGET','hypotheses':[],'candidates':[]}],
         'requests':40,'reason':'REQUEST_LIMIT','elapsed_seconds':930.0}
    text=summary_text(run,ledger,now='2026-10-24T11:00:00+00:00')
    for needle in ('Compertum engine daily summary','Run run-20261024-0123abcd','ended, reason REQUEST_LIMIT','Limits: 5 cycles, 40 AI requests (hard maximum 100)',
                   'Owner approval: Owner OK: 40 requests (fixture)','2 cycles completed in this run, 40 AI requests used, 15.5 minutes elapsed',
                   '- cycle 1: Five-session momentum (h1): REJECTED_DEFLATED, DSR 0.61000000 over 13 trials','- cycle 1: Mean reversion (h2): memo rejected or not specified',
                   '- cycle 2: no hypotheses (STOPPED_AI_REQUEST_BUDGET)','- 1 beat the baseline but failed the deflation gate.','- cycle 2 stopped with AI_REQUEST_BUDGET',
                   '- 1 sandbox jobs ended TIMED_OUT','Queue: empty.',f"Freezes: LOOPBACK_CONNECTION ({frozen['freeze_id']}).",'- director: synthetic-model at http://127.0.0.1:1234/v1'):
        assert needle in text,needle
    path=write_summary(tmp_path,run,ledger,now='2026-10-24T11:00:00+00:00')
    assert path==tmp_path/'state'/'engine'/'summary-run-20261024-0123abcd-2026-10-24.md' and path.read_text(encoding='utf-8')==text
    # Rewritten in place, bounded in size, and refused for a malformed run id.
    big=dict(run,cycles=[dict(run['cycles'][0],cycle_index=i,hypotheses=[{'id':'h1','title':'t'*120,'idea':'x'}]) for i in range(1,2000)])
    assert len(write_summary(tmp_path,big,ledger,now='2026-10-24T11:00:00+00:00').read_bytes())<=65536
    with pytest.raises(RuntimeRefused,match='^ENGINE_RECORD_DENIED$'): write_summary(tmp_path,dict(run,run_id='../x'),ledger)
    assert (PROJECT/'.gitignore').read_text(encoding='utf-8').splitlines().count('state/')==1


def test_owner_commands_clear_freezes_and_close_abandoned_runs(bridge):
    b,_=bridge;store=b.store;ledger=EngineLedger(store)
    frozen=ledger.freeze('AUDITOR_FAILED',{'fixture':True});ledger.record_run_phase('run-20261024-0123abcd','START',{})
    state=control.engine_state(store)
    assert [f['freeze_id'] for f in state['active_freezes']]==[frozen['freeze_id']] and [r['run_id'] for r in state['open_runs']]==['run-20261024-0123abcd'] and state['total_trials']==0
    with pytest.raises(RuntimeRefused,match='^ENGINE_RECORD_DENIED$'): control.close_abandoned_run(store,'run-20261024-0123abcd','')
    with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_UNKNOWN$'): control.close_abandoned_run(store,'run-20261024-ffffffff','note')
    closed=control.close_abandoned_run(store,'run-20261024-0123abcd','owner closed after a crash (fixture)')
    assert closed['reason']=='OWNER_CLOSED' and control.engine_state(store)['open_runs']==[]
    with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_UNKNOWN$'): control.close_abandoned_run(store,'run-20261024-0123abcd','again')
    cleared=control.clear_freeze(store,frozen['freeze_id'],'owner cleared (fixture)')
    assert cleared['cleared_at'] and control.engine_state(store)['active_freezes']==[]
    with pytest.raises(RuntimeRefused,match='^ENGINE_FREEZE_UNKNOWN$'): control.clear_freeze(store,frozen['freeze_id'],'again')


def test_control_command_opens_the_project_and_reports_json(tmp_path,capsys):
    """The command takes the coordinator owner lease once per process, like every owner tool. Each call is its own process."""
    shutil.copyfile(PROJECT/'config/default.toml',tmp_path/'config.toml')
    def command(*args):
        done=subprocess.run([sys.executable,'-m','compertum.ai.engine.control','--project',str(tmp_path),'--config','config.toml',*args],
                            capture_output=True,text=True,timeout=120,cwd=str(tmp_path))
        return done.returncode,json.loads(done.stdout) if done.stdout.strip() else done.stderr[-400:]
    assert command('list')==(0,{'active_freezes':[],'open_runs':[],'total_trials':0})
    assert command('close-run','--run','run-20261024-ffffffff','--note','x')==(2,{'refused':'ENGINE_RUN_UNKNOWN'})
    assert command('clear-freeze','--freeze','nope','--note','x')==(2,{'refused':'ENGINE_FREEZE_UNKNOWN'})
    assert command('nothing')[0]==2
    # In one process, a second acquisition after release is OWNER_BUSY by design (the prior owner is this live process).
    # The command reports that refusal as JSON with exit 2, the same way it reports a busy owner during a run.
    assert control.main(['--project',str(tmp_path),'--config','config.toml','list'])==0
    assert control.main(['--project',str(tmp_path),'--config','config.toml','list'])==2
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])=={'refused':'OWNER_BUSY'}
    assert control.main(['--project',str(tmp_path),'--config','missing.toml','list'])==2
