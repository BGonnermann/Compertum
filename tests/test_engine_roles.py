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
from compertum.ai.engine.prompts import ROUTING_DEFAULT,routing_text  # noqa: E402
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
        if state['mode']=='loop': return call('read_file',{'file_path':'/main.py'})  # the same call every round
        if state['mode']=='loopvary': return call('read_file',{'file_path':f'/{len(messages)}.py'})  # a different call every round
        if state['mode']=='memofault' and role=='researcher' and '"id": "h2"' in last_user: return None,None  # an unusable reply body for one memo
        if last_user.startswith('Improve the routing'):  # GEPA reflection on the routing (26 October 2026): a valid routing that turns on the rebuild
            return text('ROUTING\nreview: rebuild\nspecify_sees_hypothesis: yes\nengineer_sees_memo: no\nresearcher_sees_lessons: no\n')
        if last_user.startswith('Improve the system prompt'):
            # E7 (GEPA reflection): a valid improved prompt for the role named in the request, or an invalid one in mode 'badprompt'.
            if state['mode']=='badprompt': return text('An improved prompt without the role marker line.')
            named=re.search(r'for the (\w+) role',last_user).group(1)
            return text(f'ROLE: {named}\nImproved by the fixture reflection. Keep every output format rule of the original prompt.\n'
                        f'Round {len(state["posts"])}: state your reasoning in one short paragraph before the required output.\n')
        if role=='director':
            if last_user.startswith('Pick'):
                # Practice run 3: a one-token glitch inside otherwise valid JSON. Mode 'badjson' glitches the first pick reply of a cycle
                # and answers the retry (the task then carries PREVIOUS REPLY); mode 'badjson2' glitches every pick reply.
                if (state['mode']=='badjson' and 'PREVIOUS REPLY' not in last_user) or state['mode']=='badjson2':
                    return text('{"hypotheses": [{"id": "h1", "title":": "Glitched", "idea": "x"}]}')
                return text(json.dumps({'hypotheses':[{'id':'h1','title':'Five-session momentum','idea':'Hold after five rising sessions.'},
                                                      {'id':'h2','title':'Mean reversion','idea':'Buy after five falling sessions.'}]}))
            if last_user.startswith('Approve'): return text(json.dumps({'decision':'approve' if 'hypothesis h1' in last_user else 'reject','reason':'fixture decision'}))
            return text(json.dumps({'agenda':'fixture agenda'}))
        if role=='researcher': return text(MEMO)
        if role=='mathematician': return text(SPEC if last_user.startswith('Write') else 'Review: the code follows the specification. Test the first five sessions.')
        if role=='engineer':
            if 'tools' not in payload: return text('no tools offered')
            # GEPA run 1: the model replied DONE after reading the starter, without any run. Mode 'norun' does that until the retry task arrives.
            if state['mode']=='norun' and 'PREVIOUS REPLY' not in last_user: return text('DONE I read the starter and it looks fine.')
            n=len(tool_results)
            if state['mode']=='readspec':  # the model opens the specification file first, as the task tells it it may
                if n==0: return call('read_file',{'file_path':'/spec.md'})
                n-=1
            if n==0: return call('write_file',{'file_path':'/main.py','content':state['engineer_code']})
            if n==1: return call('run_job',{'entry':'main.py'})
            # Practice run 5: after a completed run the model hunted for signals.csv in its store until the repeat guard stopped it.
            if state['mode']=='postloop': return call('read_file',{'file_path':'/signals.csv'})
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
            if message is None: self.send({'choices':[]});return  # the client refuses this empty-choices body as AI_RESPONSE_INVALID
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
        offered={t['function']['name'] for t in state['posts'][-1]['tools']}
        assert offered==set(FILE_TOOLS)|{'run_job'}=={'read_file','write_file','edit_file','run_job'} and not offered&{'ls','glob','grep','execute','task','delete','write_todos'}
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


def test_each_candidate_has_its_own_engineer_runs_and_the_cycle_total_is_bounded(bridge,root,verification,market):
    # Practice run 11: one count for the whole cycle left later candidates with no run at all.
    b,_=bridge;ledger=EngineLedger(b.store)
    sandbox=EngineerSandbox(root,ledger=ledger,lease=b.storage.lease,verification=verification,cycle_id='cycle-budget',
                            train_csv=market['train_csv'],validation_csv=market['validation_csv'],memory_floor_bytes=FLOOR,max_runs=2)
    code={'/main.py':'print(1)\n'}
    for candidate in range(3):
        sandbox.begin_candidate()
        assert [sandbox.run(code,'main.py')['status'] for _ in range(3)]==['COMPLETED','COMPLETED','REFUSED_ENGINE_RUN_LIMIT']
    # Three candidates of two runs each: the cycle total, max_runs times the candidates per cycle, is spent.
    sandbox.begin_candidate()
    assert sandbox.run(code,'main.py')['status']=='REFUSED_ENGINE_RUN_LIMIT'
    assert [r['status'] for r in ledger.runs('cycle-budget')].count('COMPLETED')==6


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
        assert cycles[1]['routing']==ROUTING_DEFAULT  # without a changed routing file the cycle uses the routes it used before 26 October 2026


