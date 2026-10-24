"""One section 19 cycle in trusted code. The roles think; this module decides the order, records everything and never trusts a reply.

Steps: 1 Director picks at most 3 hypotheses. 2 Researcher writes one memo each; the Director approves or rejects each memo.
3 Mathematician writes one specification per approved memo. The candidate list is recorded before any run.
4 Engineer builds each specification with run_job; the Mathematician reviews the code (advice only).
5 Validator scores each candidate on the synthetic market. 6 Archivist rows exist for every step as it happens.
7 Every tenth cycle the Director reviews repeated failures and updates the agenda.
A refusal from the model path (request limit, memory floor, frozen engine) stops the cycle and is recorded with its code.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
from uuid import uuid4
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from .execution import EngineerSandbox,run_job_tool
from .market import score_signals
from .roles import ROLES,build_role_agent,load_prompt

MAX_HYPOTHESES=3
REPLY_BYTES=65536
REVIEW_TASK_BYTES=49152
AGENDA_EVERY=10
_FENCE=re.compile(r'```(?:json)?\s*(.*?)```',re.S)


def parse_json_reply(text):
    """A JSON object from a role reply, with or without a code fence. Anything else is ENGINE_REPLY_INVALID."""
    if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=REPLY_BYTES: raise RuntimeRefused('ENGINE_REPLY_INVALID')
    match=_FENCE.search(text);body=match.group(1) if match else text
    body=body.strip()
    if not body.startswith('{'):
        start=body.find('{');end=body.rfind('}')
        if start<0 or end<start: raise RuntimeRefused('ENGINE_REPLY_INVALID')
        body=body[start:end+1]
    try: value=json.loads(body)
    except ValueError: raise RuntimeRefused('ENGINE_REPLY_INVALID') from None
    if not isinstance(value,dict): raise RuntimeRefused('ENGINE_REPLY_INVALID')
    return value


def parse_hypotheses(reply):
    items=parse_json_reply(reply).get('hypotheses')
    if not isinstance(items,list) or not 1<=len(items)<=MAX_HYPOTHESES: raise RuntimeRefused('ENGINE_REPLY_INVALID')
    out=[];seen=set()
    for item in items:
        if (not isinstance(item,dict) or item.keys()!={'id','title','idea'} or any(not isinstance(item[k],str) or not 1<=len(item[k])<=4096 for k in item)
                or item['id'] in seen or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',item['id'])):
            raise RuntimeRefused('ENGINE_REPLY_INVALID')
        seen.add(item['id']);out.append({'id':item['id'],'title':item['title'],'idea':item['idea']})
    return out


def parse_decision(reply):
    value=parse_json_reply(reply)
    if value.get('decision') not in ('approve','reject') or not isinstance(value.get('reason'),str) or not 1<=len(value['reason'])<=4096: raise RuntimeRefused('ENGINE_REPLY_INVALID')
    return {'decision':value['decision'],'reason':value['reason']}


def sha(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()


@dataclass
class Engine:
    """Everything one cycle needs. Agents are rebuilt for each cycle so that every role starts a fresh conversation."""
    client:Any
    ledger:Any
    lease:Any
    project_root:Any
    sandbox_root:Any
    verification:dict
    train_csv:str
    validation_csv:str
    validation_rows:list
    memory_floor_bytes:int
    recursion_limit:int=40
    max_hypotheses:int=MAX_HYPOTHESES


def run_cycle(engine,cycle_index):
    if type(cycle_index) is not int or cycle_index<1: raise RuntimeRefused('ENGINE_CYCLE_DENIED')
    if type(engine.max_hypotheses) is not int or not 1<=engine.max_hypotheses<=MAX_HYPOTHESES: raise RuntimeRefused('ENGINE_CYCLE_DENIED')
    ledger=engine.ledger;ledger.require_unfrozen()
    cycle_id=f'cycle-{cycle_index:04d}-{uuid4().hex[:8]}'
    summary=ledger.summary()
    ledger.record_cycle(cycle_id,cycle_index,'START',{'summary':summary,'requests_before':engine.client.requests,'request_limit':engine.client.request_limit})
    state={'cycle_id':cycle_id,'cycle_index':cycle_index,'status':'RUNNING','hypotheses':[],'memos':{},'decisions':{},'specifications':{},'candidates':[],
           'reviews':{},'scores':{},'steps':0,'stop_code':None}
    prompts={role:load_prompt(engine.project_root,role) for role in ROLES}
    sandbox=EngineerSandbox(engine.sandbox_root,ledger=ledger,lease=engine.lease,verification=engine.verification,cycle_id=cycle_id,
                            train_csv=engine.train_csv,validation_csv=engine.validation_csv,memory_floor_bytes=engine.memory_floor_bytes)
    agents={role:build_role_agent(role,engine.client,system_prompt=prompts[role],tools=[run_job_tool(sandbox)] if role=='engineer' else (),
                                  recursion_limit=engine.recursion_limit) for role in ROLES}

    def step(role,kind,task,record,files=None):
        state['steps']+=1;index=state['steps']
        ledger.record_step(cycle_id,index,role,kind,{'phase':'REQUEST','task_sha256':sha(task),**record})
        try: reply=agents[role].run(task,files)
        except RuntimeRefused as error:
            ledger.record_step(cycle_id,index,role,kind,{'phase':'FAILED','code':error.code,**record});raise
        ledger.record_step(cycle_id,index,role,kind,{'phase':'REPLY','reply_sha256':sha(reply['text']),'reply_bytes':len(reply['text'].encode('utf-8')),
                                                     'messages':reply['messages'],'tool_calls':reply['tool_calls'],'files':sorted(reply['files']),**record})
        return reply

    try:
        # 1. Director picks hypotheses from the ledger summary.
        pick=step('director','pick',f'Pick at most {engine.max_hypotheses} hypotheses for cycle {cycle_index}. Ledger summary:\n{json.dumps(summary,sort_keys=True)}',{})
        try: state['hypotheses']=parse_hypotheses(pick['text'])[:engine.max_hypotheses]
        except RuntimeRefused as error:
            ledger.record_step(cycle_id,state['steps'],'director','pick',{'phase':'INVALID','code':error.code});state['hypotheses']=[]
        # 2. Researcher memos, Director decisions.
        for hypothesis in state['hypotheses']:
            memo=step('researcher','memo',f'Write the memo for this hypothesis.\n{json.dumps(hypothesis,sort_keys=True)}',{'hypothesis_id':hypothesis['id']})
            state['memos'][hypothesis['id']]=memo['text']
            verdict=step('director','approve',f'Approve or reject this memo for hypothesis {hypothesis["id"]}.\n\n{memo["text"]}',{'hypothesis_id':hypothesis['id']})
            try: decision=parse_decision(verdict['text'])
            except RuntimeRefused as error:
                decision={'decision':'reject','reason':f'invalid reply ({error.code})'}
                ledger.record_step(cycle_id,state['steps'],'director','approve',{'phase':'INVALID','code':error.code,'hypothesis_id':hypothesis['id']})
            state['decisions'][hypothesis['id']]=decision
        # 3. Mathematician specifications for approved memos. The candidate list is recorded before any run.
        for hypothesis in state['hypotheses']:
            if state['decisions'][hypothesis['id']]['decision']!='approve': continue
            spec=step('mathematician','specify',f'Write the specification for this approved memo.\n\n{state["memos"][hypothesis["id"]]}',{'hypothesis_id':hypothesis['id']})
            state['specifications'][hypothesis['id']]=spec['text']
            state['candidates'].append({'candidate_id':f'{cycle_id}:{hypothesis["id"]}','hypothesis_id':hypothesis['id'],'specification_sha256':sha(spec['text']),'trial':True})
        state['steps']+=1
        ledger.record_step(cycle_id,state['steps'],'archivist','candidates',{'phase':'RECORDED','candidates':state['candidates'],'count':len(state['candidates'])})
        # 4 and 5. Engineer builds and runs; Mathematician reviews; Validator scores.
        for candidate in state['candidates']:
            hid=candidate['hypothesis_id'];runs_before=len(sandbox.runs)
            build=step('engineer','build',f'Build this specification and run it with run_job.\n\n{state["specifications"][hid]}',{'candidate_id':candidate['candidate_id']})
            runs=sandbox.runs[runs_before:];candidate['runs']=[r['run_id'] for r in runs];candidate['run_statuses']=[r['status'] for r in runs]
            code={p:c for p,c in build['files'].items() if p.endswith('.py')}
            review_task=f'Review this code against the specification.\n\nSPECIFICATION\n{state["specifications"][hid]}\n\nCODE\n{json.dumps(code,sort_keys=True)}'
            if code and len(review_task.encode('utf-8'))<=REVIEW_TASK_BYTES:
                review=step('mathematician','review',review_task,{'candidate_id':candidate['candidate_id']})
                state['reviews'][hid]=review['text']
            else:
                # The review is advice only. Code too large for one task, or no code, skips the review and records why.
                state['steps']+=1
                ledger.record_step(cycle_id,state['steps'],'mathematician','review',{'phase':'REVIEW_SKIPPED','candidate_id':candidate['candidate_id'],
                                                                                   'reason':'no code' if not code else 'code too large for one review task'})
            signals=next((r.get('signals') for r in reversed(runs) if r['status']=='COMPLETED' and r.get('signals') is not None),None)
            if signals is None:
                candidate['status']='NO_SIGNALS';state['scores'][hid]=None
                state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'validator','score',{'phase':'NO_SIGNALS','candidate_id':candidate['candidate_id']});continue
            try: score=score_signals(signals,engine.validation_rows)
            except RuntimeRefused as error:
                candidate['status']='INVALID_SIGNALS';state['scores'][hid]=None
                state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'validator','score',{'phase':'INVALID','code':error.code,'candidate_id':candidate['candidate_id']});continue
            state['scores'][hid]=score;candidate['status']='BEATS_BASELINE_PENDING_AUDIT' if score['beats_baseline'] else 'REJECTED'
            state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'validator','score',{'phase':'SCORED','candidate_id':candidate['candidate_id'],'score':score,'status':candidate['status']})
        # 7. Agenda review every tenth cycle.
        if cycle_index%AGENDA_EVERY==0:
            agenda=step('director','agenda',f'Review the repeated failures and update the agenda. Ledger summary:\n{json.dumps(summary,sort_keys=True)}',{})
            state['agenda']=agenda['text']
        state['status']='COMPLETED'
    except RuntimeRefused as error:
        state['status']='STOPPED_'+error.code;state['stop_code']=error.code
    except BaseException as error:
        # Any other failure still closes the cycle with an honest status, then propagates.
        state['status']='FAILED_UNEXPECTED';state['stop_code']=type(error).__name__[:64];raise
    finally:
        # 6. The Archivist closes the cycle. Memos, specifications and reviews are kept by hash and size; the texts stay in the step records' hashes.
        end={'status':state['status'],'stop_code':state['stop_code'],'hypotheses':state['hypotheses'],'decisions':state['decisions'],
             'candidates':state['candidates'],'scores':state['scores'],'steps':state['steps'],'runs':len(sandbox.runs),
             'requests_after':engine.client.requests,'request_limit':engine.client.request_limit,'agenda_sha256':sha(state['agenda']) if 'agenda' in state else None,
             'texts':{k:{h:{'sha256':sha(t),'bytes':len(t.encode('utf-8'))} for h,t in state[k].items()} for k in ('memos','specifications','reviews')}}
        canonical(end);ledger.record_cycle(cycle_id,cycle_index,'END',end)
    return {'cycle_id':cycle_id,**end,'memos':state['memos'],'specifications':state['specifications'],'reviews':state['reviews']}
