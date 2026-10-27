"""The read-only live viewer (tools/engine_tail.py): its lines, the transcript reader, and a replay of a store it never changes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('engine_tail',PROJECT/'tools'/'engine_tail.py');tail=importlib.util.module_from_spec(spec);spec.loader.exec_module(tail)

SCORE={'sharpe':'1.234','benchmark_sharpe':'0.8','beats_baseline':True,'sessions':90,'positions_held':40,'position_changes':9}


def test_a_cycle_end_shows_its_level_and_every_idea():
    record={'status':'COMPLETED','hypotheses':[{'id':'h1','title':'Three-day\nreversal'},{'id':'h2','title':'Noise chase'}],
            'candidates':[{'hypothesis_id':'h1','status':'REJECTED_DEFLATED','deflation':{'deflated_sharpe':'0.6123'},'audit':{'label':'VERIFIED_PASS'}}],
            'scores':{'h1':SCORE},'decisions':{'h1':{'decision':'approve'},'h2':{'decision':'reject','reason':'no falsifier'}},
            'faults':[{'role':'engineer','kind':'build','code':'AI_RESPONSE_TRUNCATED'}],'tool':{'status':'COMPLETED'}}
    lines=tail.cycle_lines(7,'END',record)
    assert lines[0].startswith('CYCLE   #7 END COMPLETED | level 8 of 10: ') and lines[0].endswith('| tool COMPLETED')
    assert lines[1]=='        h1: level 8 | REJECTED_DEFLATED | Sharpe 1.23 vs buy-and-hold 0.80 | deflated 0.61 (gate 0.95) | Auditor VERIFIED_PASS | "Three-day reversal"'
    assert lines[2]=='        h2: not built (no falsifier) | "Noise chase"' and lines[3]=='        fault: engineer build AI_RESPONSE_TRUNCATED'
    assert tail.cycle_lines(8,'START',{'purpose':'bench'})==['CYCLE   #8 START (bench)']


def test_steps_sandbox_jobs_and_model_calls_print_the_useful_part():
    assert tail.step_line('mathematician','proposal',{'phase':'PROPOSED','changed':True,'new_bytes':900})=='GEPA    rewrote mathematician (PROPOSED, 900 bytes)'
    assert tail.step_line('director','pick',{'phase':'REQUEST'}) is None and tail.step_line('director','pick',{'phase':'REQUEST'},all_steps=True).startswith('STEP    director')
    assert tail.step_line('validator','score',{'phase':'SCORED','candidate_id':'c:h2','score':SCORE,'deflation':{'deflated_sharpe':'0.1','trials':40},'status':'REJECTED_DEFLATED'})==(
        'SCORE   h2: Sharpe 1.23 vs buy-and-hold 0.80 | deflated 0.10 over 40 trials | REJECTED_DEFLATED')
    assert tail.sandbox_line({'purpose':'tool','status':'COMPLETED','stdout':'train sessions 250\nwindow 3: -0.27'})=='SANDBOX tool COMPLETED: train sessions 250 window 3: -0.27'
    assert tail.sandbox_line({'purpose':'audit','status':'COMPLETED'}) is None and tail.sandbox_line({'purpose':'audit','status':'COMPLETED'},all_steps=True)
    call={'role':'director','purpose':'engine:director','elapsed_seconds':4.25,'status':'COMPLETED','usage':{'prompt_tokens':900,'completion_tokens':300,'reasoning_tokens':120}}
    assert tail.call_line(call,{'content':'{"hypotheses":\n [1]}'})=='MODEL   director        4.2s in 900 out 300 (thinking 120) | {"hypotheses": [1]}'
    assert tail.call_line(dict(call,role='engineer'),{'tool_calls':[{'name':'write_file'},{'name':'run_job'}]}).endswith('| calls write_file, run_job')
    assert 'GEPA reflects on tool' in tail.call_line(dict(call,purpose='gepa-reflect-tool'),None) and tail.call_line(call,{'content':'x'},text=False).endswith('(thinking 120)')
    assert tail.clip('SCORE   '+'x'*200,20)=='SCORE   xxxxxxxxx...'  # padding kept, line cut


def test_the_transcript_reader_takes_whole_lines_only(tmp_path):
    folder=tmp_path/tail.TRANSCRIPTS;folder.mkdir(parents=True);path=folder/'run-20261026-0123abcd.jsonl'
    path.write_text(json.dumps({'call_id':'a','content':'one'})+'\n'+'{"call_id": "b", "con',encoding='utf-8')  # the second line is still being written
    reader=tail.Transcripts(tmp_path);reader.poll('run-20261026-0123abcd')
    assert reader.take('a')['content']=='one' and reader.take('b') is None and reader.take('a') is None
    with path.open('a',encoding='utf-8') as stream: stream.write('tent": "two"}\n')
    reader.poll('run-20261026-0123abcd');assert reader.take('b')['content']=='two'
    reader.poll('run-20261026-missing');reader.poll(None)  # no file, no run: nothing happens


def test_a_replay_reads_the_store_and_never_changes_it(tmp_path,capsys):
    state=tmp_path/'state';state.mkdir();store=state/'research.sqlite'
    with sqlite3.connect(store) as db:
        db.execute('CREATE TABLE engine_bounded_runs(row_id INTEGER PRIMARY KEY,run_id,phase,recorded_at,record)')
        db.execute('CREATE TABLE engine_cycles(cycle_id,cycle_index,phase,record)')
        db.execute('CREATE TABLE engine_steps(step_id,cycle_id,step_index,role,kind,record)')
        db.execute('CREATE TABLE engine_runs(run_id,cycle_id,status,record)');db.execute('CREATE TABLE engine_model_calls(call_id,role,status,record)')
        db.execute('INSERT INTO engine_bounded_runs(run_id,phase,recorded_at,record) VALUES(?,?,?,?)',('run-1','START','',json.dumps(
            {'recorded_at':'2026-10-26T20:00:00','kind':'gepa','owner_approval':'fixture','models':{'director':{'model':'m'}},'limits':{'cycle_limit':5}})))
        db.execute('INSERT INTO engine_cycles VALUES(?,?,?,?)',('c1',1,'END',json.dumps({'recorded_at':'2026-10-26T20:05:00','status':'COMPLETED','candidates':[]})))
        db.execute('INSERT INTO engine_runs VALUES(?,?,?,?)',('r1','c1-tool','COMPLETED',json.dumps({'recorded_at':'2026-10-26T20:01:00','purpose':'tool','status':'COMPLETED','stdout':'report'})))
    before=hashlib.sha256(store.read_bytes()).hexdigest()
    assert tail.main(['--project',str(tmp_path),'--replay','--once'])==0
    out=capsys.readouterr().out.splitlines()
    assert out[1]=='20:00:00 RUN     run-1 START gepa: "fixture" | models m | limits 5 cycles'
    assert out[2]=='20:01:00 SANDBOX tool COMPLETED: report' and out[3].startswith('20:05:00 CYCLE   #1 END COMPLETED | level 1 of 10')  # time order across tables
    assert hashlib.sha256(store.read_bytes()).hexdigest()==before
    assert tail.main(['--project',str(tmp_path/'nowhere'),'--once'])==2