def test_the_routing_sends_each_input_where_it_says(bridge,root,verification,market,project):
    """Routing (owner direction, 26 October 2026): every route on, then the review off. The routing changes what roles receive, never the judge."""
    on={'review':'rebuild','specify_sees_hypothesis':'yes','engineer_sees_memo':'yes','researcher_sees_lessons':'yes'}
    (project/'config'/'engine_prompts'/'routing.md').write_text(routing_text(on),encoding='utf-8',newline='\n')
    with role_server() as (port,state):
        engine=make_engine(bridge,root,verification,market,client(port,limit=80),project);result=run_cycle(engine,1)
        assert result['status']=='COMPLETED' and result['routing']==on
        def tasks_of(role): return [p['messages'][1]['content'] for p in state['posts'] if p['messages'][0]['content'].startswith(f'ROLE: {role}\n')]
        assert all('Ledger summary:' in t for t in tasks_of('researcher'))
        specify=[t for t in tasks_of('mathematician') if t.startswith('Write')];assert specify and all('HYPOTHESIS\n' in t for t in specify)
        engineer=[t for t in tasks_of('engineer') if t.startswith(('Build','Rebuild'))];assert engineer[0].startswith('Build') and 'MEMO (the research behind the specification)' in engineer[0]
        # The review goes back to the Engineer for one more build; the last completed run is scored and audited.
        rebuild=[t for t in engineer if t.startswith('Rebuild')];assert len(set(rebuild))==1 and 'REVIEW\nReview: the code follows the specification.' in rebuild[0]
        candidate=result['candidates'][0];assert candidate['run_statuses']==['COMPLETED','COMPLETED'] and result['scores']['h1'] is not None
        assert ('engineer','rebuild','REPLY') in [(s['role'],s['kind'],s['phase']) for s in engine.ledger.steps(result['cycle_id'])]
    # The review off: no review request, the skip is recorded with its reason. A candidate's own routing text replaces the file.
    off=dict(ROUTING_DEFAULT,review='off')
    with role_server() as (port,state):
        engine=make_engine(bridge,root,verification,market,client(port),project)
        engine.prompts={**{role:load_prompt(project,role) for role in ROLES},'routing':routing_text(off)};result=run_cycle(engine,2)
        assert result['status']=='COMPLETED' and result['routing']==off and result['reviews']=={}
        assert not [p for p in state['posts'] if p['messages'][0]['content'].startswith('ROLE: mathematician\n') and p['messages'][1]['content'].startswith('Review')]
        skipped=[s for s in engine.ledger.steps(result['cycle_id']) if s['kind']=='review'];assert [(s['phase'],s['reason']) for s in skipped]==[('REVIEW_SKIPPED','routing: review off')]
    # A routing that does not parse stops before any request.
    engine.prompts={**engine.prompts,'routing':'ROUTING\nreview: always\n'}
    with pytest.raises(RuntimeRefused,match='^ENGINE_ROUTING_INVALID$'): run_cycle(engine,3)


def test_the_second_pick_shows_the_lessons_table_of_the_first_cycle_on_this_market(bridge,root,verification,market,project):
    with role_server() as (port,state):
        ledger=ListLedger();c=client(port,ledger,limit=120);engine=make_engine(bridge,root,verification,market,c,project)
        first=run_cycle(engine,1);posts=len(state['posts']);second=run_cycle(engine,2)
        assert first['status']==second['status']=='COMPLETED' and first['market_sha256']==second['market_sha256']
        pick=state['posts'][posts]['messages'][-1]['content'];assert pick.startswith('Pick at most')
        summary=json.loads(pick.split('Ledger summary:\n',1)[1])
        level=next(r for r in summary['lessons'] if r['idea']=='Five-session momentum')
        assert level['tries']==1 and level['last_cycle']==1 and level['best_outcome'].startswith(f"Level {level['best_level']} of 10.")
        assert {'idea':'Mean reversion','tries':1,'last_cycle':1,'best_level':None,'best_outcome':'Not built: the Director rejected the memo.'} in summary['lessons']
        assert 'lessons' in state['posts'][0]['messages'][-1]['content'] and json.loads(state['posts'][0]['messages'][-1]['content'].split('Ledger summary:\n',1)[1])['lessons']==[]
        starts=[r for r in engine.ledger.cycles() if r['phase']=='START'];assert all(r['market_sha256']==first['market_sha256'] for r in starts)


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
        assert result['decisions']['h1']['decision']=='approve' and result['decisions']['h2']=={'decision':'reject','reason':'memo step failed (AI_RESPONSE_INVALID)','source':'code'}
        assert result['faults']==[{'role':'researcher','kind':'memo','code':'AI_RESPONSE_INVALID','hypothesis_id':'h2'}]
        assert [x['hypothesis_id'] for x in result['candidates']]==['h1'] and set(result['memos'])=={'h1'}
        steps=engine.ledger.steps(result['cycle_id']);failed=[s for s in steps if s['phase']=='FAILED']
        assert len(failed)==1 and (failed[0]['role'],failed[0]['kind'],failed[0]['code'],failed[0]['hypothesis_id'])==('researcher','memo','AI_RESPONSE_INVALID','h2')
        assert engine.ledger.cycles()[-1]['faults']==result['faults']


