"""Evaluation-owned final completion, bounded exit proof and streamed publication."""
from datetime import datetime,timezone
import json,sqlite3,time
from types import SimpleNamespace
from .data.encoding import canonical
from .evaluation_protocol import identifier,digest
from .clean_registration import _text
from .persistence import _active_store_path,checked_path
from .final_dispatch import check,context,mirrors,read_dispatch
from .review_evidence import sha,published,successful_receipt
from .review_frame import result_binding,verify_review
from .runtime.campaign_environment import observed_from_native
from .runtime.startup_record import expected_proof
from .runtime.job_identity import validate_execution_identity
from .runtime.owners import require_live_owner
from .runtime.errors import RuntimeRefused

MODES=frozenset({'COMPLETED','INTERRUPTED','REJECTED','STOPPED'})

def observe_exited(native):
    """Observe the original root only; denial or an indeterminate wait is unknown."""
    from .runtime._windows import WindowsAPI,NativeCallError
    from copy import deepcopy
    validate_execution_identity(native);api=WindowsAPI();p=native['process'];creation=None;wait=None
    try:
        with api.open_process(p['pid']) as process:
            creation=api.creation_time(process);wait=api.WaitForSingleObject(process.get(),0)
            if type(wait) is not int or wait not in (0,258):raise RuntimeRefused('FINAL_PROCESS_EXIT_UNVERIFIED')
            if creation==p['creation_filetime']:
                if wait!=0:raise RuntimeRefused('FINAL_PROCESS_STILL_LIVE')
                status='VERIFIED_EXIT'
            else:status='VERIFIED_PID_REUSED'
    except NativeCallError as error:
        if error.operation!='OpenProcess' or error.winerror!=87 or p['pid'] in api.process_snapshot():
            raise RuntimeRefused('FINAL_PROCESS_EXIT_UNVERIFIED') from None
        status='VERIFIED_ABSENT'
    return dict(schema='final-root-exit-v1',process=deepcopy(p),status=status,observed_at=datetime.now(timezone.utc).isoformat(),observed_creation_filetime=creation,wait_result=wait)


def require_exited(native):
    observe_exited(native)


def _receipt(receipt,native):
    success=successful_receipt(receipt,native)
    check(len(canonical(receipt))<=2048 and receipt['active_processes']==0 and receipt['assigned_before_resume'] and receipt['observed_children_exited'] and receipt['observed_child_pids']==[])
    check(receipt['memory_limit']==4*1024**3 and 0<receipt['peak_job_memory']<=4*1024**3 and 0<receipt['affinity'].bit_count()<=4)
    return success

def _save(db,table,attempt,value,maximum):
    check(table in ('final_exits','final_closures'));body=canonical(value);check(len(body)<=maximum)
    with db:
        before=db.execute('SELECT '+_text('body',maximum)+','+_text('sha256',64)+' FROM '+table+' WHERE attempt_id=?',(attempt,)).fetchall()
        expected=(body.decode(),sha(body))
        if before:check(before==[expected])
        else:db.execute('INSERT INTO '+table+' VALUES(?,?,?)',(attempt,*expected))
        check(db.execute('SELECT '+_text('body',maximum)+','+_text('sha256',64)+' FROM '+table+' WHERE attempt_id=?',(attempt,)).fetchall()==[expected])
    return sha(body)

def _read(db,table,attempt,maximum):
    check(table in ('final_exits','final_closures'))
    rows=db.execute('SELECT '+_text('body',maximum)+','+_text('sha256',64)+' FROM '+table+' WHERE attempt_id=?',(attempt,)).fetchall()
    check(len(rows)==1 and type(rows[0][0]) is str and sha(rows[0][0].encode())==rows[0][1]);v=json.loads(rows[0][0]);check(canonical(v).decode()==rows[0][0]);return v,rows[0][1]

