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
from compertum.ai.models import (ENGINE_ROLES,ModelClient,RoleModel,StoreLedger,auth_headers,load_models,load_providers,loopback_base_url,model_base_url,
                                   remote_base_url)
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
            if state['mode']=='bound': return self.send(b'x'*270000)
            message={'role':'assistant','content':'echo: '+p['messages'][-1]['content']}
            if state['mode']=='tool': message['tool_calls']=[{'function':{'name':'read_file','arguments':'{}'}}]
            if state['mode'] in ('toolcall','toolbad','toolargs','toolmany','toolstop') and 'tools' in p:
                name={'toolbad':'delete_everything'}.get(state['mode'],'write_file')
                arguments={'toolargs':'[1,2]'}.get(state['mode'],'{"file_path":"/main.py","content":"print(1)"}')
                calls=[{'id':f'call_{i}','type':'function','function':{'name':name,'arguments':arguments}} for i in range(9 if state['mode']=='toolmany' else 1)]
                message={'role':'assistant','content':None,'tool_calls':calls}
                return self.send({'choices':[{'message':message,'finish_reason':'stop' if state['mode']=='toolstop' else 'tool_calls'}],'usage':{'prompt_tokens':10,'completion_tokens':3}})
            if state['mode']=='two': return self.send({'choices':[{'message':message,'finish_reason':'stop'}]*2})
            if state['mode'] in ('toollength','lengthbadusage'):  # cut off inside a tool call: the arguments are broken JSON
                calls=[{'id':'call_0','type':'function','function':{'name':'write_file','arguments':'{"file_path":"/main.py","content":"pri'}}]
                usage={'prompt_tokens':900,'completion_tokens':2048} if state['mode']=='toollength' else {'prompt_tokens':'many'}
                return self.send({'choices':[{'message':{'role':'assistant','content':None,'tool_calls':calls},'finish_reason':'length'}],'usage':usage})
            if state['mode']=='length':  # bench baseline 1: a review stopped at the token cap after 518 reasoning tokens
                return self.send({'choices':[{'message':message,'finish_reason':'length'}],
                                  'usage':{'prompt_tokens':900,'completion_tokens':2048,'total_tokens':2948,'completion_tokens_details':{'reasoning_tokens':518}}})
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
    # The committed IDs are either the placeholder (every probe refuses) or the IDs the owner's server reported
    # (flint@q6_k since 24 October 2026). Either way each is one bounded string.
    assert all(isinstance(spec.model,str) and 1<=len(spec.model)<=256 and spec.model.strip()==spec.model for spec in loaded.values())


def test_models_file_loads_four_roles_on_any_loopback_port(tmp_path):
    path=write_models(tmp_path,[('director','http://127.0.0.1:1234/v1','a'),('researcher','http://localhost:8080','b'),
                                ('mathematician','http://127.0.0.1:65535/','c'),('engineer','http://127.0.0.1:1/v1/','d')])
    loaded=load_models(path,tmp_path)
    assert loaded.keys()==ENGINE_ROLES
    assert loaded['researcher']==RoleModel('researcher','http://localhost:8080/v1','b')
    assert loaded['mathematician'].base_url=='http://127.0.0.1:65535/v1' and loaded['engineer'].base_url=='http://127.0.0.1:1/v1'
    with pytest.raises(TypeError): loaded['director']=None


@pytest.mark.parametrize('url',['https://127.0.0.1:1234','http://example.com:1234','http://10.0.0.5:1234','http://user@127.0.0.1:1234',
                                 'http://127.0.0.1:1234/other','http://127.0.0.1','http://127.0.0.1:1234?x=1','http://127.0.0.1.lookalike.example:80',
                                 'http://[::1]:1234','http://127.0.0.1:70000','http://127.0.0.1:0',''])
def test_other_hosts_schemes_and_paths_are_refused(url):
    with pytest.raises(RuntimeRefused,match='NON_LOOPBACK_DENIED'): loopback_base_url(url)


DEEPSEEK={'https://api.deepseek.com':('deepseek','DEEPSEEK_API_KEY')}


def write_providers(root,text):
    (root/'config').mkdir(exist_ok=True);(root/'config'/'providers.toml').write_text(text,encoding='utf-8')


