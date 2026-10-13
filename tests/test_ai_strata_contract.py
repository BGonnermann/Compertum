"""Real disposable loopback server; these checks do not qualify Strata."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import pytest
from test_ai_manual import bridge
from ai_fixture import ai_task
from compertum.ai.strata import StrataAdapter,StrataProfile
from compertum.runtime.errors import RuntimeRefused
from compertum.events import canonical

@contextmanager
def server(mode='ok'):
    state={'posts':[],'active':0,'mode':mode}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,obj,code=200):
            raw=obj if isinstance(obj,bytes) else json.dumps(obj).encode()
            self.send_response(code);self.send_header('Content-Length',str(len(raw)));self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError): pass
        def do_GET(self):
            if self.path=='/health':
                if state['mode']=='strata-health': self.send({'status':'ok','loaded':True,'service':'strata','api_key':False})
                elif state['mode']=='unsafe-health': self.send({'loaded':True,'active_requests':0,'api_key':'credential-shaped-value'})
                else: self.send({'loaded':True,'active_requests':state['active']})
            elif self.path=='/slots': self.send([{'id':0,'n_ctx':16384,'is_processing':state['active']!=0}])
            elif self.path=='/v1/models': self.send({'data':[{'id':'synthetic-model'}]})
            else: self.send({},404)
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']));p=json.loads(raw);state['posts'].append(p);state['active']+=1
            try:
                if state['mode']=='timeout': time.sleep(1.5)
                if state['mode']=='malformed': return self.send(b'{no')
                if state['mode']=='http': return self.send({},503)
                message={'role':'assistant','content':json.dumps({'echo':p['messages'][-1]['content']})}
                if state['mode']=='fictional' and 'tools' in p:
                    fixture=p['tools'][0]['function']['parameters']['properties']['fixture_id']['enum'][0]
                    call={'id':'synthetic-call','type':'function','function':{'name':'fixture_lookup','arguments':json.dumps({'fixture_id':fixture})}}
                    return self.send({'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[call]},'finish_reason':'tool_calls'}]})
                if state['mode']=='tool': message['tool_calls']=[{'function':{'name':'read_file','arguments':'{}'}}]
                if state['mode']=='overflow': message['content']='x'*3000
                if state['mode']=='bound': return self.send(b'x'*70000)
                self.send({'choices':[{'message':message,'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':10}})
            finally: state['active']-=1
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.daemon_threads=True
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try: yield http.server_port,state
    finally: http.shutdown();http.server_close();thread.join(timeout=2)

def adapter(bridge,port):
    b,_=bridge
    return StrataAdapter(b,StrataProfile('http://127.0.0.1:8080','synthetic-model','a'*64),
        token_counter=lambda messages:len(canonical(messages)),_fixture_port=port)

def test_contexts_are_isolated_and_usage_is_real_server_telemetry(bridge):
    _,root=bridge
    with server() as (port,state):
        a=adapter(bridge,port);one,_=ai_task(root,'strata');two,_=ai_task(root,'strata')
        first=a.request_proposal(one,[{'role':'user','content':'fixture-one'}],validate_proposal=False)
        second=a.request_proposal(two,[{'role':'user','content':'fixture-two'}],validate_proposal=False)
        assert first['proposal']=={'echo':'fixture-one'} and second['proposal']=={'echo':'fixture-two'}
        assert state['posts'][1]['messages']==[{'role':'user','content':'fixture-two'}]
        assert second['executed'] is False and second['usage_status']=='MEASURED'

@pytest.mark.parametrize('mode',['malformed','http','tool','overflow','bound'])
def test_malformed_tool_and_oversized_responses_are_rejected(bridge,mode):
    _,root=bridge;task,_=ai_task(root,'strata')
    with server(mode) as (port,state):
        a=adapter(bridge,port)
        with pytest.raises(RuntimeRefused,match='AI_RESPONSE_REJECTED'):
            a.request_proposal(task,[{'role':'user','content':'bounded fixture'}],validate_proposal=False)
        assert len(state['posts'])==1

def test_context_overflow_and_unknown_tokenizer_send_no_request(bridge):
    _,root=bridge;task,_=ai_task(root,'strata')
    with server() as (port,state):
        a=adapter(bridge,port)
        with pytest.raises(RuntimeRefused,match='AI_CONTEXT_BOUND'):
            a.request_proposal(task,[{'role':'user','content':'x'*17000}],validate_proposal=False)
        a.token_counter=None
        with pytest.raises(RuntimeRefused,match='TOKENIZER_UNVERIFIED'):
            a.request_proposal(task,[{'role':'user','content':'x'}],validate_proposal=False)
        assert state['posts']==[]

def test_timeout_blocks_dispatch_until_actual_idle_is_observed(bridge):
    _,root=bridge;task,_=ai_task(root,'strata',deadline=1)
    with server('timeout') as (port,state):
        a=adapter(bridge,port)
        with pytest.raises(RuntimeRefused,match='LOCAL_COMPLETION_UNVERIFIED'):
            a.request_proposal(task,[{'role':'user','content':'x'}],validate_proposal=False)
        assert a.state()=='OWNED_REQUEST_UNCERTAIN'
        with pytest.raises(RuntimeRefused,match='LOCAL_DISPATCH_BLOCKED'):
            a.request_proposal(task,[{'role':'user','content':'x'}],validate_proposal=False)
        with pytest.raises(RuntimeRefused,match='PROVIDER_IDLE_UNVERIFIED'): a.recover_idle()
        time.sleep(.7);assert a.recover_idle()['status']=='IDLE_OBSERVED'
        state['mode']='ok'
        assert a.request_proposal(task,[{'role':'user','content':'after'}],validate_proposal=False)['proposal']=={'echo':'after'}
        assert len(state['posts'])==2

def test_request_budget_denies_additional_attempt_before_http(bridge):
    _,root=bridge;task,_=ai_task(root,'strata')
    with server() as (port,state):
        a=adapter(bridge,port)
        for _ in range(3): a.request_proposal(task,[{'role':'user','content':'x'}],validate_proposal=False)
        with pytest.raises(RuntimeRefused,match='AI_REQUEST_BUDGET'): a.request_proposal(task,[{'role':'user','content':'x'}],validate_proposal=False)
        assert len(state['posts'])==3

@pytest.mark.parametrize('url',['https://example.com','http://localhost:8080','http://127.0.0.1:80','http://user@127.0.0.1:8080','http://127.0.0.1:8080/else'])
def test_only_recorded_loopback_endpoint_is_admitted(bridge,url):
    with pytest.raises(RuntimeRefused): StrataAdapter(bridge[0],StrataProfile(url,'x','a'*64))


def test_fictional_tool_round_trip_is_bound_to_durable_task_receipt(bridge):
    from uuid import uuid4
    from compertum.domain import TaskSpec
    import copy
    _,root=bridge;original,_=ai_task(root,'strata');value=original.to_payload();value['permissions']['tools']=['propose_fixture_tool'];task=TaskSpec(value,project_root=root)
    with server('fictional') as (port,state):
        a=adapter(bridge,port)
        first=a.request_proposal(task,[{'role':'user','content':'fictional lookup'}],validate_proposal=False,approved_fixture_id=str(uuid4()))
        changed=copy.deepcopy(first);changed['fictional_call']['function']['arguments']='{}'
        with pytest.raises(RuntimeRefused,match='AI_CONTEXT_ISOLATION'):
            a.request_proposal(task,[{'role':'user','content':'next'}],validate_proposal=False,fixture_result_for=changed)
        second=a.request_proposal(task,[{'role':'user','content':'next'}],validate_proposal=False,fixture_result_for=first)
        assert second['executed'] is False
        assert state['posts'][-1]['messages'][-1]['content']=='{"fixture_value":7,"synthetic":true}'
        assert (root/first['request_artifact']['path']).is_file()
        assert len(state['posts'])==2


def test_strata_health_boolean_is_metadata_not_a_credential(bridge):
    _,root=bridge;task,_=ai_task(root,'strata')
    with server('strata-health') as (port,state):
        a=adapter(bridge,port)
        assert a.probe_strata()['status']=='IDLE_OBSERVED'
        result=a.request_proposal(task,[{'role':'user','content':'synthetic'}],validate_proposal=False)
        assert result['status']=='PROPOSAL_ONLY' and len(state['posts'])==1


def test_health_never_accepts_a_credential_value(bridge):
    with server('unsafe-health') as (port,state):
        with pytest.raises(RuntimeRefused): adapter(bridge,port).probe_strata()
        assert state['posts']==[]
