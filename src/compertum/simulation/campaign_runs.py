"""Campaign-specific transitions using the existing guarded saved-run owner."""
from dataclasses import asdict
import hashlib,json,re
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.campaign_contract import UNITS,DETERMINISTIC
from .campaign_record import pack_result,verify_result
from compertum.runtime.startup_record import expected_proof,outcome_proof
from compertum.runtime.campaign_environment import validate_expected,check_native,outcome_environment

MIB=1024**2
RECEIPT_FIELDS={'pid','exit_code','timed_out','active_processes','assigned_before_resume','affinity','memory_limit','peak_job_memory','observed_child_pids','observed_children_exited'}


def is_campaign(state):return state.get('input_kind')=='synthetic-campaign'


def validate_receipt(receipt):
    if not isinstance(receipt,dict) or not RECEIPT_FIELDS<=set(receipt)<=RECEIPT_FIELDS|{'execution_identity'} or len(canonical(receipt))>2048:raise DataError('CAMPAIGN_RECEIPT_INVALID')
    for key in ('pid','exit_code','active_processes','affinity','memory_limit','peak_job_memory'):
        if type(receipt[key]) is not int or not 0<=receipt[key]<2**64:raise DataError('CAMPAIGN_RECEIPT_INVALID')
    for key in ('timed_out','assigned_before_resume','observed_children_exited'):
        if type(receipt[key]) is not bool:raise DataError('CAMPAIGN_RECEIPT_INVALID')
    if 'execution_identity' in receipt:
        from compertum.runtime.job_identity import validate_execution_identity
        validate_execution_identity(receipt['execution_identity'])
        if receipt['execution_identity']['process']['pid']!=receipt['pid']:raise DataError('CAMPAIGN_RECEIPT_INVALID')
    children=receipt['observed_child_pids']
    if not isinstance(children,list) or len(children)>64 or any(type(p) is not int or not 0<p<2**32 for p in children):raise DataError('CAMPAIGN_RECEIPT_INVALID')


