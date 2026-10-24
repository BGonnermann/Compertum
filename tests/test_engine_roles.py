"""Stage E3: four Deep Agents roles over the ledgered loopback model, one supervised cycle on a synthetic market, and the freeze path.

These tests need the separate engine environment (.cache/engine-env). In the product environment they are skipped, and the
report counts them as skipped. Every model reply comes from a scripted loopback server. Engineer code really runs in the sandbox.
"""
from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from multiprocessing.connection import Listener
import os
from pathlib import Path
import re
import shutil
import socket
import threading
from uuid import uuid4
import pytest
deepagents=pytest.importorskip('deepagents')
from test_ai_manual import bridge  # noqa: E402,F401  (fixture)
from test_ai_models_interface import FLOOR,ListLedger,roles  # noqa: E402
from test_engine_sandbox import FIXED_TARGETS  # noqa: E402
from compertum.ai.models import ModelClient  # noqa: E402
from compertum.ai.engine import PROVIDER_KEYS,harden_environment  # noqa: E402
from compertum.ai.engine.cycle import Engine,parse_decision,parse_hypotheses,parse_json_reply,run_cycle  # noqa: E402
from compertum.ai.engine.execution import EngineerSandbox,job_files,run_job_tool  # noqa: E402
from compertum.ai.engine.ledger import EngineLedger  # noqa: E402
from compertum.ai.engine.market import market_csv,parse_signals,score_signals,split_market,synthetic_market  # noqa: E402
from compertum.ai.engine.roles import FILE_TOOLS,ROLES,LedgerChatModel,build_role_agent,load_prompt,to_chat_messages  # noqa: E402
from compertum.runtime.errors import RuntimeRefused  # noqa: E402
from compertum.runtime.sandbox import verify_sandbox  # noqa: E402

PROJECT=Path(__file__).resolve().parents[1]
ENGINEER_CODE='''import csv
rows=list(csv.DictReader(open('validation.csv',encoding='utf-8')))
closes=[float(r['close']) for r in rows]
with open('signals.csv','w',encoding='utf-8',newline='') as out:
    out.write('session,position\\n')
    for i,r in enumerate(rows):
        out.write(f"{r['session']},{1 if i>=5 and closes[i]>closes[i-5] else 0}\\n")
print('signals written',len(rows))
'''
ESCAPE_CODE='''import socket,time
s=socket.socket();s.settimeout(5)
try:
    s.connect(('127.0.0.1',PORT));time.sleep(0.4);print('CONNECTED')
except OSError as e: print('DENIED',e)
s.close()
'''
MEMO='1. Idea\nBuy after five rising sessions.\n2. Why it might work\nA planted drift continues for a few sessions.\n3. What would disprove it\nNo excess return on validation.'
SPEC='1. Features\nFive-session close change.\n2. Model\nPosition 1 when the change is positive, else 0.\n3. Assumptions\nDaily closes.\n4. Failure modes\nWhipsaw.'


