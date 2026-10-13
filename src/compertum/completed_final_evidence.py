"""Read-only admission of an already completed Final under its original code pin.

This module cannot start or consume an evaluation. The owner supplies verified
journal/guard state; all original publications and successful exit are rechecked.
"""
from copy import deepcopy
import json,time
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier
from .clean_registration import _text
from .final_dispatch import FIELDS,MAXIMUM,context,mirrors,source_artifact
from .final_request import build_request,read_request
from .historical_final_task import validate_historical_task
from .final_attempts import ATTEMPT_FIELDS,_start,_time
from .final_completion import _exit,_publication,_read
from .review_evidence import sha,published,successful_receipt


def _check(ok):
    if not ok:raise DataError('COMPLETED_FINAL_EVIDENCE_UNVERIFIED')


def _completed(storage,seal_id,evidence,guard):
    """Internal reader. Its inputs must come from current verified owner state."""
    identifier(seal_id);db=storage.store.conn
    row=evidence['seals'][seal_id];plan=row['final']['plan'];prior=row.get('final_attempts',[])
    terminal=row.get('final_complete')
    _check(row['status']=='SEALED' and bool(plan['selected']) and 1<=len(prior)<=2)
    _check(type(terminal) is dict and terminal['outcome']=='COMPLETED')
    own=prior[-1];a=own['start']['attempt'];aid=identifier(a['attempt_id']);closed=own['close']
    _check(type(a) is dict and set(a)==ATTEMPT_FIELDS and closed is not None and closed['outcome']=='COMPLETED')
    _check(canonical({k:terminal[k] for k in closed})==canonical(closed))
    previous=prior[:-1];charged=previous[-1]['close']['charged_ms'] if previous else 0
    _check(not previous or previous[-1]['close']['outcome']=='INTERRUPTED')
    _check(type(a['number']) is int and a['number']==len(previous)+1 and a['charged_before_ms']==charged)
    found=db.execute('SELECT '+_text('body',MAXIMUM)+','+_text('sha256',64)+' FROM final_dispatches WHERE seal_id=? AND attempt_id=?',(seal_id,aid)).fetchone()
    _check(found is not None and type(found[0]) is str and sha(found[0].encode())==found[1])
    dispatch=json.loads(found[0]);_check(type(dispatch) is dict and set(dispatch)==FIELDS and canonical(dispatch).decode()==found[0])
    _check(dispatch['schema']=='synthetic-final-dispatch-v1' and dispatch['seal_id']==seal_id and canonical(dispatch['attempt'])==canonical(a))
    source=source_artifact(storage,row);raw=published(storage,dispatch['request_artifact'],32768,read=True)
    request=read_request(raw,expected_sha256=dispatch['request_artifact']['sha256'])
    consumption_sha=sha(canonical(guard['consumed'][seal_id]))
    _check(raw==build_request(plan,plan_sha256=row['final']['plan_sha256'],consumption_sha256=consumption_sha,number=a['number'],source_artifact=source))
    task=dispatch['task_artifact'];_check(task['task_id']==plan['evaluation_id'] and task['path']==f"artifacts/runs/{plan['evaluation_id']}/input/final/task-attempt-{a['number']:02}.json")
    task_raw=published(storage,task,64*1024,read=True);payload=json.loads(task_raw);_check(canonical(payload)==task_raw)
    validate_historical_task(storage.root,payload,raw,dispatch['request_artifact'],charged_ms=charged)
    expected=dict(number=a['number'],attempt_id=request['attempt_id'],evaluation_id=plan['evaluation_id'],checkpoint_id=plan['checkpoint_id'],plan_sha256=row['final']['plan_sha256'],consumption_sha256=consumption_sha,task_sha256=sha(task_raw),reservation_id=identifier(a['reservation_id']),output_path=f"artifacts/runs/{plan['evaluation_id']}/final/attempt-{a['number']:02}.final",native_execution=a['native_execution'],charged_before_ms=charged,started_at=payload['created_at'],deadline_at=payload['deadline_at'])
    _check(canonical(a)==canonical(expected))
    projected=deepcopy(row);projected['final_attempts']=previous;projected['final_complete']=None
    _start(projected,own['start'])
    value,exit_sha=_exit(db,a)
    _check(_time(value['observed_at'])<=_time(closed['created_at']))
    _check(successful_receipt(value['job_receipt'],a['native_execution']))
    _check(canonical(value['job_receipt'])==canonical(closed['job_receipt']))
    publication=closed['publication'];frame=publication['artifact']
    reserve=db.execute("SELECT count(*) FROM reservations WHERE id=? AND task=? AND category='records' AND typeof(maximum)='integer' AND maximum=? AND typeof(written)='integer' AND written=? AND status='PUBLISHED' AND path=? AND typeof(manifest)='text' AND length(CAST(manifest AS BLOB))<=4096",(a['reservation_id'],plan['evaluation_id'],16*1024**2,frame['size_bytes'],a['output_path'])).fetchone()
    _check(reserve==(1,));_publication(storage,a,request,plan['runtime'],publication)
    closure,closure_sha=_read(db,'final_closures',aid,8192)
    _check(canonical(closure)==canonical(dict(schema='synthetic-final-closure-v1',seal_id=seal_id,attempt_id=aid,exit_sha256=exit_sha,mode='COMPLETED',publication=publication)))
    return dict(schema='completed-final-evidence-v1',seal_id=seal_id,evaluation_id=plan['evaluation_id'],plan=plan,plan_sha256=row['final']['plan_sha256'],
        consumption_sha256=consumption_sha,seal_head=dict(sequence=evidence['sequence'],sha256=evidence['sha256']),guard_head=dict(sequence=guard['sequence'],sha256=guard['sha256']),
        dispatch_sha256=found[1],request_artifact=dispatch['request_artifact'],task_artifact=task,source_artifact=source,frame=frame,payload_sha256=publication['payload_sha256'],payload_bytes=publication['payload_bytes'],
        author=a['native_execution'],original_exit_sha256=exit_sha,original_closure_sha256=closure_sha,original_result_sha256=terminal['result_sha256'])


def completed_final(storage,seal_id):
    """Called only by the live coordinator; returns no launch capability."""
    try:
        identifier(seal_id);deadline=time.monotonic()+4
        with storage.store._live() as scope:
            evidence,guard,receipt=context(scope.project,seal_id,active_only=False)
            _check(receipt['status']=='COMPLETED');mirrors(scope.project,evidence,guard,seal_id)
            result=_completed(storage,seal_id,evidence,guard)
            after,after_guard,after_receipt=context(scope.project,seal_id,active_only=False)
            _check(canonical((after,after_guard,after_receipt))==canonical((evidence,guard,receipt)))
            _check(time.monotonic()<deadline);return result
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('COMPLETED_FINAL_EVIDENCE_UNVERIFIED') from None