def test_an_unusable_json_reply_gets_one_retry_that_shows_the_failure(bridge,root,verification,market,project):
    with role_server(mode='badjson') as (port,state):
        c=client(port);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        assert result['status']=='COMPLETED' and [h['id'] for h in result['hypotheses']]==['h1','h2'] and result['faults']==[]
        picks=[s for s in engine.ledger.steps(result['cycle_id']) if s['kind']=='pick']
        assert [(s['phase'],s.get('retry')) for s in picks]==[('REQUEST',None),('REPLY',None),('INVALID',0),('REQUEST',1),('REPLY',1)]
        assert picks[2]['code']=='ENGINE_REPLY_INVALID'
        retry_task=state['posts'][1]['messages'][-1]['content']
        assert retry_task.startswith('Pick at most') and 'not usable (ENGINE_REPLY_INVALID)' in retry_task and 'PREVIOUS REPLY\n{"hypotheses"' in retry_task
    with role_server(mode='badjson2') as (port,state):
        c=client(port);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        # Two unusable replies: two INVALID rows, no hypotheses, the cycle completes with nothing to do, and only two requests were spent.
        assert result['status']=='COMPLETED' and result['hypotheses']==[] and c.requests==2
        assert [s.get('retry') for s in engine.ledger.steps(result['cycle_id']) if s['kind']=='pick' and s['phase']=='INVALID']==[0,1]


def test_a_build_fault_after_a_completed_run_still_scores_the_signals(bridge,root,verification,market,project):
    with role_server(mode='postloop') as (port,state):
        c=client(port);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        candidate=result['candidates'][0]
        assert result['status']=='COMPLETED' and candidate['run_statuses']==['COMPLETED'] and candidate['status']!='BUILD_FAILED'
        assert candidate['status'] in ('QUEUED','REJECTED_AUDIT','REJECTED_DEFLATED','REJECTED') and result['scores']['h1']['sessions']==len(market['validation_rows'])
        assert result['faults']==[{'role':'engineer','kind':'build','code':'ENGINE_REPEATED_TOOL_CALL','candidate_id':candidate['candidate_id']}]
        steps=engine.ledger.steps(result['cycle_id'])
        review=[s for s in steps if s['kind']=='review'][0];assert review['phase']=='REVIEW_SKIPPED' and 'faulted after a completed run' in review['reason']
        # The Engineer starts from the starter program and run_job's result says the signals are accepted and what to do next.
        build_task=next(p['messages'][1]['content'] for p in state['posts'] if p['messages'][0]['content'].startswith('ROLE: engineer'))
        assert build_task.startswith('Build this specification') and 'starter program' in build_task and 'SPECIFICATION\n' in build_task
        # Practice runs 5 to 10 sent the literal text of a template here. The task must hold the specification itself, a TRAIN sample
        # and no validation row; the placeholder text must not appear.
        assert build_task.endswith(SPEC) and '{state[' not in build_task and '[hid]' not in build_task
        sample=build_task.split('TRAIN SAMPLE (the first rows of train.csv)\n',1)[1].split('\n\nSPECIFICATION',1)[0].splitlines()
        assert sample[0]=='session,close,return' and len(sample)==7 and sample[1].startswith('0,')
        first_validation=market['validation_rows'][0]
        assert f"\n{first_validation['session']}," not in build_task and first_validation['close'] not in build_task
        tool_results=[m['content'] for p in state['posts'] for m in p['messages'] if m['role']=='tool' and '"signals_present": true' in m['content']]
        assert tool_results and 'is accepted' in tool_results[0] and 'Reply with the single word DONE' in tool_results[0]


