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
from .ledger import EVALUATION_PURPOSES,HISTORY_FREE_PURPOSES,PURPOSES
from .limits import STEP_FAULTS
from .market import score_signals
from .promotion import promote
from .prompts import COMPONENTS,check_component,load_component,parse_routing,parse_settings
from .roles import ROLES,build_role_agent,load_prompt
from .tasks import (RETRY_REPLY_BYTES,SAMPLE_ROWS,STARTER_MAIN,TRANSCRIPT_BYTES,agenda_task,approve_task,clip_bytes,engineer_task,  # noqa: F401 (kept importable from cycle)
                    market_brief,memo_task,pick_task,retry_task,review_task,specify_task)
from .vault import CandidateQueue

MAX_HYPOTHESES=3
REPLY_BYTES=65536
REVIEW_TASK_BYTES=49152
AGENDA_EVERY=10
RETRIES=1  # the default: one bounded retry for a JSON-answer step whose reply did not parse (the settings slot may choose 0 to 2)
SLOTS=tuple(name for name in COMPONENTS if name not in ('director','researcher','mathematician','engineer'))
TOOL_ROUTES=('director_sees_tool','researcher_sees_tool','specify_sees_tool')
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
    gate:Any=None  # E5: callable that raises when no step may start (kill switch, hour limit, freeze)
    run_id:Any=None  # E5: the bounded run this cycle belongs to
    prompts:Any=None  # E7: role prompts for this cycle (GEPA candidate), and optionally its 'routing' text; None reads config/engine_prompts
    purpose:str='practice'  # 'gepa', 'bench' or 'holdout': no history in, no lessons out, no agenda step; bench and holdout also never promote


def market_sha256(engine):
    """One fingerprint of the two files a cycle sees. Never a vault file: the engine has none."""
    return sha(canonical({'train_csv':engine.train_csv,'validation_csv':engine.validation_csv}).decode())


