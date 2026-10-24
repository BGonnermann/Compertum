"""Stage E1: any loopback port works, other hosts are refused, the ledger records every call, the memory floor blocks."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import pytest
from test_ai_manual import bridge
from compertum.ai.models import ENGINE_ROLES,ModelClient,RoleModel,StoreLedger,load_models,loopback_base_url
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused

FLOOR=8*1024**3


@contextmanager
def server(mode='ok',model='synthetic-model'):
    state={'gets':0,'posts':[],'mode':mode}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,obj,code=200):
            raw=obj if isinstance(obj,bytes) else json.dumps(obj).encode()
            self.send_response(code);self.send_header('Content-Length',str(len(raw)));self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError): pass
        def do_GET(self):
            state['gets']+=1
            if self.path=='/v1/models': self.send({'data':[{'id':model}]})
            else: self.send({},404)
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']));p=json.loads(raw);state['posts'].append(p)
            if state['mode']=='timeout': time.sleep(1.5)
            if state['mode']=='malformed': return self.send(b'{no')
            if state['mode']=='http': return self.send({},503)
            if state['mode']=='bound': return self.send(b'x'*70000)
            message={'role':'assistant','content':'echo: '+p['messages'][-1]['content']}
            if state['mode']=='tool': message['tool_calls']=[{'function':{'name':'read_file','arguments':'{}'}}]
            if state['mode']=='two': return self.send({'choices':[{'message':message,'finish_reason':'stop'}]*2})
            usage={'prompt_tokens':10,'completion_tokens':3}
            if state['mode']=='bigusage': usage.update(total_tokens=13,vendor_blob='x'*30000)
            self.send({'choices':[{'message':message,'finish_reason':'stop'}],'usage':usage})
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.daemon_threads=True
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try: yield http.server_port,state
    finally: http.shutdown();http.server_close();thread.join(timeout=2)


class ListLedger:
    def __init__(self): self.entries=[]
    def record(self,entry): self.entries.append(entry);return entry


def roles(port,model='synthetic-model'):
    return {role:RoleModel(role,f'http://127.0.0.1:{port}/v1',model) for role in ENGINE_ROLES}


def client(port,ledger=None,*,available=FLOOR+1,limit=5,model='synthetic-model'):
    return ModelClient(roles(port,model),ledger or ListLedger(),memory_floor_bytes=FLOOR,request_limit=limit,
                       available_memory=lambda:available,native_limits=False)


def write_models(root,entries):
    (root/'config').mkdir(exist_ok=True)
    text=''.join(f'[roles.{role}]\nbase_url = "{url}"\nmodel = "{model}"\n\n' for role,url,model in entries)
    (root/'config/models.toml').write_text(text,encoding='utf-8');return root/'config/models.toml'


def test_committed_models_file_loads_with_lm_studio_default_port():
    root=Path(__file__).resolve().parents[1];loaded=load_models(root/'config/models.toml',root)
    assert loaded.keys()==ENGINE_ROLES and {spec.base_url for spec in loaded.values()}=={'http://127.0.0.1:1234/v1'}
    # The server-reported IDs are set after the first practice run. Until then every probe must refuse.
    assert {spec.model for spec in loaded.values()}=={'SET_FROM_SERVER_MODEL_LIST'}


def test_models_file_loads_four_roles_on_any_loopback_port(tmp_path):
    path=write_models(tmp_path,[('director','http://127.0.0.1:1234/v1','a'),('researcher','http://localhost:8080','b'),
                                ('mathematician','http://127.0.0.1:65535/','c'),('engineer','http://127.0.0.1:1/v1/','d')])
    loaded=load_models(path,tmp_path)
    assert loaded.keys()==ENGINE_ROLES
    assert loaded['researcher']==RoleModel('researcher','http://localhost:8080/v1','b')
    assert loaded['mathematician'].base_url=='http://127.0.0.1:65535/v1' and loaded['engineer'].base_url=='http://127.0.0.1:1/v1'
    with pytest.raises(TypeError): loaded['director']=None


@pytest.mark.parametrize('url',['https://127.0.0.1:1234','http://example.com:1234','http://10.0.0.5:1234','http://user@127.0.0.1:1234',
                                 'http://127.0.0.1:1234/other','http://127.0.0.1','http://127.0.0.1:1234?x=1','http://127.0.0.1.evil.com:80',
                                 'http://[::1]:1234','http://127.0.0.1:70000','http://127.0.0.1:0',''])
def test_other_hosts_schemes_and_paths_are_refused(url):
    with pytest.raises(RuntimeRefused,match='NON_LOOPBACK_DENIED'): loopback_base_url(url)


@pytest.mark.parametrize('fault',['missing_role','extra_role','extra_key','outside'])
def test_incomplete_or_foreign_model_files_are_refused(tmp_path,fault):
    entries=[(role,'http://127.0.0.1:1234/v1','m') for role in sorted(ENGINE_ROLES)]
    if fault=='missing_role': entries=entries[:-1]
    if fault=='extra_role': entries.append(('validator','http://127.0.0.1:1234/v1','m'))
    path=write_models(tmp_path,entries)
    if fault=='extra_key': path.write_text(path.read_text(encoding='utf-8')+'[limits]\nx = 1\n',encoding='utf-8')
    root=tmp_path/'elsewhere' if fault=='outside' else tmp_path
    with pytest.raises(RuntimeRefused,match='UNKNOWN_CONFIG_FIELD|CONFIG_OUTSIDE_PROJECT'): load_models(path,root)


def test_completion_records_role_address_model_and_hashes_for_each_call():
    with server() as (port,state):
        ledger=ListLedger();c=client(port,ledger)
        messages=[{'role':'system','content':'Synthetic fixture.'},{'role':'user','content':'two plus two'}]
        content,entry=c.complete('engineer',messages,purpose='e1-fixture',max_tokens=64)
        assert content=='echo: two plus two' and entry['status']=='COMPLETED'
        assert state['posts']==[{'model':'synthetic-model','messages':messages,'temperature':0,'max_tokens':64,'stream':False}]
        assert ledger.entries==[entry]
        assert (entry['role'],entry['provider'],entry['address'],entry['model_requested'],entry['model_reported'])==(
            'engineer','loopback',f'http://127.0.0.1:{port}/v1','synthetic-model','synthetic-model')
        assert entry['prompt_sha256']==hashlib.sha256(canonical(messages)).hexdigest() and len(entry['response_sha256'])==64
        assert entry['usage']=={'prompt_tokens':10,'completion_tokens':3} and entry['request_index']==1
        assert entry['available_memory_bytes']==FLOOR+1 and entry['memory_floor_bytes']==FLOOR
        assert c.probe('director')=='synthetic-model'


def test_server_without_the_configured_model_gets_no_completion():
    with server(model='other-model') as (port,state):
        ledger=ListLedger()
        with pytest.raises(RuntimeRefused,match='MODEL_IDENTITY_MISMATCH'):
            client(port,ledger).complete('director',[{'role':'user','content':'x'}],purpose='e1-fixture')
        assert state['posts']==[] and ledger.entries[0]['status']=='REFUSED_MODEL_IDENTITY_MISMATCH'


def test_memory_floor_blocks_before_any_request():
    with server() as (port,state):
        ledger=ListLedger()
        with pytest.raises(RuntimeRefused,match='AVAILABLE_RAM_FLOOR'):
            client(port,ledger,available=FLOOR-1).complete('researcher',[{'role':'user','content':'x'}],purpose='e1-fixture')
        assert state['gets']==0 and state['posts']==[]
        assert ledger.entries[0]['status']=='REFUSED_AVAILABLE_RAM_FLOOR' and ledger.entries[0]['available_memory_bytes']==FLOOR-1
        assert client(port,ledger,available=FLOOR).complete('researcher',[{'role':'user','content':'x'}],purpose='e1-fixture')[0]=='echo: x'


def test_request_limit_refuses_before_http_and_counts_failed_attempts():
    with server('http') as (port,state):
        ledger=ListLedger();c=client(port,ledger,limit=2)
        for _ in range(2):
            with pytest.raises(RuntimeRefused,match='AI_RESPONSE_REJECTED'): c.complete('director',[{'role':'user','content':'x'}],purpose='e1-fixture')
        with pytest.raises(RuntimeRefused,match='AI_REQUEST_BUDGET'): c.complete('director',[{'role':'user','content':'x'}],purpose='e1-fixture')
        assert len(state['posts'])==2 and [e['status'] for e in ledger.entries][-1]=='REFUSED_AI_REQUEST_BUDGET'


@pytest.mark.parametrize('mode',['malformed','http','bound','tool','two'])
def test_malformed_tool_and_oversized_responses_are_rejected(mode):
    with server(mode) as (port,state):
        ledger=ListLedger()
        with pytest.raises(RuntimeRefused,match='AI_RESPONSE_REJECTED'):
            client(port,ledger).complete('mathematician',[{'role':'user','content':'x'}],purpose='e1-fixture')
        assert len(state['posts'])==1 and ledger.entries[0]['status']=='REFUSED_AI_RESPONSE_REJECTED'


def test_timeout_is_reported_as_unverified_completion():
    with server('timeout') as (port,state):
        with pytest.raises(RuntimeRefused,match='LOCAL_COMPLETION_UNVERIFIED'):
            client(port).complete('engineer',[{'role':'user','content':'x'}],purpose='e1-fixture',seconds=1)


def test_secret_shaped_prompt_unknown_role_and_bad_settings_send_nothing_and_are_recorded():
    with server() as (port,state):
        ledger=ListLedger();c=client(port,ledger)
        with pytest.raises(RuntimeRefused,match='AI_SENSITIVE_INPUT_DENIED'):
            c.complete('engineer',[{'role':'user','content':'api_key sk-abcdefghijklmnop'}],purpose='e1-fixture')
        with pytest.raises(RuntimeRefused,match='AI_ROLE_DENIED'): c.complete('validator',[{'role':'user','content':'x'}],purpose='e1-fixture')
        with pytest.raises(RuntimeRefused,match='AI_ROLE_DENIED'): c.complete(None,[{'role':'user','content':'x'}],purpose='e1-fixture')
        with pytest.raises(RuntimeRefused,match='AI_SETTINGS_DENIED'): c.complete('engineer',[{'role':'user','content':'x'}],purpose='e1-fixture',max_tokens=0)
        with pytest.raises(RuntimeRefused,match='AI_MESSAGES_DENIED'): c.complete('engineer',[{'role':'tool','content':'x'}],purpose='e1-fixture')
        assert state['gets']==0 and state['posts']==[]
        assert [e['status'] for e in ledger.entries]==['REFUSED_AI_SENSITIVE_INPUT_DENIED','REFUSED_AI_ROLE_DENIED','REFUSED_AI_ROLE_DENIED',
                                                       'REFUSED_AI_SETTINGS_DENIED','REFUSED_AI_MESSAGES_DENIED']
        assert ledger.entries[1]['address'] is None and ledger.entries[2]['role']=='INVALID_ROLE'


def test_client_rechecks_every_address_and_model_id():
    good=roles(1234)
    with pytest.raises(RuntimeRefused,match='NON_LOOPBACK_DENIED'):
        ModelClient(good|{'engineer':RoleModel('engineer','http://example.com:80/v1','m')},ListLedger(),memory_floor_bytes=FLOOR,request_limit=1,native_limits=False)
    with pytest.raises(RuntimeRefused,match='UNKNOWN_CONFIG_FIELD'):
        ModelClient(good|{'engineer':RoleModel('engineer','http://127.0.0.1:1234','m')},ListLedger(),memory_floor_bytes=FLOOR,request_limit=1,native_limits=False)
    with pytest.raises(RuntimeRefused,match='MODEL_IDENTITY_UNVERIFIED'):
        ModelClient(good|{'engineer':RoleModel('engineer','http://127.0.0.1:1234/v1',' m')},ListLedger(),memory_floor_bytes=FLOOR,request_limit=1,native_limits=False)


def test_unexpected_failure_still_leaves_a_complete_record():
    with server() as (port,state):
        ledger=ListLedger()
        def broken(): raise RuntimeError('synthetic fault')
        c=ModelClient(roles(port),ledger,memory_floor_bytes=FLOOR,request_limit=2,available_memory=broken,native_limits=False)
        with pytest.raises(RuntimeError,match='synthetic fault'): c.complete('director',[{'role':'user','content':'x'}],purpose='e1-fixture')
        assert state['posts']==[] and ledger.entries[0]['status']=='FAILED_UNEXPECTED' and ledger.entries[0]['elapsed_seconds']>=0


def test_non_finite_or_non_numeric_settings_are_refused_and_still_recorded():
    with server() as (port,state):
        ledger=ListLedger();c=client(port,ledger)
        with pytest.raises(RuntimeRefused,match='AI_SETTINGS_DENIED'): c.complete('engineer',[{'role':'user','content':'x'}],purpose='e1-fixture',temperature=float('nan'))
        with pytest.raises(RuntimeRefused,match='AI_SETTINGS_DENIED'): c.complete('engineer',[{'role':'user','content':'x'}],purpose='e1-fixture',max_tokens='64')
        with pytest.raises(RuntimeRefused,match='AI_SETTINGS_DENIED'): c.complete('engineer',[{'role':'user','content':'x'}],purpose='e1-fixture',seconds=True)
        assert state['gets']==0 and [e['status'] for e in ledger.entries]==['REFUSED_AI_SETTINGS_DENIED']*3
        assert ledger.entries[0]['settings']['temperature'] is None and ledger.entries[1]['settings']['max_tokens'] is None
        assert ledger.entries[2]['settings']['request_seconds'] is None and all(canonical(e) for e in ledger.entries)


def test_usage_record_keeps_only_token_counts():
    with server('bigusage') as (port,state):
        _,entry=client(port).complete('director',[{'role':'user','content':'x'}],purpose='e1-fixture')
        assert entry['usage']=={'prompt_tokens':10,'completion_tokens':3,'total_tokens':13} and len(canonical(entry))<4096


def test_store_ledger_persists_every_call_durably(bridge):
    b,_=bridge;ledger=StoreLedger(b.store)
    with server() as (port,state):
        c=client(port,ledger,limit=3)
        c.complete('director',[{'role':'user','content':'one'}],purpose='e1-fixture')
        with pytest.raises(RuntimeRefused): client(port,ledger,available=1).complete('director',[{'role':'user','content':'two'}],purpose='e1-fixture')
    rows=ledger.rows()
    assert [r['status'] for r in rows]==['COMPLETED','REFUSED_AVAILABLE_RAM_FLOOR']
    assert rows[0]['model_reported']=='synthetic-model' and rows[0]['address']==f'http://127.0.0.1:{port}/v1'
    assert StoreLedger(b.store).rows()==rows