@pytest.mark.parametrize('url,base',[('https://api.deepseek.com','https://api.deepseek.com'),('https://api.deepseek.com/','https://api.deepseek.com'),
                                     ('https://api.deepseek.com:443','https://api.deepseek.com'),('https://API.deepseek.com','https://api.deepseek.com'),
                                     ('https://openrouter.ai/api/v1/','https://openrouter.ai/api/v1')])
def test_remote_addresses_have_one_exact_https_form(url,base):
    # Owner standard, 26 October 2026: any provider the owner lists. The path is kept; host names ignore case.
    assert remote_base_url(url)==base


@pytest.mark.parametrize('url',['http://api.deepseek.com','https://api.deepseek.com:8443','https://unlisted-host.example.com','https://api.deepseek.com.lookalike.example',
                                 'https://user:pw@api.deepseek.com','https://api.deepseek.com/v1?x=1','https://api.deepseek.com/v1','https://deepseek.com',
                                 'https://api.deepseek.com#x','https://127.0.0.1','https://localhost:1234'])
def test_only_listed_providers_and_loopback_are_admitted(url):
    # Test addresses only; nothing is sent. example.com and .example are reserved names that never belong to a real service.
    with pytest.raises(RuntimeRefused,match='NON_LOOPBACK_DENIED'): model_base_url(url,DEEPSEEK)
    assert model_base_url('https://api.deepseek.com',DEEPSEEK)=='https://api.deepseek.com'
    assert model_base_url('http://localhost:8080',DEEPSEEK)=='http://localhost:8080/v1'
    with pytest.raises(RuntimeRefused,match='NON_LOOPBACK_DENIED'): model_base_url('https://api.deepseek.com',{})  # not listed, not admitted


def test_the_provider_file_is_checked(tmp_path):
    assert dict(load_providers(tmp_path))=={}  # no file: loopback only
    write_providers(tmp_path,'[providers.deepseek]\nbase_url = "https://api.deepseek.com/"\nkey_variable = "DEEPSEEK_API_KEY"\n\n[providers.lab]\nbase_url = "https://models.lab.example/v1"\n')
    assert dict(load_providers(tmp_path))=={'https://api.deepseek.com':('deepseek','DEEPSEEK_API_KEY'),'https://models.lab.example/v1':('lab',None)}
    for bad in ('[providers.x]\nbase_url = "http://api.deepseek.com"\n','[providers.loopback]\nbase_url = "https://a.example"\n',
                '[providers.Bad_Name]\nbase_url = "https://a.example"\n','[providers.x]\nbase_url = "https://a.example"\nkey = "sk-secret"\n',
                '[providers.x]\nbase_url = "https://a.example"\nkey_variable = "lower case"\n','[providers.x]\nkey_env = "A_KEY"\n',
                '[providers.x]\nbase_url = "https://a.example"\n[providers.y]\nbase_url = "https://a.example/"\n','[other]\nx = 1\n'):
        write_providers(tmp_path,bad)
        with pytest.raises(RuntimeRefused,match='NON_LOOPBACK_DENIED|UNKNOWN_CONFIG_FIELD|PROVIDER_KEY_IN_FILE'): load_providers(tmp_path)
    # A pasted key gets its own refusal, and the message never holds the value.
    write_providers(tmp_path,'[providers.x]\nbase_url = "https://a.example"\nkey_variable = "sk-'+'0'*32+'"\n')
    with pytest.raises(RuntimeRefused) as caught: load_providers(tmp_path)
    assert caught.value.code=='PROVIDER_KEY_IN_FILE' and 'sk-' not in str(caught.value)


def test_a_model_file_takes_its_provider_and_key_variable_from_the_provider_file(tmp_path):
    write_providers(tmp_path,'[providers.deepseek]\nbase_url = "https://api.deepseek.com"\nkey_variable = "DEEPSEEK_API_KEY"\n')
    path=write_models(tmp_path,[('director','https://api.deepseek.com','deepseek-chat'),('researcher','http://127.0.0.1:1234/v1','flint'),
                                ('mathematician','https://api.deepseek.com/','deepseek-chat'),('engineer','https://api.deepseek.com','deepseek-chat')])
    loaded=load_models(path,tmp_path)
    assert loaded['director']==RoleModel('director','https://api.deepseek.com','deepseek-chat','deepseek','DEEPSEEK_API_KEY')
    assert loaded['researcher']==RoleModel('researcher','http://127.0.0.1:1234/v1','flint')  # roles may mix providers
    (tmp_path/'config'/'providers.toml').unlink()
    with pytest.raises(RuntimeRefused,match='NON_LOOPBACK_DENIED'): load_models(path,tmp_path)