def run_cycle(engine,cycle_index):
    if type(cycle_index) is not int or cycle_index<1: raise RuntimeRefused('ENGINE_CYCLE_DENIED')
    if type(engine.max_hypotheses) is not int or not 1<=engine.max_hypotheses<=MAX_HYPOTHESES: raise RuntimeRefused('ENGINE_CYCLE_DENIED')
    if engine.purpose not in PURPOSES: raise RuntimeRefused('ENGINE_CYCLE_DENIED')
    ledger=engine.ledger;ledger.require_unfrozen()
    cycle_id=f'cycle-{cycle_index:04d}-{uuid4().hex[:8]}'
    # The market fingerprint scopes the Director's lessons table to cycles on the same TRAIN and VALIDATION files (owner request, 25 October 2026).
    market=market_sha256(engine)
    # A bench or holdout cycle starts with no history (bench.py), so every evaluation cycle sees the same task whatever ran before it.
    summary=ledger.summary(market) if engine.purpose not in HISTORY_FREE_PURPOSES else ledger.blank_summary()
    ledger.record_cycle(cycle_id,cycle_index,'START',{'run_id':engine.run_id,'purpose':engine.purpose,'market_sha256':market,'summary':summary,'requests_before':engine.client.requests,'request_limit':engine.client.request_limit})
    state={'cycle_id':cycle_id,'cycle_index':cycle_index,'status':'RUNNING','hypotheses':[],'memos':{},'decisions':{},'specifications':{},'candidates':[],
           'reviews':{},'scores':{},'steps':0,'stop_code':None,'transcript':[],'faults':[],'tool':None}
    if engine.prompts is None: prompts={role:load_prompt(engine.project_root,role) for role in ROLES}
    else:
        if (not isinstance(engine.prompts,dict) or set(engine.prompts)-set(SLOTS)!=set(ROLES)
                or any(not isinstance(engine.prompts[r],str) or not engine.prompts[r].startswith(f'ROLE: {r}\n') for r in ROLES)):
            raise RuntimeRefused('ENGINE_PROMPT_INVALID')
        prompts={role:engine.prompts[role] for role in ROLES}
    # The firm's slots (26 October 2026): a GEPA candidate may carry its own routing, settings, tool and starter; otherwise the committed
    # files are used, or the defaults without them (the cycle as it was before the slots existed).
    given=engine.prompts if isinstance(engine.prompts,dict) else {}
    def slot(name): return check_component(name,given[name]) if name in given else load_component(engine.project_root,name)
    routing=parse_routing(slot('routing'));settings=parse_settings(slot('settings'));tool_code=slot('tool');starter=slot('starter')
    def routed(key,value): return value if routing[key]=='yes' else None
    max_hypotheses=min(engine.max_hypotheses,int(settings['hypotheses']));retries=int(settings['retries'])
    queue=CandidateQueue(ledger)
    sandbox=EngineerSandbox(engine.sandbox_root,ledger=ledger,lease=engine.lease,verification=engine.verification,cycle_id=cycle_id,
                            train_csv=engine.train_csv,validation_csv=engine.validation_csv,memory_floor_bytes=engine.memory_floor_bytes,
                            max_runs=int(settings['engineer_runs']))
    def cap(role): return None if settings[f'{role}_max_tokens']=='model' else int(settings[f'{role}_max_tokens'])
    agents={role:build_role_agent(role,engine.client,system_prompt=prompts[role],tools=[run_job_tool(sandbox)] if role=='engineer' else (),
                                  recursion_limit=engine.recursion_limit,max_tokens=cap(role),temperature=float(settings[f'{role}_temperature'])) for role in ROLES}

    def run_tool():
        """The analysis tool slot: one sandbox job on train.csv only. Its run is filed under '<cycle id>-tool', apart from the candidates' runs,
        so the Auditor's checks of a candidate see only that candidate's runs. A denied access or a loopback connection still freezes the engine."""
        if engine.gate is not None: engine.gate()
        toolbox=EngineerSandbox(engine.sandbox_root,ledger=ledger,lease=engine.lease,verification=engine.verification,cycle_id=f'{cycle_id}-tool',
                                train_csv=engine.train_csv,validation_csv=engine.validation_csv,memory_floor_bytes=engine.memory_floor_bytes)
        record=toolbox.run_tool(tool_code)
        output=record['stdout'] if record['status']=='COMPLETED' and record['stdout'].strip() else None
        state['tool']={'run_id':record['run_id'],'status':record['status'],'output_bytes':len(output.encode('utf-8')) if output else 0}
        state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'tool','run',{'phase':record['status'],'run_id':record['run_id']})
        # GEPA reads what the tool printed, or why it failed, when it rewrites the tool.
        state['transcript'].append({'role':'tool','kind':'run','task':'tool.py on train.csv','reply':clip_bytes(output if output else f"status {record['status']}; stderr {record['stderr']}")})
        return output

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

    def attempt(role,kind,task,record,files=None):
        """A step whose fault is recorded and tolerated. Returns the reply, or None after a fault in STEP_FAULTS (the FAILED step row is already written)."""
        try: return step(role,kind,task,record,files)
        except RuntimeRefused as error:
            if error.code not in STEP_FAULTS: raise
            state['faults'].append({'role':role,'kind':kind,'code':error.code,**record});return None

    def parsed(role,kind,task,record,parse):
        """A JSON-answer step with one bounded retry. Practice run 3 (24 October 2026): a real model's pick had a one-token glitch
        inside otherwise valid JSON; one retry that shows the parse failure recovers that without any repair of the model's text.
        Returns the parsed value, or None when both replies were unusable (each INVALID row is recorded)."""
        reply=attempt(role,kind,task,record)
        for retry in range(retries+1):
            if reply is None: return None
            try: return parse(reply['text'])
            except RuntimeRefused as error:
                ledger.record_step(cycle_id,state['steps'],role,kind,{'phase':'INVALID','code':error.code,'retry':retry,**record})
                if retry==retries: return None
                reply=attempt(role,kind,retry_task(task,error.code,reply['text']),{**record,'retry':retry+1})

    try:
        # 1. Director picks hypotheses from the ledger summary and its lessons table.
        brief=market_brief(engine)
        # 0. The analysis tool runs first when the routing sends its output to any role.
        tool_output=run_tool() if any(routing[key]=='yes' for key in TOOL_ROUTES) else None
        picked=parsed('director','pick',pick_task(max_hypotheses,cycle_index,brief,summary,routed('director_sees_tool',tool_output)),{},parse_hypotheses)
        state['hypotheses']=picked[:max_hypotheses] if picked is not None else []
        # 2. Researcher memos, Director decisions. A faulty memo or verdict rejects that hypothesis and the cycle goes on.
        for hypothesis in state['hypotheses']:
            memo=attempt('researcher','memo',memo_task(brief,hypothesis,routed('researcher_sees_lessons',summary),routed('researcher_sees_tool',tool_output)),{'hypothesis_id':hypothesis['id']})
            if memo is None:
                state['decisions'][hypothesis['id']]={'decision':'reject','reason':f'memo step failed ({state["faults"][-1]["code"]})','source':'code'};continue
            state['memos'][hypothesis['id']]=memo['text']
            decision=parsed('director','approve',approve_task(hypothesis['id'],memo['text']),{'hypothesis_id':hypothesis['id']},parse_decision)
            if decision is None:
                last=state['faults'][-1]['code'] if state['faults'] and state['faults'][-1].get('hypothesis_id')==hypothesis['id'] and state['faults'][-1]['kind']=='approve' else 'ENGINE_REPLY_INVALID'
                decision={'decision':'reject','reason':f'approval step unusable ({last})','source':'code'}  # a fault, not the Director's verdict (levels.lessons)
            state['decisions'][hypothesis['id']]=decision
        # 3. Mathematician specifications for approved memos. The candidate list is recorded before any run. A faulty specification yields no candidate.
        for hypothesis in state['hypotheses']:
            if state['decisions'][hypothesis['id']]['decision']!='approve': continue
            spec=attempt('mathematician','specify',specify_task(brief,state['memos'][hypothesis['id']],routed('specify_sees_hypothesis',hypothesis),routed('specify_sees_tool',tool_output)),{'hypothesis_id':hypothesis['id']})
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
            sandbox.begin_candidate()  # each candidate has its own Engineer runs
            # The Engineer starts from a starter program and the specification in its file store, and sees a TRAIN sample in the task (practice runs 5 to 10).
            memo=routed('engineer_sees_memo',state['memos'][hid])
            task,start_files=engineer_task(engine,state['specifications'][hid],memo=memo,starter=starter)
            build=attempt('engineer','build',task,{'candidate_id':candidate['candidate_id']},files=start_files)
            runs=sandbox.runs[runs_before:]
            if build is not None and not runs:
                # GEPA run 1 (24 October 2026): three times the model read the starter and replied DONE without ever calling run_job.
                # One bounded retry, a fresh conversation that names the omission; the starter is offered again.
                ledger.record_step(cycle_id,state['steps'],'engineer','build',{'phase':'INVALID','code':'ENGINE_NO_RUN','retry':0,'candidate_id':candidate['candidate_id']})
                task,start_files=engineer_task(engine,state['specifications'][hid],previous_reply=build['text'],memo=memo,starter=starter)
                build=attempt('engineer','build',task,{'candidate_id':candidate['candidate_id'],'retry':1},files=start_files)
                runs=sandbox.runs[runs_before:]
            candidate['runs']=[r['run_id'] for r in runs];candidate['run_statuses']=[r['status'] for r in runs]
            signals=next((r.get('signals') for r in reversed(runs) if r['status']=='COMPLETED' and r.get('signals') is not None),None)
            if build is None and signals is None:
                # The Engineer step faulted (loop, timeout, unusable reply) with no completed run. The candidate stays a counted trial with no score.
                code=state['faults'][-1]['code'];candidate['status']='BUILD_FAILED';state['scores'][hid]=None
                ledger.record_trial_score(candidate['candidate_id'],{'sharpe_per_period':None,'status':'BUILD_FAILED','code':code})
                state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'validator','score',{'phase':'BUILD_FAILED','code':code,'candidate_id':candidate['candidate_id']});continue
            # A build fault after a completed run (practice run 5: the model hunted for signals.csv after writing it) keeps the signals: they are scored.
            code={p:c for p,c in build['files'].items() if p.endswith('.py')} if build is not None else {}
            review_text=review_task(state['specifications'][hid],code)
            if routing['review']!='off' and code and len(review_text.encode('utf-8'))<=REVIEW_TASK_BYTES:
                review=attempt('mathematician','review',review_text,{'candidate_id':candidate['candidate_id']})
                if review is not None: state['reviews'][hid]=review['text']  # with review 'advice' the review is recorded only; a faulty review is recorded and skipped
            else:
                # Routing review 'off', code too large for one task, no code, or a build fault after a completed run skips the review and records why.
                state['steps']+=1
                reason=('routing: review off' if routing['review']=='off' else 'build step faulted after a completed run; the signals are scored' if build is None
                        else 'no code' if not code else 'code too large for one review task')
                ledger.record_step(cycle_id,state['steps'],'mathematician','review',{'phase':'REVIEW_SKIPPED','candidate_id':candidate['candidate_id'],'reason':reason})
            if routing['review']=='rebuild' and hid in state['reviews']:
                # Routing review 'rebuild': one more Engineer build from its own code and the review. The review never sees a score, so the rebuild
                # cannot select on VALIDATION results. The last completed run is scored and audited, as for any build.
                task,start_files=engineer_task(engine,state['specifications'][hid],memo=memo,review=state['reviews'][hid],code=code,starter=starter)
                attempt('engineer','rebuild',task,{'candidate_id':candidate['candidate_id']},files=start_files)
                runs=sandbox.runs[runs_before:]
                candidate['runs']=[r['run_id'] for r in runs];candidate['run_statuses']=[r['status'] for r in runs]
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
            if not score['beats_baseline']: continue
            # 5b (E6). The Auditor is the binding gate. Integrity failure freezes the engine; a candidate defect rejects the candidate.
            # Since 25 October 2026 (owner decision) it checks every candidate that beat buy-and-hold, at the gate or below it, so a strategy
            # that read future data is caught at any deflated Sharpe. Only a candidate at the gate can be promoted and queued.
            audit=audit_candidate(ledger=ledger,sandbox=sandbox,cycle_id=cycle_id,candidate=candidate,score=score,deflation=deflation,validation_rows=engine.validation_rows)
            state['steps']+=1;ledger.record_step(cycle_id,state['steps'],'auditor','audit',{'phase':audit['label'],'candidate_id':candidate['candidate_id'],'audit':audit})
            candidate['audit']={'label':audit['label'],'integrity':audit['integrity'],'reasons':audit['reasons']}
            if not audit['integrity']:
                ledger.freeze('AUDITOR_FAILED',{'cycle_id':cycle_id,'candidate_id':candidate['candidate_id'],'checks':audit['checks'],'reasons':audit['reasons']})
                candidate['status']='FROZEN';raise RuntimeRefused('ENGINE_FROZEN')
            if audit['label']!='VERIFIED_PASS': candidate['status']='REJECTED_AUDIT';continue
            if deflation['status']!='PASS': continue  # audited and honest, below the gate: stays REJECTED_DEFLATED with its audit record; never promoted
            if engine.purpose in EVALUATION_PURPOSES:
                # A bench or holdout check measures prompts; its strategies never become templates or enter the vault queue (review, 25 October 2026).
                candidate['status']='EVALUATION_GATE_PASS';continue
            # Tests and Auditor passed: the code becomes a versioned trusted template, then the candidate enters the queue.
            source=sandbox.record_for(audit['source_run_id'])
            promoted=promote(engine.project_root,candidate['candidate_id'],source['files'],audit=audit,score=score,deflation=deflation,source_job_folder=source['job_folder'])
            queued=queue.admit(candidate['candidate_id'],score,deflation,tests_passed=True,auditor_passed=True)
            candidate['status']='QUEUED';candidate['promoted_folder']=promoted['folder']
            state['steps']+=1
            ledger.record_step(cycle_id,state['steps'],'archivist','promotion',{'phase':'PROMOTED','candidate_id':candidate['candidate_id'],'queue_event_id':queued['event_id'],
                                                                              'folder':promoted['folder'],'files':promoted['manifest']['files']})
        # 7. Agenda review every tenth cycle.
        if cycle_index%AGENDA_EVERY==0 and engine.purpose not in HISTORY_FREE_PURPOSES:
            agenda=attempt('director','agenda',agenda_task(brief,summary),{})
            if agenda is not None: state['agenda']=agenda['text']
        state['status']='COMPLETED'
    except RuntimeRefused as error:
        state['status']='STOPPED_'+error.code;state['stop_code']=error.code
    except BaseException as error:
        # Any other failure still closes the cycle with an honest status, then propagates.
        state['status']='FAILED_UNEXPECTED';state['stop_code']=type(error).__name__[:64];raise
    finally:
        # 6. The Archivist closes the cycle. Memos, specifications and reviews are kept by hash and size; the texts stay in the step records' hashes.
        end={'run_id':engine.run_id,'purpose':engine.purpose,'market_sha256':market,'status':state['status'],'stop_code':state['stop_code'],'hypotheses':state['hypotheses'],'decisions':state['decisions'],
             'candidates':state['candidates'],'scores':state['scores'],'steps':state['steps'],'runs':len(sandbox.runs),'total_trials':state.get('total_trials'),'faults':state['faults'],
             'requests_after':engine.client.requests,'request_limit':engine.client.request_limit,'agenda_sha256':sha(state['agenda']) if 'agenda' in state else None,
             'texts':{k:{h:{'sha256':sha(t),'bytes':len(t.encode('utf-8'))} for h,t in state[k].items()} for k in ('memos','specifications','reviews')},'routing':routing,'settings':settings,'tool':state['tool']}
        canonical(end);ledger.record_cycle(cycle_id,cycle_index,'END',end)
    return {'cycle_id':cycle_id,**end,'memos':state['memos'],'specifications':state['specifications'],'reviews':state['reviews'],'transcript':state['transcript']}
