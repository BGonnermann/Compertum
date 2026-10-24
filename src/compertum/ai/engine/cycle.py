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
from .audit import audit_candidate
from .deflation import deflated_sharpe,trial_variance
from .execution import EngineerSandbox,run_job_tool
from .market import COST,score_signals
from .promotion import promote
from .roles import ROLES,build_role_agent,load_prompt
from .vault import CandidateQueue

MAX_HYPOTHESES=3
REPLY_BYTES=65536
REVIEW_TASK_BYTES=49152
AGENDA_EVERY=10
TRANSCRIPT_BYTES=8192
RETRIES=1  # one bounded retry for a JSON-answer step whose reply did not parse
RETRY_REPLY_BYTES=2048  # how much of the unusable reply the retry task shows the model
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


def clip_bytes(text,limit=TRANSCRIPT_BYTES):
    raw=text.encode('utf-8')
    return text if len(raw)<=limit else raw[:limit].decode('utf-8',errors='ignore')


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
    gate:Any=None  # E5: callable that raises when no step may start (kill switch, hour limit, freeze)
    run_id:Any=None  # E5: the bounded run this cycle belongs to
    prompts:Any=None  # E7: role prompts for this cycle (GEPA candidate); None reads config/engine_prompts


# A step fault is a model reply the harness could not use: a loop, a timeout, an unusable or oversized reply. The cycle records it and goes
# on with the other hypotheses (owner direction, 24 October 2026). Every other refusal (budget, memory floor, kill switch, freeze,
# sandbox, loopback, identity) still stops the cycle, because it is about the run, not about one reply.
STEP_FAULTS=frozenset({'ENGINE_STEP_LIMIT','ENGINE_REPEATED_TOOL_CALL','AI_RESPONSE_INVALID','AI_RESPONSE_BOUND','AI_RESPONSE_INCOMPLETE',
                       'AI_RESPONSE_REJECTED','AI_USAGE_BOUND','LOCAL_COMPLETION_UNVERIFIED','AI_TOOL_EXECUTION_DENIED','AI_MESSAGES_DENIED','AI_TASK_DENIED'})


def market_brief(engine):
    """The fixed description of the market and the scoring rule that every idea task carries. Code, not a prompt: GEPA cannot remove it.
    Practice run 1 (24 October 2026) showed a real model inventing software hypotheses when the task held only the ledger summary."""
    train=max(engine.train_csv.count('\n')-1,0);validation=len(engine.validation_rows)
    return ('MARKET\n'
            f'One asset, daily sessions, synthetic and closed. Two files: train.csv ({train} sessions) and validation.csv ({validation} sessions), '
            'columns session, close, return (return is the fractional change of close from the previous session). '
            'A hypothesis is a rule that sets a position of 0 (flat) or 1 (long) for every validation session from data up to that session. '
            f'Score: the position at session t earns the return of session t+1, minus a cost of {COST} of NAV for each position change. '
            'A strategy beats the baseline when its Sharpe ratio is defined, its annual mean excess over buy-and-hold is positive, and its Sharpe is above buy-and-hold\'s. '
            'Only these two files exist; propose nothing that needs other data.')