def test_an_engineer_reply_without_a_run_gets_one_retry(bridge,root,verification,market,project):
    with role_server(mode='norun') as (port,state):
        c=client(port);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        candidate=result['candidates'][0]
        assert result['status']=='COMPLETED' and result['faults']==[] and candidate['run_statuses']==['COMPLETED'] and candidate['status']!='NO_SIGNALS'
        builds=[s for s in engine.ledger.steps(result['cycle_id']) if s['kind']=='build']
        assert [(s['phase'],s.get('retry')) for s in builds]==[('REQUEST',None),('REPLY',None),('INVALID',0),('REQUEST',1),('REPLY',1)] and builds[2]['code']=='ENGINE_NO_RUN'
        retry_task=[p['messages'][1]['content'] for p in state['posts'] if p['messages'][0]['content'].startswith('ROLE: engineer') and 'PREVIOUS REPLY' in p['messages'][1]['content']][0]
        assert retry_task.startswith('Build this specification') and 'without running the program' in retry_task and 'DONE I read the starter' in retry_task and 'SPECIFICATION\n' in retry_task


def test_the_engineer_can_read_the_specification_file_from_its_store(bridge,root,verification,market,project):
    with role_server(mode='readspec') as (port,state):
        c=client(port);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        candidate=result['candidates'][0]
        assert result['status']=='COMPLETED' and result['faults']==[] and candidate['run_statuses']==['COMPLETED']
        reads=[m['content'] for p in state['posts'] for m in p['messages'] if m['role']=='tool' and 'Features' in m['content'] and 'Failure modes' in m['content']]
        assert reads and SPEC.splitlines()[0] in reads[0]  # read_file returned the specification text, not an error


def test_a_streak_of_read_only_rounds_stops_the_engineer_with_no_progress():
    # Practice run 10: a real model read different missing files round after round, which the identical-call guard cannot see.
    with role_server(mode='loopvary') as (port,state):
        c=client(port,limit=50)
        agent=build_role_agent('engineer',c,system_prompt=load_prompt(PROJECT,'engineer'),recursion_limit=40)
        with pytest.raises(RuntimeRefused,match='^ENGINE_NO_PROGRESS$'): agent.run('look around')
        assert c.requests==5 and len(state['posts'])==5  # READ_ONLY_LIMIT rounds, the last one already in the ledger
        with pytest.raises(RuntimeRefused,match='^ENGINE_NO_PROGRESS$'): agent.run('look around again')
        assert c.requests==10  # the streak starts from zero with the next conversation


def test_request_limit_stops_the_cycle_and_is_recorded(bridge,root,verification,market,project):
    with role_server() as (port,state):
        c=client(port,limit=3);engine=make_engine(bridge,root,verification,market,c,project)
        result=run_cycle(engine,1)
        assert result['status']=='STOPPED_AI_REQUEST_BUDGET' and result['stop_code']=='AI_REQUEST_BUDGET' and c.requests==3
        cycles=engine.ledger.cycles();steps=engine.ledger.steps(result['cycle_id'])
        assert [x['phase'] for x in cycles]==['START','END'] and cycles[1]['status']=='STOPPED_AI_REQUEST_BUDGET'
        assert steps[-1]['phase']=='FAILED' and steps[-1]['code']=='AI_REQUEST_BUDGET' and len(state['posts'])==3
        with pytest.raises(RuntimeRefused,match='^ENGINE_CYCLE_DENIED$'): run_cycle(engine,0)


def test_the_chat_message_carries_the_stop_reason_and_the_token_counts():
    """26 October 2026: LangChain sees what the ledger records, so a capped reply is visible in the agent's own messages too."""
    from compertum.ai.engine.roles import LedgerChatModel,usage_metadata
    assert usage_metadata(None) is None and usage_metadata({'prompt_tokens':'x','completion_tokens':1}) is None
    assert usage_metadata({'prompt_tokens':10,'completion_tokens':3})=={'input_tokens':10,'output_tokens':3,'total_tokens':13}
    entry={'call_id':'c1','model_reported':'m','request_index':1,'finish_reason':'stop','usage':{'prompt_tokens':900,'completion_tokens':700,'total_tokens':1600,'reasoning_tokens':512}}
    class Fake:
        def complete(self,role,chat,**settings): return 'reply',entry
    model=LedgerChatModel(client=Fake(),role='mathematician',purpose='fixture',model_name='m')
    message=model.invoke('x')
    assert message.response_metadata['finish_reason']=='stop' and message.response_metadata['call_id']=='c1'
    assert message.usage_metadata=={'input_tokens':900,'output_tokens':700,'total_tokens':1600,'output_token_details':{'reasoning':512}}