def test_the_key_goes_only_into_the_header_and_never_into_the_record(monkeypatch):
    key='sk-test-'+'a'*24
    remote={role:RoleModel(role,'https://api.deepseek.com','deepseek-chat','deepseek','DEEPSEEK_API_KEY') for role in ENGINE_ROLES}
    assert auth_headers(RoleModel('director','http://127.0.0.1:1234/v1','m'),read=lambda name:key)=={}  # loopback never gets a key
    assert auth_headers(remote['director'],read={'DEEPSEEK_API_KEY':key}.get)=={'Authorization':'Bearer '+key}
    for bad in (None,'','short','has space in it ok','x'*600):
        with pytest.raises(RuntimeRefused,match='^AI_CREDENTIAL_UNAVAILABLE$'): auth_headers(remote['director'],read=lambda name:bad)
    sent=[]
    async def fake_request(self,spec,payload,seconds,headers):
        sent.append(headers)
        raw=json.dumps({'choices':[{'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}],'usage':{'prompt_tokens':5,'completion_tokens':1}}).encode()
        return spec.model,json.loads(raw),raw
    monkeypatch.setattr(ModelClient,'_request',fake_request)
    ledger=ListLedger();c=ModelClient(remote,ledger,memory_floor_bytes=FLOOR,request_limit=3,available_memory=lambda:FLOOR+1,native_limits=False)
    monkeypatch.setattr('compertum.ai.models.user_variable',lambda name:key if name=='DEEPSEEK_API_KEY' else None)
    content,entry=c.complete('director',[{'role':'user','content':'x'}],purpose='e1-fixture')
    assert content=='ok' and sent==[{'Authorization':'Bearer '+key}] and entry['provider']=='deepseek' and entry['address']=='https://api.deepseek.com'
    assert key not in json.dumps(ledger.entries)
    # Without the key: refused before the request counts and before anything is sent.
    monkeypatch.setattr('compertum.ai.models.user_variable',lambda name:None)
    with pytest.raises(RuntimeRefused,match='^AI_CREDENTIAL_UNAVAILABLE$'): c.complete('director',[{'role':'user','content':'x'}],purpose='e1-fixture')
    assert len(sent)==1 and c.requests==1 and ledger.entries[-1]['status']=='REFUSED_AI_CREDENTIAL_UNAVAILABLE'
    # The sender checks hand-built models again: a loopback model with a key variable, or a remote one with a malformed address, is refused.
    for bad in (RoleModel('director','http://127.0.0.1:1234/v1','m','loopback','DEEPSEEK_API_KEY'),RoleModel('director','http://api.deepseek.com','m','deepseek',None)):
        with pytest.raises(RuntimeRefused):
            ModelClient({**remote,'director':bad},ListLedger(),memory_floor_bytes=FLOOR,request_limit=3,available_memory=lambda:FLOOR+1,native_limits=False)


def test_a_model_file_can_raise_the_output_cap_and_time_limit_for_its_model(tmp_path):
    # 26 October 2026: deepseek-v4-pro used all 2048 output tokens on thinking. The model file's cap replaces the caller's.
    with server() as (port,state):
        url=f'http://127.0.0.1:{port}/v1'
        path=write_models(tmp_path,[(role,url,'synthetic-model') for role in sorted(ENGINE_ROLES)])
        path.write_text(path.read_text(encoding='utf-8').replace('model = "synthetic-model"\n','model = "synthetic-model"\nmax_tokens = 8192\nseconds = 300\n',1),encoding='utf-8')
        loaded=load_models(path,tmp_path);capped=[spec for spec in loaded.values() if spec.max_tokens]
        assert len(capped)==1 and capped[0].max_tokens==8192 and capped[0].seconds==300 and sum(1 for spec in loaded.values() if spec.max_tokens is None)==3
        ledger=ListLedger();c=ModelClient(loaded,ledger,memory_floor_bytes=FLOOR,request_limit=5,available_memory=lambda:FLOOR+1,native_limits=False)
        c.complete(capped[0].role,[{'role':'user','content':'x'}],purpose='e1-fixture',max_tokens=2048)
        other=next(spec.role for spec in loaded.values() if spec.max_tokens is None)
        c.complete(other,[{'role':'user','content':'x'}],purpose='e1-fixture',max_tokens=2048)
        assert [p['max_tokens'] for p in state['posts']]==[8192,2048] and ledger.entries[0]['settings']['max_tokens']==8192
        assert ledger.entries[0]['settings']['request_seconds']==300 and ledger.entries[1]['settings']['request_seconds']==120
    for bad in ('max_tokens = 0\n','max_tokens = 20000\n','max_tokens = "8192"\n','seconds = 601\n','seconds = 1.5\n','temperature = 1\n'):
        path=write_models(tmp_path,[(role,'http://127.0.0.1:1234/v1','m') for role in sorted(ENGINE_ROLES)])
        path.write_text(path.read_text(encoding='utf-8').replace('model = "m"\n','model = "m"\n'+bad,1),encoding='utf-8')
        with pytest.raises(RuntimeRefused,match='AI_SETTINGS_DENIED|UNKNOWN_CONFIG_FIELD'): load_models(path,tmp_path)


def test_the_committed_provider_and_deepseek_files_load_and_hold_no_key():
    root=Path(__file__).resolve().parents[1];loaded=load_models(root/'config/models-deepseek.toml',root)
    assert {(spec.base_url,spec.provider,spec.key_env) for spec in loaded.values()}=={('https://api.deepseek.com','deepseek','DEEPSEEK_API_KEY')}
    assert {spec.model for spec in loaded.values()}=={'deepseek-v4-pro'}
    assert {role:(spec.max_tokens,spec.seconds) for role,spec in loaded.items()}=={'director':(8192,300),'researcher':(8192,300),'engineer':(8192,300),'mathematician':(16384,600)}
    for name in ('config/models-deepseek.toml','config/providers.toml'): assert 'sk-' not in (root/name).read_text(encoding='utf-8')


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


# Since 26 October 2026 the reply checks keep their own code; other inner refusals stay AI_RESPONSE_REJECTED with the inner code as refusal_detail.
@pytest.mark.parametrize('mode,code,detail',[('malformed','AI_RESPONSE_REJECTED','AI_JSON_INVALID'),('http','AI_RESPONSE_REJECTED','HTTPStatusError'),
                                             ('bound','AI_RESPONSE_BOUND','AI_RESPONSE_BOUND'),('tool','AI_TOOL_EXECUTION_DENIED','AI_TOOL_EXECUTION_DENIED'),
                                             ('two','AI_RESPONSE_INVALID','AI_RESPONSE_INVALID')])
def test_malformed_tool_and_oversized_responses_are_rejected(mode,code,detail):
    with server(mode) as (port,state):
        ledger=ListLedger()
        with pytest.raises(RuntimeRefused,match=f'^{code}$'):
            client(port,ledger).complete('mathematician',[{'role':'user','content':'x'}],purpose='e1-fixture')
        assert len(state['posts'])==1 and ledger.entries[0]['status']=='REFUSED_'+code and ledger.entries[0]['refusal_detail']==detail


def test_a_reply_stopped_at_the_token_cap_is_truncated_and_keeps_its_counts():
    with server('length') as (port,state):
        ledger=ListLedger()
        with pytest.raises(RuntimeRefused,match='^AI_RESPONSE_TRUNCATED$'):
            client(port,ledger).complete('mathematician',[{'role':'user','content':'x'}],purpose='e1-fixture')
        entry=ledger.entries[0]
        assert entry['status']=='REFUSED_AI_RESPONSE_TRUNCATED' and entry['finish_reason']=='length' and entry['refusal_detail']=='AI_RESPONSE_TRUNCATED'
        assert entry['usage']=={'prompt_tokens':900,'completion_tokens':2048,'total_tokens':2948,'reasoning_tokens':518}


@pytest.mark.parametrize('mode,usage',[('toollength',{'prompt_tokens':900,'completion_tokens':2048}),('lengthbadusage',None)])
def test_a_reply_cut_off_inside_a_tool_call_is_truncated_not_a_tool_fault(mode,usage):
    # Review, 26 October 2026: the tool-call and usage checks ran first, so these replies were recorded as tool faults without counts.
    with server(mode) as (port,state):
        ledger=ListLedger()
        with pytest.raises(RuntimeRefused,match='^AI_RESPONSE_TRUNCATED$'):
            client(port,ledger).complete_tools('engineer',[{'role':'user','content':'build it'}],TOOLS,purpose='e3-fixture',max_tokens=64)
        entry=ledger.entries[0]
        assert entry['status']=='REFUSED_AI_RESPONSE_TRUNCATED' and entry['finish_reason']=='length' and entry['usage']==usage and entry['tool_calls'] is None


def test_a_tool_reply_without_offered_tools_keeps_its_stop_reason_and_counts():
    with server('tool') as (port,state):
        ledger=ListLedger()
        with pytest.raises(RuntimeRefused,match='^AI_TOOL_EXECUTION_DENIED$'):
            client(port,ledger).complete('mathematician',[{'role':'user','content':'x'}],purpose='e1-fixture')
        entry=ledger.entries[0]
        assert entry['finish_reason']=='stop' and entry['usage']=={'prompt_tokens':10,'completion_tokens':3}


def test_a_completed_reply_records_its_stop_reason_and_no_detail():
    with server() as (port,state):
        ledger=ListLedger();_,entry=client(port,ledger).complete('director',[{'role':'user','content':'x'}],purpose='e1-fixture')
        assert entry['finish_reason']=='stop' and entry['refusal_detail'] is None and entry['status']=='COMPLETED'


TOOLS=[{'type':'function','function':{'name':'write_file','description':'Write a file.','parameters':{'type':'object','properties':{'file_path':{'type':'string'},'content':{'type':'string'}},'required':['file_path','content']}}},
       {'type':'function','function':{'name':'run_job','description':'Run the job.','parameters':{'type':'object','properties':{}}}}]


def test_tool_calls_need_an_allowlist_and_are_recorded_by_name_and_argument_hash():
    with server('toolcall') as (port,state):
        ledger=ListLedger();c=client(port,ledger)
        messages=[{'role':'system','content':'ROLE: engineer'},{'role':'user','content':'build it'}]
        content,calls,entry=c.complete_tools('engineer',messages,TOOLS,purpose='e3-fixture',max_tokens=64)
        assert content=='' and calls==[{'id':'call_0','name':'write_file','arguments':{'file_path':'/main.py','content':'print(1)'}}]
        assert state['posts'][-1]['tools']==TOOLS and state['posts'][-1]['tool_choice']=='auto'
        assert entry['status']=='COMPLETED' and entry['tools']==['run_job','write_file']
        assert entry['tool_calls']==[{'id':'call_0','name':'write_file','arguments_sha256':hashlib.sha256(canonical({'file_path':'/main.py','content':'print(1)'})).hexdigest()}]
        # The conversation continues with the assistant's tool call and the tool result. Both message shapes are admitted.
        follow=messages+[{'role':'assistant','content':'','tool_calls':[{'id':'call_0','type':'function','function':{'name':'write_file','arguments':'{"file_path":"/main.py","content":"print(1)"}'}}]},
                         {'role':'tool','content':'written','tool_call_id':'call_0'}]
        state['mode']='ok'
        content,calls,entry=c.complete_tools('engineer',follow,TOOLS,purpose='e3-fixture')
        assert content=='echo: written' and calls==[] and entry['tool_calls'] is None and entry['tools']==['run_job','write_file']
        # Without the allowlist, complete() still refuses the same reply.
        state['mode']='toolcall'
        content,entry=c.complete('engineer',messages,purpose='e3-fixture')
        assert content.startswith('echo:') and entry['tools'] is None  # the fake only emits tool calls when tools are offered
        assert len(state['posts'])==3 and all(e['status']=='COMPLETED' for e in ledger.entries)


@pytest.mark.parametrize('mode,code',[('toolbad','AI_TOOL_EXECUTION_DENIED'),('toolargs','AI_TOOL_EXECUTION_DENIED'),('toolmany','AI_TOOL_EXECUTION_DENIED'),('toolstop','AI_RESPONSE_INCOMPLETE')])
def test_tool_calls_outside_the_allowlist_or_malformed_are_rejected_and_recorded(mode,code):
    with server(mode) as (port,state):
        ledger=ListLedger()
        with pytest.raises(RuntimeRefused,match=f'^{code}$'):
            client(port,ledger).complete_tools('engineer',[{'role':'user','content':'x'}],TOOLS,purpose='e3-fixture')
        assert len(state['posts'])==1 and ledger.entries[0]['status']=='REFUSED_'+code
        # Calls that parsed are kept as evidence even when the reply is rejected; calls that did not parse leave nothing.
        assert (ledger.entries[0]['tool_calls'] is None)==(mode!='toolstop')


def test_tool_allowlists_and_tool_messages_are_checked_before_any_request():
    with server() as (port,state):
        ledger=ListLedger();c=client(port,ledger,limit=20)
        bad_tools=[None,[],TOOLS*9,[{'type':'function','function':{'name':'bad name','parameters':{}}}],[{'type':'retrieval','function':{'name':'x'}}],
                   [{'type':'function','function':{'name':'x','extra':1}}],TOOLS+[TOOLS[0]],[{'type':'function','function':{'name':'x','parameters':{'blob':'y'*70000}}}]]
        for tools in bad_tools:
            with pytest.raises(RuntimeRefused,match='^AI_TOOLS_DENIED$'): c.complete_tools('engineer',[{'role':'user','content':'x'}],tools,purpose='e3-fixture')
        bad_messages=[[{'role':'tool','content':'r'}],[{'role':'tool','content':'r','tool_call_id':''}],[{'role':'assistant','content':'','tool_calls':[]}],
                      [{'role':'assistant','content':'','tool_calls':[{'id':'1','type':'function','function':{'name':'other','arguments':'{}'}}]}],
                      [{'role':'user','content':'x','tool_calls':[]}],[{'role':'system','content':None}]]
        for messages in bad_messages:
            with pytest.raises(RuntimeRefused,match='^AI_MESSAGES_DENIED$'): c.complete_tools('engineer',messages,TOOLS,purpose='e3-fixture')
        # complete() never admits an assistant tool call, because it offers no tools.
        with pytest.raises(RuntimeRefused,match='^AI_MESSAGES_DENIED$'):
            c.complete('engineer',[{'role':'assistant','content':'','tool_calls':[{'id':'1','type':'function','function':{'name':'write_file','arguments':'{}'}}]}],purpose='e3-fixture')
        assert state['posts']==[] and len(ledger.entries)==len(bad_tools)+len(bad_messages)+1
        assert all(e['status'] in ('REFUSED_AI_TOOLS_DENIED','REFUSED_AI_MESSAGES_DENIED') for e in ledger.entries)


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


def test_gate_runs_before_every_request_and_consumes_nothing():
    """Stage E5: the run gate refuses before memory is read, before a request counts, and leaves one refusal row."""
    with server() as (port,state):
        ledger=ListLedger();looks=[];halted=[False]
        def gate():
            if halted[0]: raise RuntimeRefused('ENGINE_STOPPED')
        def available(): looks.append(1);return FLOOR+1
        c=ModelClient(roles(port),ledger,memory_floor_bytes=FLOOR,request_limit=5,available_memory=available,native_limits=False,gate=gate)
        c.complete('engineer',[{'role':'user','content':'x'}],purpose='e5-fixture')
        assert c.requests==1 and len(looks)==1 and len(state['posts'])==1
        halted[0]=True
        with pytest.raises(RuntimeRefused,match='^ENGINE_STOPPED$'): c.complete('engineer',[{'role':'user','content':'y'}],purpose='e5-fixture')
        assert c.requests==1 and len(looks)==1 and len(state['posts'])==1
        assert [e['status'] for e in ledger.entries]==['COMPLETED','REFUSED_ENGINE_STOPPED'] and ledger.entries[1]['request_index']==2 and ledger.entries[1]['available_memory_bytes'] is None
        halted[0]=False
        c.complete('engineer',[{'role':'user','content':'z'}],purpose='e5-fixture');assert c.requests==2 and len(state['posts'])==2
        with pytest.raises(RuntimeRefused,match='^AI_SETTINGS_DENIED$'):
            ModelClient(roles(port),ledger,memory_floor_bytes=FLOOR,request_limit=5,available_memory=available,native_limits=False,gate='not callable')
