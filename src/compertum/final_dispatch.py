"""Committed final dispatch; evaluation reads coordinator state independently.

This module never imports the numerical engine or grants authority from JSON.
"""
from copy import deepcopy
from datetime import datetime,timezone
import json,sqlite3,time
from types import SimpleNamespace
from uuid import uuid4
from .runtime.job_identity import validate_execution_identity
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier,digest
from .clean_registration import _text
from .persistence import _active_store_path
from .review_evidence import sha,published
from .final_request import build_request,read_request
from .final_task import build_task,validate_task
from .final_attempts import ATTEMPT_FIELDS,_start
from .runtime.owners import require_live_owner
from .runtime.errors import RuntimeRefused

MAXIMUM=32768
FIELDS={'schema','seal_id','attempt','request_artifact','task_artifact'}

def check(ok):
    if not ok:raise DataError('FINAL_DISPATCH_UNVERIFIED')

def context(project,seal_id,*,active_only=True):
    from .evaluation_seals import verify_seal_journal
    from .consumption import verify_consumption_guard
    from .final_transaction import final_receipt
    evidence=verify_seal_journal(project);guard=verify_consumption_guard(project)
    check(evidence['status']=='VERIFIED' and guard['status']=='VERIFIED')
    receipt=final_receipt(project.project_id,evidence,guard,seal_id)
    if active_only:check(receipt['status'] in ('CONSUMED_WAITING_FOR_BATCH','BATCH_INTERRUPTED','BATCH_RUNNING'))
    else:check(receipt['status']!='INVALIDATED')
    return evidence,guard,receipt

def mirrors(project,evidence,guard,seal_id):
    from .development_seals import _mirror
    _mirror(project,evidence)
    path=_active_store_path(project.root_path,project.project_id,'evaluation')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
    try:
        check(dict(db.execute('SELECT key,value FROM metadata'))=={'schema_version':'1','project_id':project.project_id,'role':'evaluation'})
        record=guard['consumed'][seal_id]
        rows=db.execute('SELECT evaluation_id,'+_text('body',8192)+' FROM consumption WHERE seal_id=?',(seal_id,)).fetchall()
        check(rows==[(record['evaluation_id'],canonical(record).decode())])
    finally:db.close()

def source_artifact(storage,row):
    run=row['freeze']['ticket']['pair']['source']['run_id'];protocol=row['creation']['protocol']
    found=storage.store.conn.execute('SELECT '+_text('body',512*1024)+' FROM baseline_runs WHERE run_id=?',(run,)).fetchone()
    check(found is not None and type(found[0]) is str);s=json.loads(found[0]);check(canonical(s).decode()==found[0])
    check(s['run_id']==run and s['input_kind']=='synthetic-campaign' and s['state']=='COMPLETED')
    a=s['input_artifact'];check(a['task_id']==run and a['path']==f'artifacts/runs/{run}/baseline/inputs.json' and a['sha256']==s['request_sha256']==protocol['development_sha256'])
    published(storage,a,20*1024**2);return a