@contextmanager
def role_server(*,mode='ok',engineer_code=ENGINEER_CODE,model='synthetic-model'):
    """A scripted Chat Completions server. It answers by role (first system line) and by how many tool results it has seen."""
    state={'posts':[],'mode':mode,'engineer_code':engineer_code}
    def reply(payload):
        messages=payload['messages'];role=messages[0]['content'].split('\n',1)[0].removeprefix('ROLE: ')
        tool_results=[m for m in messages if m['role']=='tool'];last_user=[m for m in messages if m['role']=='user'][-1]['content']
        def text(value): return {'role':'assistant','content':value},'stop'
        def call(name,arguments): return {'role':'assistant','content':None,'tool_calls':[{'id':f'call_{len(messages)}','type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]},'tool_calls'
        if state['mode']=='loop': return call('ls',{'path':'/'})  # the same call every round
        if state['mode']=='loopvary': return call('ls',{'path':f'/{len(messages)}'})  # a different call every round
        if state['mode']=='memofault' and role=='researcher' and '"id": "h2"' in last_user: return None,None  # an unusable reply body for one memo
        if last_user.startswith('Improve the system prompt'):
            # E7 (GEPA reflection): a valid improved prompt for the role named in the request, or an invalid one in mode 'badprompt'.
            if state['mode']=='badprompt': return text('An improved prompt without the role marker line.')
            named=re.search(r'for the (\w+) role',last_user).group(1)
            return text(f'ROLE: {named}\nImproved by the fixture reflection. Keep every output format rule of the original prompt.\n'
                        f'Round {len(state["posts"])}: state your reasoning in one short paragraph before the required output.\n')
        if role=='director':
            if last_user.startswith('Pick'):
                return text(json.dumps({'hypotheses':[{'id':'h1','title':'Five-session momentum','idea':'Hold after five rising sessions.'},
                                                      {'id':'h2','title':'Mean reversion','idea':'Buy after five falling sessions.'}]}))
            if last_user.startswith('Approve'): return text(json.dumps({'decision':'approve' if 'hypothesis h1' in last_user else 'reject','reason':'fixture decision'}))
            return text(json.dumps({'agenda':'fixture agenda'}))
        if role=='researcher': return text(MEMO)
        if role=='mathematician': return text(SPEC if last_user.startswith('Write') else 'Review: the code follows the specification. Test the first five sessions.')
        if role=='engineer':
            if 'tools' not in payload: return text('no tools offered')
            if len(tool_results)==0: return call('write_file',{'file_path':'/main.py','content':state['engineer_code']})
            if len(tool_results)==1: return call('run_job',{'entry':'main.py'})
            return text('DONE The program writes momentum signals.')
        return text('unknown role')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,obj):
            raw=json.dumps(obj).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self): self.send({'data':[{'id':model}]})
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state['posts'].append(payload)
            message,finish=reply(payload)
            if message is None: self.send({'choices':[]});return  # the client refuses this empty-choices body as AI_RESPONSE_REJECTED
            self.send({'choices':[{'message':message,'finish_reason':finish}],'usage':{'prompt_tokens':10,'completion_tokens':3}})
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.daemon_threads=True
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try: yield http.server_port,state
    finally: http.shutdown();http.server_close();thread.join(timeout=2)


def client(port,ledger=None,*,limit=60):
    return ModelClient(roles(port),ledger or ListLedger(),memory_floor_bytes=FLOOR,request_limit=limit,available_memory=lambda:FLOOR+1,native_limits=False)


@pytest.fixture(scope='module')
def root():
    folder=PROJECT/'.cache'/'test-runs'/f'e3-engine-{date.today():%Y%m%d}-{uuid4().hex[:8]}'
    folder.mkdir(parents=True)
    yield folder
    shutil.rmtree(folder,ignore_errors=True)


@pytest.fixture(scope='module')
def verification(root):
    pipe=r'\\.\pipe\compertum-e3-'+uuid4().hex[:8];listener=Listener(pipe,'AF_PIPE')
    try: return verify_sandbox(root,memory_floor_bytes=FLOOR,fixed_targets=FIXED_TARGETS,pipe=pipe)
    finally: listener.close()


@pytest.fixture(scope='module')
def market():
    rows=synthetic_market(7,300,planted={'kind':'momentum','window':5,'strength':0.004});train,validation=split_market(rows)
    return {'train_csv':market_csv(train),'validation_csv':market_csv(validation),'validation_rows':validation}


@pytest.fixture
def project(tmp_path):
    """A project folder with the real role prompts. Promotions (E6) land under its state/engine, never under master's."""
    shutil.copytree(PROJECT/'config'/'engine_prompts',tmp_path/'config'/'engine_prompts')
    return tmp_path


def make_engine(bridge,root,verification,market,model_client,project_root):
    b,_=bridge
    return Engine(client=model_client,ledger=EngineLedger(b.store),lease=b.storage.lease,project_root=project_root,sandbox_root=root,verification=verification,
                  train_csv=market['train_csv'],validation_csv=market['validation_csv'],validation_rows=market['validation_rows'],memory_floor_bytes=FLOOR)


def test_prompts_load_from_the_project_and_carry_the_role_marker(tmp_path):
    for role in ROLES:
        text=load_prompt(PROJECT,role)
        assert text.startswith(f'ROLE: {role}\n') and len(text)<=16384
    (tmp_path/'config'/'engine_prompts').mkdir(parents=True)
    (tmp_path/'config'/'engine_prompts'/'director.md').write_text('ROLE: engineer\n'+'x'*50,encoding='utf-8')
    with pytest.raises(RuntimeRefused,match='^ENGINE_PROMPT_INVALID$'): load_prompt(tmp_path,'director')
    with pytest.raises(RuntimeRefused,match='^ENGINE_PROMPT_UNAVAILABLE$'): load_prompt(tmp_path,'researcher')
    (tmp_path/'config'/'engine_prompts'/'engineer.md').write_bytes(b'ROLE: engineer\n'+b'x'*16400)
    with pytest.raises(RuntimeRefused,match='^ENGINE_PROMPT_TOO_LARGE$'): load_prompt(tmp_path,'engineer')
    with pytest.raises(RuntimeRefused,match='^AI_ROLE_DENIED$'): load_prompt(PROJECT,'auditor')


def test_harden_environment_turns_tracing_off_and_removes_provider_key_names(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY','fixture-value-never-read');monkeypatch.setenv('LANGSMITH_TRACING','true')
    result=harden_environment()
    assert 'ANTHROPIC_API_KEY' in result['removed_keys'] and 'ANTHROPIC_API_KEY' not in os.environ
    assert os.environ['LANGSMITH_TRACING']=='false' and os.environ['LANGCHAIN_TRACING_V2']=='false'
    assert all(key not in os.environ for key in PROVIDER_KEYS) and set(result)=={'tracing_off','removed_keys'}
    assert {'LANGSMITH_TRACING','LANGSMITH_TRACING_V2','LANGCHAIN_TRACING_V2','LANGCHAIN_TRACING'}<=set(result['tracing_off'])
    import langsmith.utils as utils
    if hasattr(utils.get_env_var,'cache_clear'): utils.get_env_var.cache_clear()
    assert utils.tracing_is_enabled() is False


def test_director_summary_is_bounded(bridge):
    from compertum.events import canonical
    b,_=bridge;ledger=EngineLedger(b.store)
    for index in range(1,26):
        ledger.record_cycle(f'cycle-{index:04d}-x',index,'END',{'status':'COMPLETED','hypotheses':[{'id':f'h{i}','title':'t'*4000,'idea':'i'*4000} for i in range(3)],
                                                                'candidates':[{'candidate_id':'c','hypothesis_id':f'h{i}','status':'REJECTED','extra':'e'*4000} for i in range(3)]})
    summary=ledger.summary()
    assert summary['cycles_completed']==25 and 1<=len(summary['recent'])<=20 and len(canonical(summary))<=16384
    assert summary['recent'][-1]['cycle_index']==25 and len(summary['recent'][-1]['hypotheses'][0]['title'])==120 and 'extra' not in summary['recent'][-1]['candidates'][0]


def test_ledger_chat_model_sends_every_call_through_the_e1_client():
    from langchain_core.messages import AIMessage,HumanMessage,SystemMessage,ToolMessage
    from langchain_core.tools import tool
    @tool
    def write_file(file_path:str,content:str)->str:
        """Write a file."""
        return 'ok'
    @tool
    def run_job(entry:str)->str:
        """Run a job."""
        return 'ok'
    with role_server() as (port,state):
        ledger=ListLedger();c=client(port,ledger)
        model=LedgerChatModel(client=c,role='engineer',purpose='engine:engineer',model_name='synthetic-model')
        bound=model.bind_tools([write_file,run_job])
        first=bound.invoke([SystemMessage(content='ROLE: engineer\nfixture'),HumanMessage(content='build')])
        assert isinstance(first,AIMessage) and [t['name'] for t in first.tool_calls]==['write_file'] and first.tool_calls[0]['args']['file_path']=='/main.py'
        assert ledger.entries[-1]['tools']==['run_job','write_file'] and ledger.entries[-1]['tool_calls'][0]['name']=='write_file'
        second=bound.invoke([SystemMessage(content='ROLE: engineer\nfixture'),HumanMessage(content='build'),first,ToolMessage(content='written',tool_call_id=first.tool_calls[0]['id'])])
        assert [t['name'] for t in second.tool_calls]==['run_job']
        sent=state['posts'][-1]['messages']
        assert sent[2]['role']=='assistant' and sent[2]['tool_calls'][0]['function']['name']=='write_file' and sent[3]=={'role':'tool','content':'written','tool_call_id':first.tool_calls[0]['id']}
        plain=model.invoke([SystemMessage(content='ROLE: researcher\nfixture'),HumanMessage(content='memo')])
        assert plain.content==MEMO and plain.tool_calls==[] and 'tools' not in state['posts'][-1]
        assert [e['status'] for e in ledger.entries]==['COMPLETED']*3 and all(e['role']=='engineer' for e in ledger.entries)
        with pytest.raises(RuntimeRefused,match='^AI_TOOLS_DENIED$'): model.bind_tools([run_job],tool_choice='any')
        with pytest.raises(RuntimeRefused,match='^AI_SETTINGS_DENIED$'): model.invoke([HumanMessage(content='x')],stop=['\n'])
        with pytest.raises(RuntimeRefused,match='^AI_MESSAGES_DENIED$'): to_chat_messages([HumanMessage(content=[{'type':'image_url','image_url':'x'}])])
        assert to_chat_messages([AIMessage(content=[{'type':'text','text':'a'},'b'])])==[{'role':'assistant','content':'ab'}]


def test_text_roles_get_no_tools_and_the_engineer_gets_file_tools_and_run_job(bridge,root,verification,market,project):
    with role_server() as (port,state):
        c=client(port);engine=make_engine(bridge,root,verification,market,c,project)
        sandbox=EngineerSandbox(root,ledger=engine.ledger,lease=engine.lease,verification=verification,cycle_id='cycle-tools',
                                train_csv=market['train_csv'],validation_csv=market['validation_csv'],memory_floor_bytes=FLOOR)
        engineer=build_role_agent('engineer',c,system_prompt=load_prompt(PROJECT,'engineer'),tools=[run_job_tool(sandbox)])
        researcher=build_role_agent('researcher',c,system_prompt=load_prompt(PROJECT,'researcher'))
        memo=researcher.run('Write the memo.')
        assert memo=={'text':MEMO,'files':{},'messages':2,'tool_calls':0}
        # A text role is one completion: no tools offered, the role prompt as the system message, the task as the only user message.
        assert 'tools' not in state['posts'][-1] and [m['role'] for m in state['posts'][-1]['messages']]==['system','user'] and c.requests==1
        with pytest.raises(RuntimeRefused,match='^ENGINE_FILES_DENIED$'): researcher.run('Write the memo.',{'/x.txt':'y'})
        with pytest.raises(RuntimeRefused,match='^AI_TOOLS_DENIED$'): build_role_agent('director',c,system_prompt=load_prompt(PROJECT,'director'),tools=[run_job_tool(sandbox)])
        built=engineer.run('Build it.')
        assert built['text'].startswith('DONE') and built['tool_calls']==2 and built['files']=={'/main.py':ENGINEER_CODE}
        assert {t['function']['name'] for t in state['posts'][-1]['tools']}==set(FILE_TOOLS)|{'run_job'}
        assert len(sandbox.runs)==1 and sandbox.runs[0]['status']=='COMPLETED' and sandbox.runs[0]['signals_present'] is True
        assert 'signals written' in sandbox.runs[0]['stdout'] and sandbox.completed_signals().startswith('session,position\n')
        assert len(engine.ledger.runs('cycle-tools'))==1 and 'signals' not in engine.ledger.runs('cycle-tools')[0]
        for bad in (dict(role='auditor'),dict(recursion_limit=1),dict(system_prompt='ROLE: director\nwrong')):
            kw=dict(role='researcher',system_prompt=load_prompt(PROJECT,'researcher'));kw.update(bad)
            with pytest.raises(RuntimeRefused): build_role_agent(kw['role'],c,system_prompt=kw['system_prompt'],recursion_limit=kw.get('recursion_limit',40))


def test_recursion_limit_bounds_a_looping_agent():
    with role_server(mode='loopvary') as (port,state):
        c=client(port,limit=50)
        agent=build_role_agent('engineer',c,system_prompt=load_prompt(PROJECT,'engineer'),recursion_limit=6)
        with pytest.raises(RuntimeRefused,match='^ENGINE_STEP_LIMIT$'): agent.run('loop')
        assert 1<=c.requests<=4 and len(state['posts'])==c.requests


def test_repeated_identical_tool_calls_stop_the_agent_before_the_step_limit():
    # Practice run 1: a real model repeated the same file reads until the step limit, 20 requests for nothing.
    with role_server(mode='loop') as (port,state):
        c=client(port,limit=50)
        agent=build_role_agent('engineer',c,system_prompt=load_prompt(PROJECT,'engineer'),recursion_limit=40)
        with pytest.raises(RuntimeRefused,match='^ENGINE_REPEATED_TOOL_CALL$'): agent.run('loop')
        assert c.requests==3 and len(state['posts'])==3
        # The guard starts fresh with the next conversation: three more identical rounds are needed, not one.
        with pytest.raises(RuntimeRefused,match='^ENGINE_REPEATED_TOOL_CALL$'): agent.run('loop again')
        assert c.requests==6


def test_synthetic_market_and_validator_adapter_are_deterministic_and_strict(market):
    assert synthetic_market(7,300,planted={'kind':'momentum','window':5,'strength':0.004})==synthetic_market(7,300,planted={'kind':'momentum','window':5,'strength':0.004})
    assert synthetic_market(7,300)!=synthetic_market(8,300)
    rows=market['validation_rows'];sessions=[str(r['session']) for r in rows]
    foresight='session,position\n'+''.join(f'{s},{1 if i+1<len(rows) and float(rows[i+1]["return"])>0 else 0}\n' for i,s in enumerate(sessions))
    score=score_signals(foresight,rows)
    assert score['beats_baseline'] is True and score['sharpe_status']=='DEFINED' and score['sessions']==len(rows) and json.loads(json.dumps(score))==score
    flat='session,position\n'+''.join(f'{s},0\n' for s in sessions)
    assert score_signals(flat,rows)['beats_baseline'] is False and score_signals(flat,rows)['sharpe_status']=='UNDEFINED'
    hold='session,position\n'+''.join(f'{s},1\n' for s in sessions)
    held=score_signals(hold,rows);assert held['beats_baseline'] is False and held['position_changes']==1
    for bad in ('position,session\n'+''.join(f'{s},1\n' for s in sessions),'session,position\n'+''.join(f'{s},2\n' for s in sessions),
                'session,position\n'+''.join(f'{s},1\n' for s in sessions[:-1]),'session,position\n'+''.join(f'{int(s)+1},1\n' for s in sessions),'',None,'x'*(1024*1024+1)):
        with pytest.raises(RuntimeRefused,match='^ENGINE_SIGNALS_INVALID$'): parse_signals(bad,rows)
    for bad in (dict(seed='7',sessions=300),dict(seed=7,sessions=10),dict(seed=7,sessions=300,planted={'kind':'trend'}),dict(seed=7,sessions=300,planted={'kind':'momentum','window':0,'strength':0.1})):
        with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): synthetic_market(bad.pop('seed'),bad.pop('sessions'),**bad)


def test_replies_are_parsed_strictly():
    assert parse_json_reply('```json\n{"a": 1}\n```')=={'a':1} and parse_json_reply('Sure: {"a": [1]} done')=={'a':[1]}
    for bad in ('[1]','no json here','','{"a":',None,'x'*70000):
        with pytest.raises(RuntimeRefused,match='^ENGINE_REPLY_INVALID$'): parse_json_reply(bad)
    assert parse_hypotheses('{"hypotheses":[{"id":"h1","title":"t","idea":"i"}]}')==[{'id':'h1','title':'t','idea':'i'}]
    for bad in ('{"hypotheses":[]}','{"hypotheses":[{"id":"h1","title":"t"}]}','{"hypotheses":[{"id":"h 1","title":"t","idea":"i"}]}',
                '{"hypotheses":[{"id":"h1","title":"t","idea":"i"},{"id":"h1","title":"t","idea":"i"}]}','{"hypotheses":[{"id":"h%d","title":"t","idea":"i"}]}'.replace('[{','[{"id":"a","title":"t","idea":"i"},{"id":"b","title":"t","idea":"i"},{"id":"c","title":"t","idea":"i"},{')):
        with pytest.raises(RuntimeRefused,match='^ENGINE_REPLY_INVALID$'): parse_hypotheses(bad)
    assert parse_decision('{"decision":"reject","reason":"r"}')=={'decision':'reject','reason':'r'}
    with pytest.raises(RuntimeRefused,match='^ENGINE_REPLY_INVALID$'): parse_decision('{"decision":"maybe","reason":"r"}')


def test_sandbox_tool_refuses_bad_files_and_records_every_run(bridge,root,verification,market):
    b,_=bridge;ledger=EngineLedger(b.store)
    sandbox=EngineerSandbox(root,ledger=ledger,lease=b.storage.lease,verification=verification,cycle_id='cycle-files',
                            train_csv=market['train_csv'],validation_csv=market['validation_csv'],memory_floor_bytes=FLOOR,max_runs=2)
    for files,entry,code in ((({'/../x.py':'print(1)'}),'x.py','ENGINE_FILES_DENIED'),({'/x.py':'print(1)'},'y.py','ENGINE_ENTRY_DENIED'),
                             ({'/pkg/x.py':'print(1)'},'pkg/x.py','ENGINE_ENTRY_DENIED'),({'/train.csv':'a'},'train.csv','ENGINE_FILES_DENIED'),
                             ({f'/f{i}.py':'' for i in range(33)},'f0.py','ENGINE_FILES_DENIED'),({'/x.py':'y'*300000},'x.py','ENGINE_FILES_DENIED'),
                             ({'/x.py':b'bytes'},'x.py','ENGINE_FILES_DENIED'),({},'x.py','ENGINE_FILES_DENIED')):
        assert sandbox.run(files,entry)['status']=='REFUSED_'+code
    assert len(sandbox.runs)==8 and len(ledger.runs('cycle-files'))==8 and all(r['job_folder'] is None for r in sandbox.runs)
    good=sandbox.run({'/main.py':'print("hello")\n'},'main.py')
    assert good['status']=='COMPLETED' and good['exit_code']==0 and good['stdout'].startswith('hello') and good['signals_present'] is False
    assert sandbox.run({'/main.py':'raise SystemExit(3)\n'},'main.py')['status']=='FAILED'
    assert sandbox.run({'/main.py':'print(1)\n'},'main.py')['status']=='REFUSED_ENGINE_RUN_LIMIT'
    assert [r['status'] for r in ledger.runs('cycle-files')][-3:]==['COMPLETED','FAILED','REFUSED_ENGINE_RUN_LIMIT']
    with pytest.raises(RuntimeRefused,match='^SANDBOX_UNVERIFIED'):
        EngineerSandbox(root,ledger=ledger,lease=b.storage.lease,verification={'controls':{},'failed':[]},cycle_id='c',train_csv='a',validation_csv='b',memory_floor_bytes=FLOOR)
    assert job_files({'/a/b.py':'x'})=={'a/b.py':'x'}


def test_one_supervised_cycle_on_the_synthetic_market(bridge,root,verification,market,project):
    # Master's state/engine may hold real practice-run records (since 24 October 2026); this test must add nothing there.
    master_engine_state=PROJECT/'state'/'engine'
    def master_listing(): return sorted(str(p) for p in master_engine_state.rglob('*')) if master_engine_state.exists() else []
    before=master_listing()
    with role_server() as (port,state):
        ledger=ListLedger();c=client(port,ledger);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        assert result['status']=='COMPLETED' and result['stop_code'] is None
        assert [h['id'] for h in result['hypotheses']]==['h1','h2'] and result['decisions']['h1']['decision']=='approve' and result['decisions']['h2']['decision']=='reject'
        assert len(result['candidates'])==1 and result['candidates'][0]['hypothesis_id']=='h1' and result['candidates'][0]['trial'] is True
        candidate=result['candidates'][0]
        assert candidate['run_statuses']==['COMPLETED'] and candidate['status'] in ('QUEUED','REJECTED_AUDIT','REJECTED_DEFLATED','REJECTED')
        score=result['scores']['h1'];assert score['sessions']==len(market['validation_rows']) and score['beats_baseline']==(candidate['status']!='REJECTED')
        # E4: the candidate is one trial, counted before its run; its deflated Sharpe ratio uses that total.
        assert result['total_trials']==1 and candidate['deflation']['trials']==1 and candidate['deflation']['status'] in ('PASS','FAIL','UNDEFINED')
        # E6: a candidate that beats the baseline and passes the gate is audited; it is queued or rejected by the Auditor.
        assert (candidate['status'] in ('QUEUED','REJECTED_AUDIT'))==(score['beats_baseline'] and candidate['deflation']['status']=='PASS')
        assert engine.ledger.total_trials()==1 and engine.ledger.trial_sharpes()==[score['deflation_inputs']['sharpe_per_period']]
        assert result['memos']=={'h1':MEMO,'h2':MEMO} and result['specifications']=={'h1':SPEC} and result['reviews']['h1'].startswith('Review')
        # Archivist: START and END rows, every step recorded, the candidate list before the first run.
        store=engine.ledger;cycles=store.cycles();steps=store.steps(result['cycle_id']);runs=store.runs(result['cycle_id'])
        assert [c['phase'] for c in cycles]==['START','END'] and cycles[1]['status']=='COMPLETED' and cycles[1]['requests_after']==c.requests
        kinds=[(s['role'],s['kind'],s['phase']) for s in steps]
        assert kinds[:2]==[('director','pick','REQUEST'),('director','pick','REPLY')]
        # Every idea task carries the fixed market brief (practice run 1 finding), and no text role is ever offered a tool.
        first_task=state['posts'][0]['messages'][-1]['content']
        assert first_task.startswith('Pick at most') and 'MARKET\n' in first_task and f'validation.csv ({len(market["validation_rows"])} sessions)' in first_task
        assert all('MARKET\n' in p['messages'][1]['content'] for p in state['posts'] if p['messages'][0]['content'].startswith(('ROLE: researcher','ROLE: director')) and 'Approve' not in p['messages'][1]['content'])
        assert all('tools' not in p for p in state['posts'] if not p['messages'][0]['content'].startswith('ROLE: engineer'))
        candidates_at=next(i for i,s in enumerate(steps) if s['kind']=='candidates');first_build=next(i for i,s in enumerate(steps) if s['kind']=='build')
        assert candidates_at<first_build and steps[candidates_at]['count']==1
        assert runs[0]['purpose']=='engineer' and runs[0]['status']=='COMPLETED' and runs[0]['recorded_at']>=steps[candidates_at]['recorded_at'] and 'signals' not in runs[0]
        assert set(r['purpose'] for r in runs[1:])<={'audit'}  # E6: the Auditor's reruns follow a candidate that passed the gate
        assert master_listing()==before  # nothing from this test reaches master's state
        scored=[s for s in steps if s['kind']=='score'][0];assert scored['phase']=='SCORED' and scored['deflation']['trials']==1 and scored['trial_variance']['trial_sharpes']==1
        # Every model call went through the E1 ledger with a known role, and no excluded tool was ever offered.
        assert ledger.entries and all(e['status']=='COMPLETED' and e['role'] in ROLES for e in ledger.entries) and len(ledger.entries)==c.requests
        offered={t['function']['name'] for p in state['posts'] for t in p.get('tools',[])}
        assert offered==set(FILE_TOOLS)|{'run_job'}
        assert store.summary()['cycles_completed']==1 and store.summary()['recent'][0]['candidates'][0]['status']==candidate['status']
        # The sandbox verification's loopback observation is recorded; no freeze happened.
        assert store.active_freezes()==[] and verification['observations']['loopback_connected'] in (True,False)


def test_engineer_code_that_reaches_loopback_freezes_the_engine(bridge,root,verification,market,project):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(60);port=listener.getsockname()[1]
    def accept():
        try:
            import time
            connection,_=listener.accept();time.sleep(.5);connection.close()
        except OSError: pass
    waiter=threading.Thread(target=accept,daemon=True);waiter.start()
    try:
        with role_server(engineer_code=ESCAPE_CODE.replace('PORT',str(port))) as (server_port,state):
            c=client(server_port);engine=make_engine(bridge,root,verification,market,c,project)
            result=run_cycle(engine,1)
            store=engine.ledger;runs=store.runs(result['cycle_id'])
            if verification['observations']['loopback_connected']:
                # This host lets the sandbox reach loopback. The compensating control must catch it and freeze the engine.
                assert result['status']=='STOPPED_ENGINE_FROZEN' and runs[-1]['status']=='FROZEN'
                assert runs[-1]['watcher']['loopback_connections'][0]['remote_port']==port
                frozen=store.active_freezes();assert len(frozen)==1 and frozen[0]['reason']=='LOOPBACK_CONNECTION' and frozen[0]['evidence']['connections'][0]['remote_port']==port
                with pytest.raises(RuntimeRefused,match='^ENGINE_FROZEN$'): run_cycle(engine,2)
                with pytest.raises(RuntimeRefused,match='^ENGINE_FROZEN$'):
                    EngineerSandbox(root,ledger=store,lease=engine.lease,verification=verification,cycle_id='after',train_csv='a',validation_csv='b',memory_floor_bytes=FLOOR).run({'/m.py':'print(1)'},'m.py') and store.require_unfrozen()
                cleared=store.clear_freeze(frozen[0]['freeze_id'],'owner cleared after review (fixture)')
                assert cleared['cleared_at'] and store.active_freezes()==[] and store.require_unfrozen() is True
                with pytest.raises(RuntimeRefused,match='^ENGINE_FREEZE_UNKNOWN$'): store.clear_freeze(frozen[0]['freeze_id'],'again')
            else:
                assert result['status']=='COMPLETED' and store.active_freezes()==[] and 'DENIED' in runs[-1]['stdout']
    finally:
        listener.close();waiter.join(timeout=3)


def test_a_faulty_memo_rejects_that_hypothesis_and_the_cycle_goes_on(bridge,root,verification,market,project):
    # Owner direction, 24 October 2026: a step fault is recorded, not a reason to stop the cycle and learn nothing.
    with role_server(mode='memofault') as (port,state):
        c=client(port);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        assert result['status']=='COMPLETED' and result['stop_code'] is None
        assert result['decisions']['h1']['decision']=='approve' and result['decisions']['h2']=={'decision':'reject','reason':'memo step failed (AI_RESPONSE_REJECTED)'}
        assert result['faults']==[{'role':'researcher','kind':'memo','code':'AI_RESPONSE_REJECTED','hypothesis_id':'h2'}]
        assert [x['hypothesis_id'] for x in result['candidates']]==['h1'] and set(result['memos'])=={'h1'}
        steps=engine.ledger.steps(result['cycle_id']);failed=[s for s in steps if s['phase']=='FAILED']
        assert len(failed)==1 and (failed[0]['role'],failed[0]['kind'],failed[0]['code'],failed[0]['hypothesis_id'])==('researcher','memo','AI_RESPONSE_REJECTED','h2')
        assert engine.ledger.cycles()[-1]['faults']==result['faults']


def test_request_limit_stops_the_cycle_and_is_recorded(bridge,root,verification,market,project):
    with role_server() as (port,state):
        c=client(port,limit=3);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        assert result['status']=='STOPPED_AI_REQUEST_BUDGET' and result['stop_code']=='AI_REQUEST_BUDGET' and c.requests==3
        cycles=engine.ledger.cycles();steps=engine.ledger.steps(result['cycle_id'])
        assert [x['phase'] for x in cycles]==['START','END'] and cycles[1]['status']=='STOPPED_AI_REQUEST_BUDGET'
        assert steps[-1]['phase']=='FAILED' and steps[-1]['code']=='AI_REQUEST_BUDGET' and len(state['posts'])==3
        with pytest.raises(RuntimeRefused,match='^ENGINE_CYCLE_DENIED$'): run_cycle(engine,0)