def run_cycle(engine,cycle_index):
    if type(cycle_index) is not int or cycle_index<1: raise RuntimeRefused('ENGINE_CYCLE_DENIED')
    if type(engine.max_hypotheses) is not int or not 1<=engine.max_hypotheses<=MAX_HYPOTHESES: raise RuntimeRefused('ENGINE_CYCLE_DENIED')
    ledger=engine.ledger;ledger.require_unfrozen()
    cycle_id=f'cycle-{cycle_index:04d}-{uuid4().hex[:8]}'
    summary=ledger.summary()
    ledger.record_cycle(cycle_id,cycle_index,'START',{'run_id':engine.run_id,'summary':summary,'requests_before':engine.client.requests,'request_limit':engine.client.request_limit})
    state={'cycle_id':cycle_id,'cycle_index':cycle_index,'status':'RUNNING','hypotheses':[],'memos':{},'decisions':{},'specifications':{},'candidates':[],
           'reviews':{},'scores':{},'steps':0,'stop_code':None,'transcript':[],'faults':[]}
    if engine.prompts is None: prompts={role:load_prompt(engine.project_root,role) for role in ROLES}
    else:
        if not isinstance(engine.prompts,dict) or set(engine.prompts)!=set(ROLES) or any(not isinstance(t,str) or not t.startswith(f'ROLE: {r}\n') for r,t in engine.prompts.items()):
            raise RuntimeRefused('ENGINE_PROMPT_INVALID')
        prompts=dict(engine.prompts)
    queue=CandidateQueue(ledger)
    sandbox=EngineerSandbox(engine.sandbox_root,ledger=ledger,lease=engine.lease,verification=engine.verification,cycle_id=cycle_id,
                            train_csv=engine.train_csv,validation_csv=engine.validation_csv,memory_floor_bytes=engine.memory_floor_bytes)
    agents={role:build_role_agent(role,engine.client,system_prompt=prompts[role],tools=[run_job_tool(sandbox)] if role=='engineer' else (),
                                  recursion_limit=engine.recursion_limit) for role in ROLES}

    def step(role,kind,task,record,files=None):
        if engine.gate is not None: engine.gate()  # E5: a paused or stopped run starts no new step
        state['steps']+=1;index=state['steps']
        ledger.record_step(cycle_id,index,role,kind,{'phase':'REQUEST','task_sha256':sha(task),**record})
        try: reply=agents[role].run(task,files)
        except RuntimeRefused as error:
            ledger.record_step(cycle_id,index,role,kind,{'phase':'FAILED','code':error.code,**record});raise
        ledger.record_step(cycle_id,index,role,kind,{'phase':'REPLY','reply_sha256':sha(reply['text']),'reply_bytes':len(reply['text'].encode('utf-8')),
                                                     'messages':reply['messages'],'tool_calls':reply['tool_calls'],'files':sorted(reply['files']),**record})
        # E7: the in-memory transcript lets GEPA reflect on inputs and outputs. It never enters the ledger; the hashes above do.
        state['transcript'].append({'role':role,'kind':kind,'task':clip_bytes(task),'reply':clip_bytes(reply['text'])})
        return reply

    def attempt(role,kind,task,record):
        """A step whose fault is recorded and tolerated. Returns the reply, or None after a fault in STEP_FAULTS (the FAILED step row is already written)."""
        try: return step(role,kind,task,record)
        except RuntimeRefused as error:
            if error.code not in STEP_FAULTS: raise
            state['faults'].append({'role':role,'kind':kind,'code':error.code,**record});return None

    def parsed(role,kind,task,record,parse):
        """A JSON-answer step with one bounded retry. Practice run 3 (24 October 2026): a real model's pick had a one-token glitch
        inside otherwise valid JSON; one retry that shows the parse failure recovers that without any repair of the model's text.
        Returns the parsed value, or None when both replies were unusable (each INVALID row is recorded)."""
        reply=attempt(role,kind,task,record)
        for retry in range(RETRIES+1):
            if reply is None: return None
            try: return parse(reply['text'])
            except RuntimeRefused as error:
                ledger.record_step(cycle_id,state['steps'],role,kind,{'phase':'INVALID','code':error.code,'retry':retry,**record})
                if retry==RETRIES: return None
                previous=clip_bytes(reply['text'],RETRY_REPLY_BYTES)
                reply=attempt(role,kind,f'{task}\n\nYour previous reply was not usable ({error.code}). Reply again with JSON only, no other text, exactly in the format the role prompt gives.'
                                        f'\n\nPREVIOUS REPLY\n{previous}',{**record,'retry':retry+1})

    try:
        # 1. Director picks hypotheses from the ledger summary.
        brief=market_brief(engine)
        picked=parsed('director','pick',f'Pick at most {engine.max_hypotheses} hypotheses for cycle {cycle_index}.\n\n{brief}\n\nLedger summary:\n{json.dumps(summary,sort_keys=True)}',{},parse_hypotheses)
        state['hypotheses']=picked[:engine.max_hypotheses] if picked is not None else []
        # 2. Researcher memos, Director decisions. A faulty memo or verdict rejects that hypothesis and the cycle goes on.
        for hypothesis in state['hypotheses']:
            memo=attempt('researcher','memo',f'Write the memo for this hypothesis.\n\n{brief}\n\nHYPOTHESIS\n{json.dumps(hypothesis,sort_keys=True)}',{'hypothesis_id':hypothesis['id']})
            if memo is None:
                state['decisions'][hypothesis['id']]={'decision':'reject','reason':f'memo step failed ({state["faults"][-1]["code"]})'};continue
            state['memos'][hypothesis['id']]=memo['text']
            decision=parsed('director','approve',f'Approve or reject this memo for hypothesis {hypothesis["id"]}.\n\n{memo["text"]}',{'hypothesis_id':hypothesis['id']},parse_decision)
            if decision is None:
                last=state['faults'][-1]['code'] if state['faults'] and state['faults'][-1].get('hypothesis_id')==hypothesis['id'] and state['faults'][-1]['kind']=='approve' else 'ENGINE_REPLY_INVALID'
                decision={'decision':'reject','reason':f'approval step unusable ({last})'}
            state['decisions'][hypothesis['id']]=decision
        # 3. Mathematician specifications for approved memos. The candidate list is recorded before any run. A faulty specification yields no candidate.
        for hypothesis in state['hypotheses']:
            if state['decisions'][hypothesis['id']]['decision']!='approve': continue
            spec=attempt('mathematician','specify',f'Write the specification for this approved memo.\n\n{brief}\n\nMEMO\n{state["memos"][hypothesis["id"]]}',{'hypothesis_id':hypothesis['id']})
            if spec is None: continue
            state['specifications'][hypothesis['id']]=spec['text']
            state['candidates'].append({'candidate_id':f'{cycle_id}:{hypothesis["id"]}','hypothesis_id':hypothesis['id'],'specification_sha256':sha(spec['text']),'trial':True})
        state['steps']+=1
        ledger.record_step(cycle_id,state['steps'],'archivist','candidates',{'phase':'RECORDED','candidates':state['candidates'],'count':len(state['candidates'])})
        # Every candidate is one trial from this moment, whatever happens to it later (E4).
        for candidate in state['candidates']:
            ledger.record_trial(cycle_id,candidate['candidate_id'],{'hypothesis_id':candidate['hypothesis_id'],'specification_sha256':candidate['specification_sha256']})
        state['total_trials']=ledger.total_trials()
        # 4 and 5. Engineer builds and runs; Mathematician reviews; Validator scores.
        for candidate in state['candidates']:
            hid=candidate['hypothesis_id'];runs_before=len(sandbox.runs)
            build=attempt('engineer','build',f'Build this specification and run it with run_job.\n\n{state["specifications"][hid]}',{'candidate_id':candidate['candidate_id']})
            runs=sandbox.runs[runs_before:];candidate['runs']=[r['run_id'] for r in runs];candidate['run_statuses']=[r['status'] for r in runs]
            if build is None:
                # The Engineer step faulted (loop, timeout, unusable reply). The candidate stays a counted trial with no score; the cycle goes on.
                code=state['faults'][-1]['code'];candidate['status']='BUILD_FAILED';state['scores'][hid]=None
                ledger.record_trial_score(candidate['candidate_id'],{'sharpe_per_period':None,'status':'BUILD_FAILED','code':code})
                state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'validator','score',{'phase':'BUILD_FAILED','code':code,'candidate_id':candidate['candidate_id']});continue
            code={p:c for p,c in build['files'].items() if p.endswith('.py')}
            review_task=f'Review this code against the specification.\n\nSPECIFICATION\n{state["specifications"][hid]}\n\nCODE\n{json.dumps(code,sort_keys=True)}'
            if code and len(review_task.encode('utf-8'))<=REVIEW_TASK_BYTES:
                review=attempt('mathematician','review',review_task,{'candidate_id':candidate['candidate_id']})
                if review is not None: state['reviews'][hid]=review['text']  # the review is advice only; a faulty review is recorded and skipped
            else:
                # The review is advice only. Code too large for one task, or no code, skips the review and records why.
                state['steps']+=1
                ledger.record_step(cycle_id,state['steps'],'mathematician','review',{'phase':'REVIEW_SKIPPED','candidate_id':candidate['candidate_id'],
                                                                                   'reason':'no code' if not code else 'code too large for one review task'})
            signals=next((r.get('signals') for r in reversed(runs) if r['status']=='COMPLETED' and r.get('signals') is not None),None)
            if signals is None:
                candidate['status']='NO_SIGNALS';state['scores'][hid]=None
                ledger.record_trial_score(candidate['candidate_id'],{'sharpe_per_period':None,'status':'NO_SIGNALS'})
                state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'validator','score',{'phase':'NO_SIGNALS','candidate_id':candidate['candidate_id']});continue
            try: score=score_signals(signals,engine.validation_rows)
            except RuntimeRefused as error:
                candidate['status']='INVALID_SIGNALS';state['scores'][hid]=None
                ledger.record_trial_score(candidate['candidate_id'],{'sharpe_per_period':None,'status':'INVALID_SIGNALS','code':error.code})
                state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'validator','score',{'phase':'INVALID','code':error.code,'candidate_id':candidate['candidate_id']});continue
            # Deflation (E4): the bar uses the total trial count across all campaigns and the variance of every scored trial, this one included.
            inputs=score['deflation_inputs'];trials=ledger.total_trials()
            variance=trial_variance(ledger.trial_sharpes()+[inputs['sharpe_per_period']],inputs)
            deflation=deflated_sharpe(inputs,trials,variance['trial_variance'])
            ledger.record_trial_score(candidate['candidate_id'],{'sharpe_per_period':inputs['sharpe_per_period'],'observations':inputs['observations'],'status':'SCORED',
                                                                 'beats_baseline':score['beats_baseline'],'deflation_status':deflation['status']})
            state['scores'][hid]=score
            candidate['status']=('BEATS_BASELINE_PENDING_AUDIT' if deflation['status']=='PASS' else 'REJECTED_DEFLATED') if score['beats_baseline'] else 'REJECTED'
            candidate['deflation']={'trials':trials,'deflated_sharpe':deflation['deflated_sharpe'],'status':deflation['status']}
            state['steps']+=1
            ledger.record_step(cycle_id,state['steps'],'validator','score',{'phase':'SCORED','candidate_id':candidate['candidate_id'],'score':score,'status':candidate['status'],
                                                                           'deflation':deflation,'trial_variance':variance})
            if candidate['status']!='BEATS_BASELINE_PENDING_AUDIT': continue
            # 5b (E6). The Auditor is the binding gate. Integrity failure freezes the engine; a candidate defect rejects the candidate.
            audit=audit_candidate(ledger=ledger,sandbox=sandbox,cycle_id=cycle_id,candidate=candidate,score=score,deflation=deflation,validation_rows=engine.validation_rows)
            state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'auditor','audit',{'phase':audit['label'],'candidate_id':candidate['candidate_id'],'audit':audit})
            candidate['audit']={'label':audit['label'],'integrity':audit['integrity'],'reasons':audit['reasons']}
            if not audit['integrity']:
                ledger.freeze('AUDITOR_FAILED',{'cycle_id':cycle_id,'candidate_id':candidate['candidate_id'],'checks':audit['checks'],'reasons':audit['reasons']})
                candidate['status']='FROZEN';raise RuntimeRefused('ENGINE_FROZEN')
            if audit['label']!='VERIFIED_PASS': candidate['status']='REJECTED_AUDIT';continue
            # Tests and Auditor passed: the code becomes a versioned trusted template, then the candidate enters the queue.
            source=sandbox.record_for(audit['source_run_id'])
            promoted=promote(engine.project_root,candidate['candidate_id'],source['files'],audit=audit,score=score,deflation=deflation,source_job_folder=source['job_folder'])
            queued=queue.admit(candidate['candidate_id'],score,deflation,tests_passed=True,auditor_passed=True)
            candidate['status']='QUEUED';candidate['promoted_folder']=promoted['folder']
            state['steps']+=1
            ledger.record_step(cycle_id,state['steps'],'archivist','promotion',{'phase':'PROMOTED','candidate_id':candidate['candidate_id'],'queue_event_id':queued['event_id'],
                                                                              'folder':promoted['folder'],'files':promoted['manifest']['files']})
        # 7. Agenda review every tenth cycle.
        if cycle_index%AGENDA_EVERY==0:
            agenda=attempt('director','agenda',f'Review the repeated failures and update the agenda.\n\n{brief}\n\nLedger summary:\n{json.dumps(summary,sort_keys=True)}',{})
            if agenda is not None: state['agenda']=agenda['text']
        state['status']='COMPLETED'
    except RuntimeRefused as error:
        state['status']='STOPPED_'+error.code;state['stop_code']=error.code
    except BaseException as error:
        # Any other failure still closes the cycle with an honest status, then propagates.
        state['status']='FAILED_UNEXPECTED';state['stop_code']=type(error).__name__[:64];raise
    finally:
        # 6. The Archivist closes the cycle. Memos, specifications and reviews are kept by hash and size; the texts stay in the step records' hashes.
        end={'run_id':engine.run_id,'status':state['status'],'stop_code':state['stop_code'],'hypotheses':state['hypotheses'],'decisions':state['decisions'],
             'candidates':state['candidates'],'scores':state['scores'],'steps':state['steps'],'runs':len(sandbox.runs),'total_trials':state.get('total_trials'),'faults':state['faults'],
             'requests_after':engine.client.requests,'request_limit':engine.client.request_limit,'agenda_sha256':sha(state['agenda']) if 'agenda' in state else None,
             'texts':{k:{h:{'sha256':sha(t),'bytes':len(t.encode('utf-8'))} for h,t in state[k].items()} for k in ('memos','specifications','reviews')}}
        canonical(end);ledger.record_cycle(cycle_id,cycle_index,'END',end)
    return {'cycle_id':cycle_id,**end,'memos':state['memos'],'specifications':state['specifications'],'reviews':state['reviews'],'transcript':state['transcript']}