def read_dispatch(db,project,seal_id,attempt_id,evidence,guard,*,closing=False):
    """Bounded read of committed task, source and open output reservation."""
    identifier(seal_id);identifier(attempt_id)
    found=db.execute('SELECT '+_text('body',MAXIMUM)+','+_text('sha256',64)+' FROM final_dispatches WHERE seal_id=? AND attempt_id=?',(seal_id,attempt_id)).fetchone()
    check(found is not None and type(found[0]) is str and sha(found[0].encode())==found[1])
    d=json.loads(found[0]);check(type(d) is dict and set(d)==FIELDS and canonical(d).decode()==found[0] and d['schema']=='synthetic-final-dispatch-v1' and d['seal_id']==seal_id)
    a=d['attempt'];check(type(a) is dict and set(a)==ATTEMPT_FIELDS and a['attempt_id']==attempt_id)
    row=evidence['seals'][seal_id];plan=row['final']['plan'];prior=row.get('final_attempts',[])
    check(bool(plan['selected']) and (closing or row.get('final_complete') is None))
    own=prior[-1] if prior and prior[-1]['start']['attempt']['attempt_id']==attempt_id else None
    check(own is None or closing or own['close'] is None)
    check(row.get('final_complete') is None or own is not None)
    previous=prior[:-1] if own else prior
    check(not previous or previous[-1]['close'] is not None and previous[-1]['close']['outcome']=='INTERRUPTED')
    charged=previous[-1]['close']['charged_ms'] if previous else 0
    check(type(a['number']) is int and a['number']==len(previous)+1<=2 and a['charged_before_ms']==charged)
    storage=SimpleNamespace(root=project.root_path,store=SimpleNamespace(conn=db))
    source=source_artifact(storage,row)
    raw=published(storage,d['request_artifact'],32768,read=True)
    request=read_request(raw,expected_sha256=d['request_artifact']['sha256'])
    expected=build_request(plan,plan_sha256=row['final']['plan_sha256'],consumption_sha256=sha(canonical(guard['consumed'][seal_id])),number=a['number'],source_artifact=source)
    check(raw==expected and a['attempt_id']==request['attempt_id'])
    task=d['task_artifact'];check(task['task_id']==plan['evaluation_id'] and task['path']==f"artifacts/runs/{plan['evaluation_id']}/input/final/task-attempt-{a['number']:02}.json")
    task_raw=published(storage,task,64*1024,read=True);payload=json.loads(task_raw);check(canonical(payload)==task_raw)
    validate_task(project.root_path,payload,raw,d['request_artifact'],charged_ms=charged)
    expected_attempt=dict(number=a['number'],attempt_id=request['attempt_id'],evaluation_id=plan['evaluation_id'],checkpoint_id=plan['checkpoint_id'],plan_sha256=row['final']['plan_sha256'],consumption_sha256=request['consumption_sha256'],task_sha256=sha(task_raw),reservation_id=identifier(a['reservation_id']),output_path=f"artifacts/runs/{plan['evaluation_id']}/final/attempt-{a['number']:02}.final",native_execution=a['native_execution'],charged_before_ms=charged,started_at=payload['created_at'],deadline_at=payload['deadline_at'])
    check(canonical(a)==canonical(expected_attempt))
    if closing:
        reserve=db.execute("SELECT count(*) FROM reservations WHERE id=? AND task=? AND category='records' AND typeof(maximum)='integer' AND maximum=? AND typeof(written)='integer' AND written BETWEEN 0 AND maximum AND length(CAST(path AS BLOB))<=1024 AND ((status IN ('OPEN','ABANDONED') AND replace(path,char(92),'/')=? AND manifest IS NULL) OR (status='PUBLISHED' AND path=? AND typeof(manifest)='text' AND length(CAST(manifest AS BLOB))<=4096))",(a['reservation_id'],plan['evaluation_id'],16*1024**2,a['output_path']+'.partial-'+a['reservation_id'],a['output_path'])).fetchone()
    else:
        reserve=db.execute("SELECT count(*) FROM reservations WHERE id=? AND task=? AND category='records' AND typeof(maximum)='integer' AND maximum=? AND typeof(written)='integer' AND written=0 AND status='OPEN' AND length(CAST(path AS BLOB))<=1024 AND replace(path,char(92),'/')=? AND manifest IS NULL",(a['reservation_id'],plan['evaluation_id'],16*1024**2,a['output_path']+'.partial-'+a['reservation_id'])).fetchone()
    check(reserve==(1,))
    if a['native_execution'] is not None:
        projected=deepcopy(row);projected['final_attempts']=previous;projected['final_complete']=None
        record=own['start'] if own else dict(operation='START_FINAL_BATCH',seal_id=seal_id,created_at=a['started_at'] if closing else datetime.now(timezone.utc).isoformat(),owner_instance=str(uuid4()),owner_generation=1,attempt=a)
        check(canonical(record['attempt'])==canonical(a));_start(projected,record)
    return d,payload