def record_exit(runs,prepared,receipt):
    with runs.store._live() as scope:
        evidence,guard,_=context(scope.project,prepared['seal_id']);mirrors(scope.project,evidence,guard,prepared['seal_id'])
        d,_=read_dispatch(runs.store.conn,scope.project,prepared['seal_id'],prepared['attempt']['attempt_id'],evidence,guard,closing=True)
        attempts=evidence['seals'][d['seal_id']].get('final_attempts',[]);check(attempts and canonical(attempts[-1]['start']['attempt'])==canonical(d['attempt']))
        _receipt(receipt,d['attempt']['native_execution'])
        old=runs.store.conn.execute('SELECT 1 FROM final_exits WHERE attempt_id=?',(d['attempt']['attempt_id'],)).fetchone()
        if old:
            value,pin=_read(runs.store.conn,'final_exits',d['attempt']['attempt_id'],4096);check(canonical(value['job_receipt'])==canonical(receipt));return pin
        value=dict(schema='synthetic-final-exit-v1',attempt_id=d['attempt']['attempt_id'],observed_at=datetime.now(timezone.utc).isoformat(),job_receipt=receipt)
        return _save(runs.store.conn,'final_exits',d['attempt']['attempt_id'],value,4096)

def _exit(db,attempt):
    value,pin=_read(db,'final_exits',attempt['attempt_id'],4096)
    check(type(value) is dict and set(value)=={'schema','attempt_id','observed_at','job_receipt'} and value['schema']=='synthetic-final-exit-v1' and value['attempt_id']==attempt['attempt_id'])
    from .final_attempts import _time
    check(_time(value['observed_at'])>=_time(attempt['started_at']))
    _receipt(value['job_receipt'],attempt['native_execution']);return value,pin

def _publication(storage,attempt,request,runtime,publication):
    from .final_attempts import _publication as validate_publication
    from .shortlist_evidence import _reservation
    validate_publication(publication,attempt);a=publication['artifact'];_reservation(storage.store.conn,a,reservation=attempt['reservation_id']);published(storage,a,16*1024**2)
    n=attempt['native_execution'];binding=result_binding('final',attempt['evaluation_id'],request['source_artifact']['task_id'],sha(canonical(request)),runtime,n['process']['pid'],startup=expected_proof(n),environment=observed_from_native(n))
    with checked_path(storage.root,storage.root/a['path']).open('rb') as stream:proof=verify_review(stream,binding)
    check(all(proof[k]==a[k] for k in ('sha256','size_bytes')) and all(proof[k]==publication[k] for k in ('payload_sha256','payload_bytes')))

def propose_close(runs,prepared,mode,*,publication=None):
    check(type(mode) is str and mode in MODES)
    with runs.store._live() as scope:
        evidence,guard,_=context(scope.project,prepared['seal_id']);mirrors(scope.project,evidence,guard,prepared['seal_id'])
        d,_=read_dispatch(runs.store.conn,scope.project,prepared['seal_id'],prepared['attempt']['attempt_id'],evidence,guard,closing=True);a=d['attempt'];value,pin=_exit(runs.store.conn,a)
        if mode=='COMPLETED':
            request=json.loads(published(runs.storage,d['request_artifact'],32768,read=True));_publication(runs.storage,a,request,evidence['seals'][d['seal_id']]['final']['plan']['runtime'],publication)
        else:check(publication is None)
        proposal=dict(schema='synthetic-final-closure-v1',seal_id=d['seal_id'],attempt_id=a['attempt_id'],exit_sha256=pin,mode=mode,publication=publication)
        return _save(runs.store.conn,'final_closures',a['attempt_id'],proposal,8192)

