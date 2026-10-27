"""One bounded unattended run (section 19). Stage E5. Needs the engine environment for the roles.

The owner starts the run with a cycle limit or an hour limit, an AI request limit under the owner's hard maximum, and an
approval note. The run writes a START row, runs cycles until the first limit, the kill switch, a freeze or a request
refusal stops it, then writes an END row with the reason. The daily summary is rewritten after every cycle.
"""
from datetime import datetime,timezone
import hashlib
import os
import time
from uuid import uuid4
from compertum.runtime.errors import RuntimeRefused
from compertum.ai.manual import sanitized
from compertum.ai.models import ModelClient,StoreLedger
from .audit import check_request_invariant
from .bench import HOLDOUT_USES,SETS,fingerprint,reserved_fingerprints,set_fingerprints
from .cycle import Engine,run_cycle
from .ledger import EVALUATION_PURPOSES,PURPOSES,EngineLedger
from .limits import NOTE_LIMIT,RunGate,check_limits,load_run_settings,stop_reason,utc_now,write_summary
from .prompts import COMPONENTS,load_component
from .transcripts import TranscriptWriter

CYCLE_KEYS=('cycle_id','status','stop_code','hypotheses','candidates','runs','requests_after','total_trials','faults')


def run_bounded(*,store,lease,project_root,sandbox_root,verification,roles,market=None,memory_floor_bytes,limits,owner_approval,
                available_memory=None,clock=time.monotonic,recursion_limit=40,summary=True,schedule=None,purpose='practice',prompts=None,holdout_set=None):
    """Run cycles until a limit. Returns the run state. Refusals before the START row leave no run record.
    schedule: for a bench or holdout run (bench.py), the market of each cycle in order; the cycle limit must not exceed its length.
    prompts: role prompts to measure (a GEPA candidate); None uses config/engine_prompts."""
    if not isinstance(owner_approval,str) or not 1<=len(owner_approval)<=NOTE_LIMIT: raise RuntimeRefused('ENGINE_RUN_APPROVAL_DENIED')
    sanitized(owner_approval.encode('utf-8'))  # the note enters the ledger and the summary; no secret may ride along
    settings=load_run_settings(project_root);bounds=check_limits(limits,settings['request_hard_maximum'])
    if purpose not in PURPOSES or (purpose in EVALUATION_PURPOSES)!=(schedule is not None): raise RuntimeRefused('ENGINE_RUN_PURPOSE_DENIED')
    if schedule is None: schedule=[market]
    elif not isinstance(schedule,list) or not schedule or bounds['cycle_limit'] is None or bounds['cycle_limit']>len(schedule): raise RuntimeRefused('ENGINE_RUN_LIMITS_DENIED')
    if any(not isinstance(m,dict) or not {'train_csv','validation_csv','validation_rows'}<=m.keys() for m in schedule): raise RuntimeRefused('ENGINE_MARKET_DENIED')
    if (purpose=='holdout')!=(holdout_set is not None) or (holdout_set is not None and (holdout_set not in SETS or not holdout_set.startswith('holdout-'))):
        raise RuntimeRefused('ENGINE_RUN_PURPOSE_DENIED')
    # Each schedule item runs on the engine of its label, so a label must name one market only.
    labels={}
    for item in schedule:
        if purpose!='practice' and not isinstance(item.get('label'),str): raise RuntimeRefused('ENGINE_MARKET_DENIED')
        if labels.setdefault(item.get('label'),item['validation_csv'])!=item['validation_csv']: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    # The markets must belong to the run's purpose (review, 25 October 2026): a holdout market never runs uncounted or in a learning cycle.
    prints={fingerprint(m['train_csv'],m['validation_csv']) for m in schedule}
    if purpose=='practice': allowed=not prints&reserved_fingerprints()
    elif purpose=='holdout': allowed=prints<=set_fingerprints(holdout_set)
    else: allowed=prints<=frozenset().union(*(set_fingerprints(n) for n in SETS if n.startswith('bench-')))
    if not allowed: raise RuntimeRefused('ENGINE_MARKET_RESERVED')
    ledger=EngineLedger(store);ledger.require_unfrozen()
    gate=RunGate(store,ledger,project_root=project_root,hour_limit=bounds['hour_limit'],clock=clock)
    if gate.stop_requested(): raise RuntimeRefused('ENGINE_STOP_FILE_PRESENT')
    if gate.research_state()!='RUNNING': raise RuntimeRefused('RESEARCH_PAUSED')
    if ledger.open_runs(): raise RuntimeRefused('ENGINE_RUN_ACTIVE')
    # The holdout wears out with use. Every use counts from its START row, written before the first holdout cycle, finished or not.
    holdout_use=None
    if purpose=='holdout':
        holdout_use=ledger.holdout_uses(holdout_set)+1
        if holdout_use>HOLDOUT_USES: raise RuntimeRefused('ENGINE_HOLDOUT_RETIRED')
    options={'memory_floor_bytes':memory_floor_bytes,'request_limit':bounds['request_limit'],'native_limits':False,'gate':gate}
    if available_memory is not None: options['available_memory']=available_memory
    run_id=f'run-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8]}'
    transcript=TranscriptWriter(project_root,run_id,purpose)  # step S3: the words of every request; bench and holdout lines are marked not for training
    client=ModelClient(roles,StoreLedger(store),transcript=transcript,**options)
    models={role:{'address':spec.base_url,'model':spec.model} for role,spec in roles.items()}
    first=len([c for c in ledger.cycles() if c['phase']=='END'])+1
    started=utc_now()
    # Everything that can refuse is built before the START row, so a refusal leaves no open run.
    engines={}
    for item in schedule:
        if item.get('label') in engines: continue
        engines[item.get('label')]=Engine(client=client,ledger=ledger,lease=lease,project_root=project_root,sandbox_root=sandbox_root,verification=verification,
                                          train_csv=item['train_csv'],validation_csv=item['validation_csv'],validation_rows=item['validation_rows'],
                                          memory_floor_bytes=memory_floor_bytes,recursion_limit=recursion_limit,gate=gate,run_id=run_id,prompts=prompts,purpose=purpose)
    state={'run_id':run_id,'purpose':purpose,'started_at':started,'limits':bounds,'owner_approval':owner_approval,'models':models,'cycles':[],'requests':0,
           'reason':None,'elapsed_seconds':None,'summary_path':None}
    start={'limits':bounds,'owner_approval':owner_approval,'settings_path':settings['path'],'first_cycle_index':first,
           'models':models,'pid':os.getpid(),'started_at':started,'stop_file':str(gate.stop_file)}
    if purpose!='practice':
        # The committed prompts are hashed too (26 October 2026), so every evaluation run records the exact prompts it measured.
        measured=prompts if prompts is not None else {name:load_component(project_root,name) for name in COMPONENTS}
        start.update(purpose=purpose,markets=[m.get('label') for m in schedule],prompts_source='committed' if prompts is None else 'given',
                     prompts_sha256={role:hashlib.sha256(text.encode('utf-8')).hexdigest() for role,text in sorted(measured.items())})
    if holdout_set is not None: start.update(holdout_set=holdout_set,holdout_use=holdout_use,holdout_uses_allowed=HOLDOUT_USES)
    ledger.record_run_phase(run_id,'START',start)
    index=first
    try:
        while True:
            if bounds['cycle_limit'] is not None and len(state['cycles'])>=bounds['cycle_limit']: state['reason']='CYCLE_LIMIT';break
            try: gate()
            except RuntimeRefused as error: state['reason']=stop_reason(error.code);break
            item=schedule[len(state['cycles'])%len(schedule)]
            result=run_cycle(engines[item.get('label')],index)
            entry={'cycle_index':index,**{k:result.get(k) for k in CYCLE_KEYS}}
            if purpose!='practice': entry.update(market=item.get('label'),scores=result.get('scores'))  # the bench report needs the scores
            state['cycles'].append(entry);index+=1
            state['requests']=client.requests
            if summary: state['summary_path']=str(write_summary(project_root,state,ledger))
            if result.get('stop_code') is not None: state['reason']=stop_reason(result['stop_code']);break
    except BaseException as error:
        state['reason']='FAILED_UNEXPECTED';state['failure']=type(error).__name__[:64];raise
    finally:
        state['requests']=client.requests;state['elapsed_seconds']=round(gate.elapsed_seconds(),3)
        # E6 invariant: a count above the approved limit means the limiter failed. The engine freezes; the END row still follows.
        state['request_invariant']=check_request_invariant(ledger,run_id,client.requests,bounds['request_limit'])
        ledger.close_run(run_id,{'reason':state['reason'],'failure':state.get('failure'),'cycles':len(state['cycles']),'requests':state['requests'],
                                 'request_invariant':state['request_invariant'],'elapsed_seconds':state['elapsed_seconds'],'gate_checks':gate.checks,
                                 'stop_trigger':gate.trigger,'transcript':{**transcript.report(),'client_failures':client.transcript_failures},'ended_at':utc_now()})
        if summary: state['summary_path']=str(write_summary(project_root,state,ledger))
    return state