def start_final(seals,seal_id,attempt_id,dispatch_sha256):
    """Private evaluation-owner RPC: caller supplies only committed row identity."""
    from .shortlist_freeze import owner_ticket
    from .final_transaction import final_receipt,_mirror_consumption
    from .evaluation_seals import runtime_identity
    identifier(seal_id);identifier(attempt_id);digest(dispatch_sha256);deadline=time.monotonic()+4
    with seals.store._live() as scope:
        require_live_owner(seals.store.lease,'evaluation')
        evidence,guard,_=context(seals.project,seal_id);seals._mirror(evidence);row=evidence['seals'][seal_id]
        _mirror_consumption(seals,row['final']['plan'],guard['consumed'][seal_id])
        check(row['creation']['protocol']['runtime']==json.loads(canonical(runtime_identity())))
        frozen=row['freeze'];check(owner_ticket(seals.project,seal_id,frozen['ticket_sha256'],evidence)==frozen['ticket'])
        path=_active_store_path(seals.project.root_path,seals.project.project_id,'coordinator')
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:
            db.execute('BEGIN');check(dict(db.execute('SELECT key,value FROM metadata'))=={'schema_version':'1','project_id':seals.project.project_id,'role':'coordinator'})
            d,_=read_dispatch(db,seals.project,seal_id,attempt_id,evidence,guard)
            check(sha(canonical(d))==dispatch_sha256 and d['attempt']['native_execution'] is not None)
            check(time.monotonic()<deadline)
            previous=row.get('final_attempts',[])
            if previous and previous[-1]['start']['attempt']['attempt_id']==attempt_id:check(canonical(previous[-1]['start']['attempt'])==canonical(d['attempt']))
            else:
                record=seals._record(seal_id,'START_FINAL_BATCH');record['attempt']=d['attempt']
                seals._append(evidence,record,scope)
        finally:db.close()
        return final_receipt(seals.project.project_id,seals._evidence(),guard,seal_id)