def close_final(seals,seal_id,attempt_id,closure_sha256):
    from .final_transaction import final_receipt,_mirror_consumption
    from .shortlist_freeze import owner_ticket
    from .evaluation_seals import runtime_identity
    from .final_attempts import _time
    identifier(seal_id);identifier(attempt_id);digest(closure_sha256);deadline=time.monotonic()+4
    with seals.store._live() as scope:
        require_live_owner(seals.store.lease,'evaluation')
        evidence,guard,_=context(seals.project,seal_id,active_only=False);seals._mirror(evidence);row=evidence['seals'][seal_id]
        _mirror_consumption(seals,row['final']['plan'],guard['consumed'][seal_id])
        path=_active_store_path(seals.project.root_path,seals.project.project_id,'coordinator');db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:
            db.execute('BEGIN');check(dict(db.execute('SELECT key,value FROM metadata'))=={'schema_version':'1','project_id':seals.project.project_id,'role':'coordinator'})
            proposal,pin=_read(db,'final_closures',attempt_id,8192)
            check(pin==closure_sha256 and type(proposal) is dict and set(proposal)=={'schema','seal_id','attempt_id','exit_sha256','mode','publication'} and proposal['schema']=='synthetic-final-closure-v1' and proposal['seal_id']==seal_id and proposal['attempt_id']==attempt_id and type(proposal['mode']) is str and proposal['mode'] in MODES)
            attempts=row.get('final_attempts',[]);check(attempts and attempts[-1]['start']['attempt']['attempt_id']==attempt_id);a=attempts[-1]['start']['attempt'];value,exit_pin=_exit(db,a);check(proposal['exit_sha256']==exit_pin)
            check(row['creation']['protocol']['runtime']==json.loads(canonical(runtime_identity())))
            frozen=row['freeze'];check(owner_ticket(seals.project,seal_id,frozen['ticket_sha256'],evidence)==frozen['ticket'])
            d,_=read_dispatch(db,seals.project,seal_id,attempt_id,evidence,guard,closing=True);check(canonical(d['attempt'])==canonical(a))
            receipt=value['job_receipt'];success=_receipt(receipt,a['native_execution'])
            mode=proposal['mode'];publication=proposal['publication']
            if mode=='COMPLETED':
                storage=SimpleNamespace(root=seals.project.root_path,store=SimpleNamespace(conn=db));request=json.loads(published(storage,d['request_artifact'],32768,read=True));_publication(storage,a,request,row['final']['plan']['runtime'],publication)
            else:check(publication is None)
            check(time.monotonic()<deadline)
            if attempts[-1]['close'] is not None:
                closed=attempts[-1]['close'];check(canonical(closed['job_receipt'])==canonical(value['job_receipt']))
                check(closed['publication'] is None or canonical(closed['publication'])==canonical(proposal['publication']))
                return final_receipt(seals.project.project_id,evidence,guard,seal_id)
            require_exited(a['native_execution']);check(time.monotonic()<deadline)
            record=seals._record(seal_id,'TERMINATE_FINAL_BATCH');now=_time(record['created_at']);check(now>=_time(value['observed_at']))
            elapsed=now-_time(a['started_at']);charged=a['charged_before_ms']+elapsed.days*86400000+elapsed.seconds*1000+(elapsed.microseconds+999)//1000
            if receipt['exit_code'] not in (0,5,125) and not receipt['timed_out']:outcome='REJECTED'
            elif mode=='STOPPED':outcome='STOPPED'
            elif mode=='REJECTED':outcome='REJECTED'
            elif mode=='COMPLETED' and success and charged<=120000:outcome='COMPLETED'
            elif charged>119000 or a['number']==2:outcome='EXHAUSTED'
            elif mode=='INTERRUPTED' and not receipt['timed_out']:outcome='INTERRUPTED'
            else:outcome='REJECTED'
            if outcome=='INTERRUPTED':record['operation']='INTERRUPT_FINAL_BATCH'
            record.update(attempt_id=attempt_id,outcome=outcome,charged_ms=charged,job_receipt=receipt,publication=publication if outcome=='COMPLETED' else None)
            seals._append(evidence,record,scope)
        finally:db.close()
        return final_receipt(seals.project.project_id,seals._evidence(),guard,seal_id)

def close_through_owner(runs,prepared,closure_sha256,*,evaluation):
    from .development_seals import _caller
    from .final_transaction import final_receipt
    with runs.store._live() as scope:
        sid=prepared['seal_id'];aid=prepared['attempt']['attempt_id']
        result=_caller(evaluation,scope.project)(dict(operation='close_final',seal_id=sid,attempt_id=aid,closure_sha256=closure_sha256))
        evidence,guard,_=context(scope.project,sid,active_only=False);mirrors(scope.project,evidence,guard,sid)
        attempts=evidence['seals'][sid].get('final_attempts',[]);check(attempts and attempts[-1]['start']['attempt']['attempt_id']==aid and attempts[-1]['close'] is not None)
        check(canonical(result)==canonical(final_receipt(scope.project.project_id,evidence,guard,sid)));return result


