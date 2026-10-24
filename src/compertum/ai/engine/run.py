"""One bounded unattended run (section 19). Stage E5. Needs the engine environment for the roles.

The owner starts the run with a cycle limit or an hour limit, an AI request limit under the owner's hard maximum, and an
approval note. The run writes a START row, runs cycles until the first limit, the kill switch, a freeze or a request
refusal stops it, then writes an END row with the reason. The daily summary is rewritten after every cycle.
"""
from datetime import datetime,timezone
import os
import time
from uuid import uuid4
from compertum.runtime.errors import RuntimeRefused
from compertum.ai.manual import sanitized
from compertum.ai.models import ModelClient,StoreLedger
from .audit import check_request_invariant
from .cycle import Engine,run_cycle
from .ledger import EngineLedger
from .limits import NOTE_LIMIT,RunGate,check_limits,load_run_settings,stop_reason,utc_now,write_summary

CYCLE_KEYS=('cycle_id','status','stop_code','hypotheses','candidates','runs','requests_after','total_trials')


def run_bounded(*,store,lease,project_root,sandbox_root,verification,roles,market,memory_floor_bytes,limits,owner_approval,
                available_memory=None,clock=time.monotonic,recursion_limit=40,summary=True):
    """Run cycles until a limit. Returns the run state. Refusals before the START row leave no run record."""
    if not isinstance(owner_approval,str) or not 1<=len(owner_approval)<=NOTE_LIMIT: raise RuntimeRefused('ENGINE_RUN_APPROVAL_DENIED')
    sanitized(owner_approval.encode('utf-8'))  # the note enters the ledger and the summary; no secret may ride along
    settings=load_run_settings(project_root);bounds=check_limits(limits,settings['request_hard_maximum'])
    ledger=EngineLedger(store);ledger.require_unfrozen()
    gate=RunGate(store,ledger,project_root=project_root,hour_limit=bounds['hour_limit'],clock=clock)
    if gate.stop_requested(): raise RuntimeRefused('ENGINE_STOP_FILE_PRESENT')
    if gate.research_state()!='RUNNING': raise RuntimeRefused('RESEARCH_PAUSED')
    if ledger.open_runs(): raise RuntimeRefused('ENGINE_RUN_ACTIVE')
    options={'memory_floor_bytes':memory_floor_bytes,'request_limit':bounds['request_limit'],'native_limits':False,'gate':gate}
    if available_memory is not None: options['available_memory']=available_memory
    client=ModelClient(roles,StoreLedger(store),**options)
    models={role:{'address':spec.base_url,'model':spec.model} for role,spec in roles.items()}
    run_id=f'run-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8]}'
    first=len([c for c in ledger.cycles() if c['phase']=='END'])+1
    started=utc_now()
    # Everything that can refuse is built before the START row, so a refusal leaves no open run.
    engine=Engine(client=client,ledger=ledger,lease=lease,project_root=project_root,sandbox_root=sandbox_root,verification=verification,
                  train_csv=market['train_csv'],validation_csv=market['validation_csv'],validation_rows=market['validation_rows'],
                  memory_floor_bytes=memory_floor_bytes,recursion_limit=recursion_limit,gate=gate,run_id=run_id)
    state={'run_id':run_id,'started_at':started,'limits':bounds,'owner_approval':owner_approval,'models':models,'cycles':[],'requests':0,
           'reason':None,'elapsed_seconds':None,'summary_path':None}
    ledger.record_run_phase(run_id,'START',{'limits':bounds,'owner_approval':owner_approval,'settings_path':settings['path'],'first_cycle_index':first,
                                           'models':models,'pid':os.getpid(),'started_at':started,'stop_file':str(gate.stop_file)})
    index=first
    try:
        while True:
            if bounds['cycle_limit'] is not None and len(state['cycles'])>=bounds['cycle_limit']: state['reason']='CYCLE_LIMIT';break
            try: gate()
            except RuntimeRefused as error: state['reason']=stop_reason(error.code);break
            result=run_cycle(engine,index)
            state['cycles'].append({'cycle_index':index,**{k:result.get(k) for k in CYCLE_KEYS}});index+=1
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
                                 'stop_trigger':gate.trigger,'ended_at':utc_now()})
        if summary: state['summary_path']=str(write_summary(project_root,state,ledger))
    return state