class FinalRuns:
    def __init__(self,storage):
        self.storage=storage;self.store=storage.store
        with self.store._live(),self.store.conn:
            require_live_owner(storage.lease,'coordinator')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS final_dispatches(seal_id TEXT NOT NULL,attempt_id TEXT PRIMARY KEY,body TEXT NOT NULL,sha256 TEXT NOT NULL)')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS final_exits(attempt_id TEXT PRIMARY KEY,body TEXT NOT NULL,sha256 TEXT NOT NULL)')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS final_closures(attempt_id TEXT PRIMARY KEY,body TEXT NOT NULL,sha256 TEXT NOT NULL)')

    def _publish(self,task,path,raw):
        grant=self.storage.reserve_bytes(task,'records',len(raw));writer=self.storage.open_artifact(grant,path)
        try:writer.write(raw);return writer.publish()
        finally:writer.close()

    def prepare(self,seal_id,*,now):
        with self.store._live() as scope:
            evidence,guard,receipt=context(scope.project,seal_id);mirrors(scope.project,evidence,guard,seal_id)
            check(receipt['status']!='BATCH_RUNNING');row=evidence['seals'][seal_id];plan=row['final']['plan'];eid=plan['evaluation_id'];prior=row.get('final_attempts',[])
            check(bool(plan['selected']) and len(prior)<2)
            number=len(prior)+1;charged=prior[-1]['close']['charged_ms'] if prior else 0
            source=source_artifact(self.storage,row)
            raw=build_request(plan,plan_sha256=row['final']['plan_sha256'],consumption_sha256=receipt['consumption_sha256'],number=number,source_artifact=source)
            request=read_request(raw,expected_sha256=sha(raw));aid=request['attempt_id']
            check(self.store.conn.execute('SELECT 1 FROM final_dispatches WHERE attempt_id=?',(aid,)).fetchone() is None)
            request_artifact=self._publish(eid,f'artifacts/runs/{eid}/input/final/attempt-{number:02}.json',raw)
            task=build_task(self.storage.root,raw,request_artifact,charged_ms=charged,now=now);payload=task.to_payload()
            task_artifact=self._publish(eid,f'artifacts/runs/{eid}/input/final/task-attempt-{number:02}.json',canonical(payload))
            grant=self.storage.reserve_bytes(eid,'records',16*1024**2);output=f'artifacts/runs/{eid}/final/attempt-{number:02}.final';writer=self.storage.open_artifact(grant,output)
            try:
                a=dict(number=number,attempt_id=aid,evaluation_id=eid,checkpoint_id=plan['checkpoint_id'],plan_sha256=row['final']['plan_sha256'],consumption_sha256=receipt['consumption_sha256'],task_sha256=task_artifact['sha256'],reservation_id=grant.grant_id,output_path=output,native_execution=None,charged_before_ms=charged,started_at=payload['created_at'],deadline_at=payload['deadline_at'])
                d=dict(schema='synthetic-final-dispatch-v1',seal_id=seal_id,attempt=a,request_artifact=request_artifact,task_artifact=task_artifact);body=canonical(d);check(len(body)<=MAXIMUM)
                with self.store.conn:
                    check(self.store.conn.execute('SELECT count(*) FROM final_dispatches').fetchone()[0]<64)
                    self.store.conn.execute('INSERT INTO final_dispatches VALUES(?,?,?,?)',(seal_id,aid,body.decode(),sha(body)))
                    check(self.store.conn.execute('SELECT body,sha256 FROM final_dispatches WHERE attempt_id=?',(aid,)).fetchall()==[(body.decode(),sha(body))])
                self.verify_launch(d,payload,grant.grant_id)
                return d,task,writer
            except BaseException:writer.close();raise

    def verify_launch(self,prepared,payload,reservation_id,*,execution_identity=None):
        with self.store._live() as scope:
            evidence,guard,_=context(scope.project,prepared['seal_id']);mirrors(scope.project,evidence,guard,prepared['seal_id'])
            d,actual=read_dispatch(self.store.conn,scope.project,prepared['seal_id'],prepared['attempt']['attempt_id'],evidence,guard)
            expected=deepcopy(prepared);expected['attempt']['native_execution']=d['attempt']['native_execution']
            check(canonical(d)==canonical(expected) and canonical(payload)==canonical(actual) and reservation_id==d['attempt']['reservation_id'])
            if execution_identity is None:check(d['attempt']['native_execution'] is None)
            else:
                validate_execution_identity(execution_identity)
                check(canonical(d['attempt']['native_execution'])==canonical(execution_identity))
                attempts=evidence['seals'][d['seal_id']].get('final_attempts',[])
                check(attempts and attempts[-1]['close'] is None and canonical(attempts[-1]['start']['attempt'])==canonical(d['attempt']))
            return d

    def begin(self,prepared,native,*,evaluation):
        from .development_seals import _caller
        validate_execution_identity(native)
        from .final_transaction import final_receipt
        with self.store._live() as scope:
            evidence,guard,_=context(scope.project,prepared['seal_id']);mirrors(scope.project,evidence,guard,prepared['seal_id'])
            d,payload=read_dispatch(self.store.conn,scope.project,prepared['seal_id'],prepared['attempt']['attempt_id'],evidence,guard)
            expected=deepcopy(prepared);expected['attempt']['native_execution']=d['attempt']['native_execution'];check(canonical(d)==canonical(expected))
            if d['attempt']['native_execution'] is None:
                d['attempt']['native_execution']=native;body=canonical(d);check(len(body)<=MAXIMUM)
                with self.store.conn:
                    self.store.conn.execute('UPDATE final_dispatches SET body=?,sha256=? WHERE attempt_id=?',(body.decode(),sha(body),d['attempt']['attempt_id']))
                    check(self.store.conn.execute('SELECT body,sha256 FROM final_dispatches WHERE attempt_id=?',(d['attempt']['attempt_id'],)).fetchall()==[(body.decode(),sha(body))])
            else:check(canonical(d['attempt']['native_execution'])==canonical(native))
            result=_caller(evaluation,scope.project)(dict(operation='start_final',seal_id=d['seal_id'],attempt_id=d['attempt']['attempt_id'],dispatch_sha256=sha(canonical(d))))
            self.verify_launch(prepared,payload,d['attempt']['reservation_id'],execution_identity=native)
            evidence,guard,_=context(scope.project,d['seal_id']);check(result==final_receipt(scope.project.project_id,evidence,guard,d['seal_id']))
            return result