def abandon_final(seals,seal_id,attempt_id):
    """Forfeit an open attempt only when no durable exit record exists."""
    from .final_transaction import final_receipt,_mirror_consumption
    identifier(seal_id);identifier(attempt_id);deadline=time.monotonic()+4
    with seals.store._live() as scope:
        require_live_owner(seals.store.lease,'evaluation')
        evidence,guard,_=context(seals.project,seal_id,active_only=False);seals._mirror(evidence);row=evidence['seals'][seal_id]
        _mirror_consumption(seals,row['final']['plan'],guard['consumed'][seal_id])
        attempts=row.get('final_attempts',[]);check(attempts and attempts[-1]['start']['attempt']['attempt_id']==attempt_id)
        previous=attempts[-1];a=previous['start']['attempt']
        check(previous['close'] is None or previous['close']['operation']=='ABANDON_FINAL_BATCH')
        path=_active_store_path(seals.project.root_path,seals.project.project_id,'coordinator');db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:
            db.execute('BEGIN');check(dict(db.execute('SELECT key,value FROM metadata'))=={'schema_version':'1','project_id':seals.project.project_id,'role':'coordinator'})
            check(db.execute('SELECT count(*) FROM final_exits WHERE attempt_id=?',(attempt_id,)).fetchone()==(0,))
            check(db.execute('SELECT count(*) FROM final_closures WHERE attempt_id=?',(attempt_id,)).fetchone()==(0,))
            d,_=read_dispatch(db,seals.project,seal_id,attempt_id,evidence,guard,closing=True);check(canonical(d['attempt'])==canonical(a))
            check(time.monotonic()<deadline)
            if previous['close'] is None:
                proof=observe_exited(a['native_execution']);check(time.monotonic()<deadline)
                record=seals._record(seal_id,'ABANDON_FINAL_BATCH')
                record.update(attempt_id=attempt_id,outcome='EXHAUSTED',charged_ms=120000,budget_basis='UNKNOWN_EXIT_FORFEITS_TOTAL',process_exit=proof,publication=None)
                seals._append(evidence,record,scope)
        finally:db.close()
        return final_receipt(seals.project.project_id,seals._evidence(),guard,seal_id)


def abandon_preparation(seals,seal_id,attempt_id):
    """Preserve lost preparation and invalidate it; never replace its artifacts."""
    from .consumption import verify_consumption_guard
    from .final_transaction import final_receipt,_mirror_consumption
    identifier(seal_id);identifier(attempt_id);deadline=time.monotonic()+4
    with seals.store._live() as scope:
        require_live_owner(seals.store.lease,'evaluation')
        evidence=seals._evidence();seals._mirror(evidence);guard=verify_consumption_guard(seals.project)
        row=evidence['seals'][seal_id];plan=row['final']['plan'];check(guard['status']=='VERIFIED')
        _mirror_consumption(seals,plan,guard['consumed'][seal_id])
        old=row['invalidation'];check(old is None or old['operation']=='ABANDON_FINAL_PREPARATION' and old['attempt']['attempt_id']==attempt_id)
        path=_active_store_path(seals.project.root_path,seals.project.project_id,'coordinator');db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:
            db.execute('BEGIN');check(dict(db.execute('SELECT key,value FROM metadata'))=={'schema_version':'1','project_id':seals.project.project_id,'role':'coordinator'})
            attempts=row.get('final_attempts',[]);check(not any(x['start']['attempt']['attempt_id']==attempt_id for x in attempts))
            check(db.execute('SELECT count(*) FROM final_exits WHERE attempt_id=?',(attempt_id,)).fetchone()==(0,))
            check(db.execute('SELECT count(*) FROM final_closures WHERE attempt_id=?',(attempt_id,)).fetchone()==(0,))
            d,_=read_dispatch(db,seals.project,seal_id,attempt_id,evidence,guard,closing=True);a=d['attempt'];pin=sha(canonical(d))
            if old is not None:check(old['dispatch_sha256']==pin and canonical(old['attempt'])==canonical(a))
            else:
                proof=observe_exited(a['native_execution']) if a['native_execution'] is not None else None
                record=seals._record(seal_id,'ABANDON_FINAL_PREPARATION');record.update(attempt=a,dispatch_sha256=pin,process_exit=proof,reason='STATUS_UNCERTAIN')
                check(time.monotonic()<deadline);seals._append(evidence,record,scope)
        finally:db.close()
        return final_receipt(seals.project.project_id,seals._evidence(),guard,seal_id)