def validate_state(state):
    def require(condition):
        if not condition:raise DataError('RUN_STATE_CORRUPT')
    def digest(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None
    try:
        require(is_campaign(state) and type(state.get('campaign_version')) is int and state['campaign_version']==1 and state.get('results')==[])
        outcomes=state['outcomes'];attempts=state['attempts']
        require(isinstance(outcomes,dict) and len(outcomes)<=63 and isinstance(attempts,list) and len(attempts)<=126)
        require(set(outcomes)=={u.key for u in UNITS[:len(outcomes)]})
        require(state['state'] in {'PREPARING','PAUSED','READY','RUNNING','INTERRUPTED','BLOCKED','COMPLETED','STOPPED','FAILED'})
        require(digest(state['request_sha256']))
        if 'protocol_seal' in state:
            from compertum.development_seals import validate_binding
            validate_binding(state['protocol_seal'])
        clean=state.get('clean_environment')
        if 'clean_environment' in state:
            validate_expected(clean);require(clean['run_id']==state['run_id'] and 'protocol_seal' in state)
        grouped={};previous=-1
        for attempt in attempts:
            i=attempt['unit'];require(type(i) is int and 0<=i<63 and i>=previous);previous=i
            u=UNITS[i];prior=grouped.setdefault(i,[])
            require(not prior or prior[-1]['status']=='INTERRUPTED')
            prior.append(attempt);require(len(prior)<=2 and type(attempt['attempt']) is int and attempt['attempt']==len(prior))
            require(attempt['identity']==asdict(u) and attempt['status'] in {'RUNNING','COMPLETED','FAILED','INTERRUPTED','BLOCKED'})
            require(attempt['input_sha256']==state['request_sha256'])
            require(attempt['output_path']==f"artifacts/runs/{state['run_id']}/baseline/unit-{i:02}-attempt-{attempt['attempt']}.campaign")
            dependency=outcomes.get(UNITS[u.fit_unit].key) if u.fit_unit is not None else None
            if u.fit_unit is not None:require(dependency is not None and dependency['status']=='COMPLETED')
            require(attempt['dependency_sha256']==(dependency['payload_sha256'] if dependency else None))
            if 'native_execution' in attempt:
                from compertum.runtime.job_identity import validate_execution_identity
                native=attempt['native_execution'];validate_execution_identity(native);check_native(native,clean)
                require(native['task_id']==state['run_id'] and native['role']=='experiment_runner' and native['code_sha256']==state['identity']['package_sha256'] and native['lock_sha256']==state['identity']['lock_sha256'])
            if clean is not None and attempt['status']=='COMPLETED':require('native_execution' in attempt)
            if 'native_execution' in attempt and attempt['status']=='COMPLETED':require('job_receipt' in attempt)
            if 'job_receipt' in attempt:
                require(attempt['job_receipt'].get('execution_identity')==attempt.get('native_execution'))
                validate_receipt(attempt['job_receipt'])
                if attempt['status']=='COMPLETED':
                    r=attempt['job_receipt'];require(r['exit_code']==0 and not r['timed_out'] and r['active_processes']==0 and r['assigned_before_resume'] and r['observed_children_exited'])
        for key,outcome in outcomes.items():
            i=outcome['unit'];require(type(i) is int and 0<=i<63);u=UNITS[i]
            require(key==u.key and outcome['identity']==asdict(u) and outcome['status'] in {'COMPLETED','FAILED','SKIPPED'})
            if outcome['status']=='SKIPPED':
                require(u.fit_unit is not None and i not in grouped and outcomes[UNITS[u.fit_unit].key]['status']=='FAILED' and outcome['reason']=='DEPENDENCY_FAILED')
                require(set(outcome)=={'unit','identity','status','reason'})
                continue
            require(i in grouped);last=grouped[i][-1];require(last['status']==outcome['status'])
            if outcome['status']=='COMPLETED':
                require(set(outcome)=={'unit','identity','status','artifact','payload_sha256','dependency_sha256'})
                artifact=outcome['artifact'];require(artifact['path']==last['output_path'] and artifact['task_id']==state['run_id'])
                require(type(artifact['size_bytes']) is int and 0<artifact['size_bytes']<=16*MIB and digest(artifact['sha256']) and digest(outcome['payload_sha256']))
                require(outcome['dependency_sha256']==last['dependency_sha256'])
            else:require(set(outcome)=={'unit','identity','status','reason'} and outcome['reason']==last['reason'])
        pending=[a[-1] for i,a in grouped.items() if UNITS[i].key not in outcomes]
        require(len(pending)<=1)
        if pending:
            require(pending[0]['unit']==len(outcomes) and pending[0] is attempts[-1] and pending[0]['status'] in {'RUNNING','INTERRUPTED','BLOCKED'})
        if state['state']=='RUNNING':require(len(pending)==1 and pending[0]['status']=='RUNNING')
        else:require(not pending or pending[0]['status']!='RUNNING')
        if state['state']=='COMPLETED':require(len(outcomes)==63)
        if state['state']=='READY':require(len(outcomes)<63)
    except (ValueError,KeyError,TypeError,IndexError,AttributeError):raise DataError('RUN_STATE_CORRUPT') from None


def history_delta(before,state):
    """Keep reconstructable changes, avoiding quadratic duplication of receipts."""
    before=before or {};changed={k:v for k,v in state.items() if k not in {'attempts','outcomes'} and (k not in before or before[k]!=v)}
    attempts={str(i):a for i,a in enumerate(state['attempts']) if i>=len(before.get('attempts',[])) or before['attempts'][i]!=a}
    outcomes={k:v for k,v in state['outcomes'].items() if before.get('outcomes',{}).get(k)!=v}
    return canonical({'schema':'campaign-history-delta-v1','previous_sha256':hashlib.sha256(canonical(before)).hexdigest() if before else None,
        'fields':changed,'attempts':attempts,'outcomes':outcomes,'state_sha256':hashlib.sha256(canonical(state)).hexdigest()})


def history(runs,run_id):
    state={};records=runs.store.conn.execute('SELECT body,sha256 FROM baseline_history WHERE run_id=? ORDER BY seq',(run_id,)).fetchall()
    for raw,digest in records:
        event=json.loads(raw)
        if event.get('schema')!='campaign-history-delta-v1' or event['previous_sha256']!=(hashlib.sha256(canonical(state)).hexdigest() if state else None):raise DataError('RUN_HISTORY_CORRUPT')
        state.update(event['fields']);state.setdefault('attempts',[]);state.setdefault('outcomes',{})
        for index,a in sorted(event['attempts'].items(),key=lambda item:int(item[0])):
            index=int(index)
            if index==len(state['attempts']):state['attempts'].append(a)
            elif 0<=index<len(state['attempts']):state['attempts'][index]=a
            else:raise DataError('RUN_HISTORY_CORRUPT')
        state['outcomes'].update(event['outcomes'])
        if hashlib.sha256(canonical(state)).hexdigest()!=digest or digest!=event['state_sha256']:raise DataError('RUN_HISTORY_CORRUPT')
    if state!=runs._load(run_id):raise DataError('RUN_HISTORY_CORRUPT')
    return state


def view(state,*,compact=False):
    outcomes=state['outcomes'];results=[r for r in outcomes.values() if r['status']=='COMPLETED']
    result={'run_id':state['run_id'],'state':state['state'],'completed_units':len(results),'resolved_units':len(outcomes),'total_units':63,
        'failed_units':sum(r['status']=='FAILED' for r in outcomes.values()),'skipped_units':sum(r['status']=='SKIPPED' for r in outcomes.values()),
        'input_artifact':state['input_artifact'],'input_kind':'synthetic-campaign','request_sha256':state['request_sha256'],
        'maximum_bytes':state['maximum_bytes'],'last_transition':state['last_transition'],'financial_acceptance':'UNVERIFIED','control_boundary':'BETWEEN_COMPLETE_CAMPAIGN_UNITS'}
    result['protocol_status']='SEALED_SYNTHETIC_DEVELOPMENT' if 'protocol_seal' in state else 'UNSEALED_DIAGNOSTIC'
    if not compact:result.update(outcomes=outcomes,results=results,attempts=state['attempts'])
    return result


def create(runs,run_id,folds,maximum_bytes):
    from compertum.modeling.campaign import build_campaign
    from .runs import runtime_identity
    from compertum.events import uuid
    uuid(run_id);campaign=build_campaign(folds,identity=runtime_identity(),maximum_bytes=maximum_bytes)
    return runs._register(run_id,json.loads(campaign.content),campaign.content,maximum_bytes,None)


def _dependency(state,index):
    parent=UNITS[index].fit_unit
    if parent is None:return None
    record=state['outcomes'].get(UNITS[parent].key)
    if record is None or record['status']!='COMPLETED':raise DataError('CAMPAIGN_DEPENDENCY_REQUIRED')
    return record


def _binding(body,bundle,index,dependency_body=None):
    u=UNITS[index];v=json.loads(body);fold=bundle['folds'][(2021,2022,2023).index(u.year)]
    if u.phase=='fit':
        from compertum.modeling.checkpoints import FitCheckpoint,read_fit_checkpoint
        read_fit_checkpoint(FitCheckpoint(body,hashlib.sha256(body).hexdigest()),expected_sha256=hashlib.sha256(body).hexdigest(),market_sha256=fold['market_sha256'],candidate_id=u.candidate_id,year=u.year,training_start=fold['training_start'],training_end=fold['training_end'])
    else:
        if any(v[k]!=fold[k] for k in ['market_sha256','training_start','training_end','start','end']) or v['prediction_report']['scoring_as_of']!=fold['scoring_as_of']:raise DataError('RUN_ARTIFACT_CORRUPT')
        if u.fit_unit is not None:
            if dependency_body is None:raise DataError('CAMPAIGN_DEPENDENCY_REQUIRED')
            fit=json.loads(dependency_body)
            if any(v[k]!=fit[k] for k in ['dataset_assembly','fit_rows','fit_manifest','fit_manifest_sha256','model','model_sha256']):raise DataError('CAMPAIGN_DEPENDENCY_INVALID')



def _owner_binding(runs,state,body,bundle,index,dependency_body=None):
    """Use worker validation only after the current committed proof chain passes."""
    if UNITS[index].phase!='fit' or state.get('clean_environment') is None:
        return _binding(body,bundle,index,dependency_body)
    from compertum.development_seals import check_campaign_seal
    from compertum.review_evidence import successful_receipt
    from .fit_record import read_binding
    validate_state(state)
    if runs._load(state['run_id'])!=state:raise DataError('CAMPAIGN_EXECUTION_UNVERIFIED')
    check_campaign_seal(runs.store,state)
    selected=[a for a in state['attempts'] if a['unit']==index]
    if not selected:raise DataError('CAMPAIGN_EXECUTION_UNVERIFIED')
    attempt=selected[-1];native=attempt.get('native_execution')
    check_native(native,state['clean_environment'])
    if (native is None or native['schema']!='native-template-execution-v3' or 'job_receipt' not in attempt
            or not successful_receipt(attempt['job_receipt'],native)):
        raise DataError('CAMPAIGN_EXECUTION_UNVERIFIED')
    unit=UNITS[index];fold=bundle['folds'][(2021,2022,2023).index(unit.year)]
    read_binding(body,expected_sha256=hashlib.sha256(body).hexdigest(),market_sha256=fold['market_sha256'],candidate_id=unit.candidate_id,year=unit.year,training_start=fold['training_start'],training_end=fold['training_end'])


def payload(runs,state,record):
    raw=runs._read(state['run_id'],record['artifact'],16*MIB)
    return read_payload(state,record,raw)


def read_payload(state,record,raw):
    body=verify_result(raw,state['request_sha256'],record['unit'],record['dependency_sha256'],expected_startup=outcome_proof(state,record['unit']),expected_environment=outcome_environment(state,record['unit']))
    if hashlib.sha256(body).hexdigest()!=record['payload_sha256']:raise DataError('RUN_ARTIFACT_CORRUPT')
    return body


def read_bundle(state,raw):
    validate_state(state);bundle=json.loads(raw)
    if bundle.get('input_kind')!='synthetic-campaign' or bundle['maximum_bytes']!=state['maximum_bytes'] or bundle['identity']!=state['identity']:raise DataError('RUN_STATE_CORRUPT')
    if (bundle.get('schema')=='synthetic-campaign-v2')!=(state.get('clean_environment') is not None):raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED')
    return bundle


def verify(runs,state,raw,*,decode):
    bundle=read_bundle(state,raw);previous=None;previous_index=None
    for index,u in enumerate(UNITS):
        record=state['outcomes'].get(u.key)
        if record is None or record['status']!='COMPLETED':continue
        dependency=_dependency(state,index);expected=dependency['payload_sha256'] if dependency else None
        if record['dependency_sha256']!=expected:raise DataError('CAMPAIGN_DEPENDENCY_INVALID')
        body=payload(runs,state,record);_owner_binding(runs,state,body,bundle,index,previous if u.fit_unit==previous_index else None)
        previous=body if u.phase=='fit' else None;previous_index=index if u.phase=='fit' else None
    return bundle if decode else None


def prepare(runs,run_id,*,reserved=False,_verification=None):
    with runs.store._live():
        state=runs._load(run_id)
        if not is_campaign(state) or state['state']!='READY':raise DataError('RUN_NOT_READY')
        if _verification is None:runs._verify(state,decode=False)
        else:_verification.check(runs,state)
        index=next((i for i,u in enumerate(UNITS) if u.key not in state['outcomes']),None)
        if index is None:raise DataError('RUN_TERMINAL')
        attempts=sum(a['unit']==index for a in state['attempts'])
        if attempts>=2:raise DataError('RUN_ATTEMPT_BOUND')
        used=runs.store.conn.execute("SELECT COALESCE(sum(CASE WHEN status='PUBLISHED' THEN written ELSE maximum END),0) FROM reservations WHERE task=? AND category='records' AND status!='SPLIT'",(run_id,)).fetchone()[0]
        if used+(0 if reserved else 16*MIB)>state['maximum_bytes']:raise DataError('RUN_BUDGET')
        dependency=_dependency(state,index)
        return {'unit':index,'identity':asdict(UNITS[index]),'attempt':attempts+1,'input_artifact':state['input_artifact'],'request_sha256':state['request_sha256'],
            'dependency_artifact':dependency['artifact'] if dependency else None,'dependency_sha256':dependency['payload_sha256'] if dependency else None,
            'output_path':f'artifacts/runs/{run_id}/baseline/unit-{index:02}-attempt-{attempts+1}.campaign'}


def begin(runs,run_id,prepared,*,reservation_id=None,_verification=None):
    with runs.store._live():
        expected=prepare(runs,run_id,reserved=reservation_id is not None,_verification=_verification)
        if prepared!=expected:raise DataError('CAMPAIGN_ADMISSION_CHANGED')
        if reservation_id is not None:
            row=runs.store.conn.execute('SELECT task,path,status,maximum FROM reservations WHERE id=?',(reservation_id,)).fetchone()
            # OPEN paths name the unpublished writer temporary file.
            if row is None or row[0]!=run_id or row[2]!='OPEN' or row[3]!=16*MIB or row[1].replace('\\','/')!=prepared['output_path']+'.partial-'+reservation_id:raise DataError('CAMPAIGN_ADMISSION_CHANGED')
        state=runs._load(run_id)
        state['attempts'].append({'unit':prepared['unit'],'identity':prepared['identity'],'attempt':prepared['attempt'],'status':'RUNNING',
            'input_sha256':prepared['request_sha256'],'dependency_sha256':prepared['dependency_sha256'],'output_path':prepared['output_path'],'reservation_id':reservation_id})
        state.update(state='RUNNING',active_owner=runs.owner)
        with runs.store.conn:runs._save(state,'UNIT_STARTED')
        return dict(prepared)


def verify_native_admission(store,owner,run_id,unit,primary,dependency,dependency_sha256,output_path,reservation_id,*,started=True,execution_identity=None):
    """Confirm the exact READY attempt, then its committed RUNNING transition."""
    with store._live():
        row=store.conn.execute('SELECT body FROM baseline_runs WHERE run_id=?',(run_id,)).fetchone()
        latest=store.conn.execute('SELECT sha256 FROM baseline_history WHERE run_id=? ORDER BY seq DESC LIMIT 1',(run_id,)).fetchone()
        if row is None or len(row[0])>512*1024 or latest is None or hashlib.sha256(row[0].encode()).hexdigest()!=latest[0]:raise DataError('CAMPAIGN_ADMISSION_UNCOMMITTED')
        state=json.loads(row[0]);validate_state(state)
        from compertum.development_seals import check_campaign_seal
        check_campaign_seal(store,state)
        if execution_identity is not None:check_native(execution_identity,state.get('clean_environment'))
        if state['input_artifact']!=primary or state['request_sha256']!=primary['sha256']:raise DataError('CAMPAIGN_ADMISSION_UNCOMMITTED')
        if started:
            if state['state']!='RUNNING' or state['active_owner']!=owner:raise DataError('CAMPAIGN_ADMISSION_UNCOMMITTED')
            attempt=state['attempts'][-1]
            if execution_identity is not None and attempt.get('native_execution')!=execution_identity:raise DataError('CAMPAIGN_EXECUTION_UNVERIFIED')
            if (attempt['unit']!=unit or attempt['input_sha256']!=primary['sha256'] or attempt['dependency_sha256']!=dependency_sha256
                    or attempt['output_path']!=output_path or attempt.get('reservation_id')!=reservation_id):raise DataError('CAMPAIGN_ADMISSION_UNCOMMITTED')
        else:
            number=1+sum(a['unit']==unit for a in state['attempts'])
            if (state['state']!='READY' or unit!=len(state['outcomes']) or number>2
                    or output_path!=f'artifacts/runs/{run_id}/baseline/unit-{unit:02}-attempt-{number}.campaign'):
                raise DataError('CAMPAIGN_ADMISSION_UNCOMMITTED')
        committed=_dependency(state,unit)
        if (committed['artifact'] if committed else None)!=dependency or (committed['payload_sha256'] if committed else None)!=dependency_sha256:raise DataError('CAMPAIGN_ADMISSION_UNCOMMITTED')
        reservation=store.conn.execute('SELECT task,path,status,maximum FROM reservations WHERE id=?',(reservation_id,)).fetchone()
        if (reservation is None or reservation[0]!=run_id or reservation[1].replace('\\','/')!=output_path+'.partial-'+reservation_id
                or reservation[2]!='OPEN' or reservation[3]!=16*MIB):raise DataError('CAMPAIGN_ADMISSION_UNCOMMITTED')


def accept(runs,run_id,artifact,*,_verification=None):
    with runs.store._live():
        state=runs._load(run_id)
        if state['state']!='RUNNING' or state['active_owner']!=runs.owner:raise DataError('RUN_NOT_RUNNING')
        attempt=state['attempts'][-1];index=attempt['unit'];dependency=_dependency(state,index)
        if artifact.get('path')!=attempt['output_path']:raise DataError('RUN_ARTIFACT_CORRUPT')
        row=runs.store.conn.execute("SELECT id,manifest FROM reservations WHERE task=? AND status='PUBLISHED' AND path=?",(run_id,artifact['path'])).fetchone()
        if row is None or json.loads(row[1])!=artifact or (attempt['reservation_id'] is not None and row[0]!=attempt['reservation_id']):raise DataError('RUN_ARTIFACT_CORRUPT')
        bundle=runs._verify(state) if _verification is None else _verification.check(runs,state)
        raw=runs._read(run_id,artifact,16*MIB)
        body=verify_result(raw,state['request_sha256'],index,attempt['dependency_sha256'],expected_startup=expected_proof(attempt.get('native_execution')),expected_environment=outcome_environment(state,index))
        _owner_binding(runs,state,body,bundle,index,payload(runs,state,dependency) if dependency else None)
        state['outcomes'][UNITS[index].key]={'unit':index,'identity':asdict(UNITS[index]),'status':'COMPLETED','artifact':artifact,
            'payload_sha256':hashlib.sha256(body).hexdigest(),'dependency_sha256':attempt['dependency_sha256']}
        attempt['status']='COMPLETED';state['state']='COMPLETED' if len(state['outcomes'])==63 else 'READY'
        with runs.store.conn:runs._save(state,'UNIT_CHECKPOINTED')
        return view(state)


def _failed(state,reason):
    attempt=state['attempts'][-1];index=attempt['unit'];u=UNITS[index]
    attempt.update(status='FAILED',reason=reason)
    state['outcomes'][u.key]={'unit':index,'identity':asdict(u),'status':'FAILED','reason':reason}
    for i,v in enumerate(UNITS):
        if v.fit_unit==index:state['outcomes'][v.key]={'unit':i,'identity':asdict(v),'status':'SKIPPED','reason':'DEPENDENCY_FAILED'}
    state['state']='COMPLETED' if len(state['outcomes'])==63 else 'READY'


def interrupt(runs,run_id,reason,*,terminal=False):
    with runs.store._live():
        state=runs._load(run_id)
        if state['state']!='RUNNING' or state['active_owner']!=runs.owner:raise DataError('RUN_NOT_RUNNING')
        if reason in {'LAUNCH_FAILED','HEALTH_HALT','UNIT_INTEGRITY_FAILURE'}:
            state['state']='BLOCKED';state['attempts'][-1].update(status='BLOCKED',reason=reason)
        elif terminal:_failed(state,reason)
        elif reason=='WORKER_FAILED' and state['attempts'][-1]['attempt']==2:_failed(state,'TRANSIENT_ATTEMPTS_EXHAUSTED')
        else:
            state['state']='INTERRUPTED';state['attempts'][-1].update(status='INTERRUPTED',reason=reason)
        with runs.store.conn:runs._save(state,'UNIT_'+state['state'])
        return view(state)


def control(runs,run_id,request_id,action,state,*,_verification=None):
    # SavedRuns already checked role, request deduplication and state/control bounds.
    if action=='resume':
        if _verification is None:runs._verify(state,decode=False)
        else:_verification.check(runs,state)
        if state['attempts']:
            last=state['attempts'][-1]
            if UNITS[last['unit']].key not in state['outcomes'] and last['status']=='BLOCKED':
                if last.get('reason') not in {'LAUNCH_FAILED','HEALTH_HALT'}:raise DataError('RUN_BLOCKED')
                last['status']='INTERRUPTED'
        if state['attempts'] and state['attempts'][-1]['attempt']==2 and state['attempts'][-1]['status']=='INTERRUPTED':_failed(state,'TRANSIENT_ATTEMPTS_EXHAUSTED')
        if state['state']!='COMPLETED':state['state']='READY'
    elif action=='pause':state['state']='PAUSED'
    else:state['state']='STOPPED'
    with runs.store.conn:
        runs._save(state,action.upper());receipt=view(state,compact=True)
        runs.store.conn.execute('INSERT INTO baseline_controls VALUES(?,?,?,?)',(run_id,request_id,action,canonical(receipt).decode()))
    return receipt


def step(runs,run_id):
    with runs.store._live():
        from compertum.development_seals import expected_environment
        if expected_environment(runs.store,run_id) is not None:raise DataError('CLEAN_NATIVE_EXECUTION_REQUIRED')
        state=runs._load(run_id)
        if state['state']=='COMPLETED':runs._verify(state);return view(state)
        prepared=prepare(runs,run_id);begin(runs,run_id,prepared)
        try:
            state=runs._load(run_id);raw=runs._read(run_id,state['input_artifact'],20*MIB);dependency=_dependency(state,prepared['unit'])
            from compertum.modeling.campaign import CampaignInput,compute_campaign_unit
            from compertum.modeling.checkpoints import FitCheckpoint
            fit=FitCheckpoint(payload(runs,state,dependency),dependency['payload_sha256']) if dependency else None
            result=compute_campaign_unit(CampaignInput(raw,state['request_sha256']),prepared['unit'],identity=state['identity'],fit_checkpoint=fit,expected_fit_sha256=dependency['payload_sha256'] if dependency else None)
            framed=pack_result(result.content,state['request_sha256'],prepared['unit'],prepared['dependency_sha256'])
            artifact=runs._publish(state,prepared['output_path'].rsplit('/',1)[-1],framed)
            return accept(runs,run_id,artifact)
        except OSError:
            result=interrupt(runs,run_id,'WORKER_FAILED')
            if result['state']=='INTERRUPTED':raise DataError('RUN_INTERRUPTED') from None
            return result
        except Exception as exc:
            if isinstance(exc,DataError) and exc.code in DETERMINISTIC:return interrupt(runs,run_id,exc.code,terminal=True)
            interrupt(runs,run_id,'UNIT_INTEGRITY_FAILURE');raise DataError('RUN_BLOCKED') from None


def scorecard(runs,run_id):
    from compertum.development_seals import expected_environment
    if expected_environment(runs.store,run_id) is not None:raise DataError('CLEAN_NATIVE_EXECUTION_REQUIRED')
    from compertum.modeling.candidate import CandidateResult
    from compertum.modeling.scorecards import FailedFold,build_scorecard
    with runs.store._live():
        state=history(runs,run_id);runs._verify(state);results=[];failures=[]
        for index,u in enumerate(UNITS):
            if u.phase!='evaluate':continue
            record=state['outcomes'].get(u.key)
            if record is None:continue
            if record['status']=='COMPLETED':results.append(CandidateResult(payload(runs,state,record),record['payload_sha256']))
            else:failures.append(FailedFold(u.candidate_id,u.year,record['reason']))
        return build_scorecard(results,failures=failures)


def bind_native_execution(runs,run_id,unit,execution_identity):
    from compertum.runtime.job_identity import validate_execution_identity
    validate_execution_identity(execution_identity)
    with runs.store._live(),runs.store.conn:
        state=runs._load(run_id)
        if state['state']!='RUNNING' or state['active_owner']!=runs.owner or state['attempts'][-1]['unit']!=unit or 'native_execution' in state['attempts'][-1]:raise DataError('CAMPAIGN_EXECUTION_UNVERIFIED')
        check_native(execution_identity,state.get('clean_environment'))
        state['attempts'][-1]['native_execution']=execution_identity
        runs._save(state,'NATIVE_EXECUTION_BOUND')
