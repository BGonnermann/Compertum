"""Bounded audit snapshot continuity. Older recovery sets cannot reset attempts."""
from types import SimpleNamespace
from .data.encoding import canonical
from .runtime.errors import RuntimeRefused
from .final_audit_runs import _read_state,_key
from .clean_registration import _text


def check(ok):
    if not ok:raise RuntimeRefused('FINAL_AUDIT_RECOVERY_UNVERIFIED')


def snapshot(db):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('final_audit_runs','final_audit_history')")}
    if not tables:return {}
    check(tables=={'final_audit_runs','final_audit_history'})
    ids=db.execute('SELECT '+_text('task_id',36)+' FROM final_audit_runs ORDER BY task_id LIMIT 65').fetchall();check(len(ids)<=64)
    rows=db.execute('SELECT '+_text('task_id',36)+',seq,'+_text('body',24576)+','+_text('sha256',64)+','+_text('previous_sha256',64)+' FROM final_audit_history ORDER BY task_id,seq LIMIT 2049').fetchall();check(len(rows)<=2048)
    expected={t for (t,) in ids};check(all(t in expected for t,*_ in rows))
    result={};keys=set();total=0
    for (task,) in ids:
        state=_read_state(SimpleNamespace(conn=db),task);key=_key(state['evaluation_id'],state['auditor_runtime'],state['auditor_environment']['lane'])
        check(key not in keys);keys.add(key)
        history=[dict(seq=n,body=b,sha256=h,previous_sha256=prev) for t,n,b,h,prev in rows if t==task]
        total+=len(canonical(state))+sum(len(v['body'].encode()) for v in history);check(total<=16*1024**2)
        result[task]=dict(audit_key=key,state=state,history=history)
    return result


def closed(evidence):
    for item in evidence.values():
        for a in item['state']['attempts']:
            check(a['job_receipt'] is not None or a['exit_observation'] is not None or a['closed_unbound'] is not None)
    return evidence


def preserves(older,newer):
    """Both inputs have passed snapshot validation; compare exact history prefixes."""
    for task,old in older.items():
        new=newer.get(task)
        if new is None or old['audit_key']!=new['audit_key'] or len(old['history'])>len(new['history']):return False
        if canonical(old['history'])!=canonical(new['history'][:len(old['history'])]):return False
    return True


_CURRENT=object()


def require_preserved(project,candidate,*,prior_active=_CURRENT):
    """Refuse before generation publication if any retained audit history is lost."""
    import hashlib,json,sqlite3
    from .persistence import checked_path,_active_store_path,STORE_NAMES
    from .domain import RecoveryManifest
    from .evaluation_protocol import identifier
    restored=closed(snapshot(candidate))
    def inspect(path):
        path=checked_path(project.root_path,path);db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try:
            check(dict(db.execute('SELECT key,value FROM metadata'))=={'schema_version':'1','project_id':project.project_id,'role':'coordinator'})
            check(preserves(closed(snapshot(db)),restored))
        finally:db.close()
    if prior_active is _CURRENT:current=_active_store_path(project.root_path,project.project_id,'coordinator')
    elif prior_active is None:current=project.root_path/'state'/STORE_NAMES['coordinator']
    else:
        check(type(prior_active) is dict and set(prior_active)=={'schema_version','project_id','generation','operation_id'} and prior_active['schema_version']==1 and prior_active['project_id']==project.project_id)
        identifier(prior_active['generation']);identifier(prior_active['operation_id'])
        current=checked_path(project.root_path,project.root_path/'state/generations'/prior_active['generation']/STORE_NAMES['coordinator'])
    if current.exists():inspect(current)
    count=0
    for path in (project.root_path/'backups').glob('*/*/manifest.json'):
        count+=1;check(count<=128)
        with checked_path(project.root_path,path).open('rb') as stream:raw=stream.read(1048577)
        check(len(raw)<=1048576);manifest=RecoveryManifest(json.loads(raw),project_root=project.root_path).to_payload();check(manifest['project_id']==project.project_id)
        item=next(s for s in manifest['snapshots'] if s['owner_role']=='coordinator');source=checked_path(project.root_path,project.root_path/item['path'])
        check(source.stat().st_size==item['size_bytes'])
        with source.open('rb') as stream:check(hashlib.file_digest(stream,'sha256').hexdigest()==item['sha256'])
        inspect(source)



def verify_artifacts(db,lineage,root,supplied=None):
    """Close bounded audit requests and original/output publications over the ledger."""
    import hashlib,json
    from .persistence import checked_path
    from .final_audit_request import read_request
    from .final_audit_task import inspect_recorded_task
    from .final_audit_runs import inspect_output
    from .environment_manifest import read_manifest
    from .runtime.auditor_environment import expected_from_manifest
    from .final_completion import _read,_exit
    from .final_request import read_request as read_original
    from .historical_final_task import validate_historical_task
    from .review_evidence import successful_receipt
    from .runtime.job_identity import same_process
    from .recovery_lineage import references
    evidence=closed(snapshot(db));ledger={}
    for item in lineage['artifacts']:
        if item['path'].startswith('artifacts/runs/'):
            a={k:item[k] for k in ('artifact_id','path','size_bytes','sha256')};a['task_id']=a['path'].split('/')[2];ledger[a['artifact_id']]=a
    def read(a,maximum):
        check(ledger.get(a['artifact_id'])==a and 0<a['size_bytes']<=maximum)
        item=a if supplied is None else supplied.get(a['artifact_id']);check(item is not None)
        with checked_path(root,root/item['path']).open('rb') as stream:raw=stream.read(maximum+1)
        check(len(raw)==a['size_bytes'] and hashlib.sha256(raw).hexdigest()==a['sha256']);return raw
    def publication(a,reservation,maximum):
        rows=db.execute('SELECT category,maximum,written,status,'+_text('manifest',4096)+' FROM reservations WHERE id=? AND task=? AND path=?',(reservation,a['task_id'],a['path'])).fetchall()
        check(len(rows)==1 and rows[0][:4]==('records',maximum,a['size_bytes'],'PUBLISHED') and type(rows[0][1]) is type(rows[0][2]) is int and json.loads(rows[0][4])==a)
    def original(old):
        rows=db.execute('SELECT '+_text('body',32768)+','+_text('sha256',64)+' FROM final_dispatches WHERE seal_id=? AND sha256=? LIMIT 2',(old['seal_id'],old['dispatch_sha256'])).fetchall()
        check(len(rows)==1 and hashlib.sha256(rows[0][0].encode()).hexdigest()==rows[0][1]);d=json.loads(rows[0][0]);check(canonical(d).decode()==rows[0][0]);a=d['attempt']
        check(a['evaluation_id']==old['evaluation_id'] and a['native_execution']==old['author'] and d['request_artifact']==old['request_artifact'] and d['task_artifact']==old['task_artifact'])
        raw=read(old['request_artifact'],32768);v=read_original(raw,expected_sha256=old['request_artifact']['sha256'])
        check(v['plan']==old['plan'] and v['source_artifact']==old['source_artifact'] and v['plan_sha256']==old['plan_sha256'] and v['consumption_sha256']==old['consumption_sha256'])
        task_raw=read(old['task_artifact'],65536);task=json.loads(task_raw);check(canonical(task)==task_raw and hashlib.sha256(task_raw).hexdigest()==a['task_sha256'])
        validate_historical_task(root,task,raw,old['request_artifact'],charged_ms=a['charged_before_ms'])
        exited,exit_pin=_exit(db,a);check(exit_pin==old['original_exit_sha256'] and successful_receipt(exited['job_receipt'],old['author']))
        closure,pin=_read(db,'final_closures',a['attempt_id'],8192)
        check(pin==old['original_closure_sha256'] and closure==dict(schema='synthetic-final-closure-v1',seal_id=old['seal_id'],attempt_id=a['attempt_id'],exit_sha256=exit_pin,mode='COMPLETED',publication=dict(artifact=old['frame'],payload_sha256=old['payload_sha256'],payload_bytes=old['payload_bytes'])))
        publication(old['frame'],a['reservation_id'],16*1024**2)
    for task,item in evidence.items():
        s=item['state'];references(s,ledger);manifest=read(s['manifest'],4*1024**2);v=read_manifest(manifest,expected_sha256=s['manifest']['sha256'])
        check(v['runtime']==s['auditor_runtime'] and expected_from_manifest(manifest,s['manifest']['sha256'],task)==s['auditor_environment'])
        for a in s['attempts']:
            raw=read(a['request_artifact'],65536);request=read_request(raw,expected_sha256=a['request_artifact']['sha256']);references(request,ledger)
            check(request['task_id']==task and request['attempt']==a['number'] and request['manifest_artifact']==s['manifest'] and request['auditor_runtime']==s['auditor_runtime'] and request['original']['seal_id']==s['seal_id'] and request['original']['evaluation_id']==s['evaluation_id'] and hashlib.sha256(canonical(request['original'])).hexdigest()==s['original_sha256'])
            original(request['original']);task_raw=read(a['task_artifact'],65536);payload=json.loads(task_raw);check(canonical(payload)==task_raw)
            inspect_recorded_task(root,payload,raw,a['request_artifact'])
            if a['native_execution'] is not None:
                check(hashlib.sha256(task_raw).hexdigest()==a['native_execution']['task_sha256'])
                check(not same_process(a['native_execution'],request['original']['author']))
        if s['artifact'] is not None:
            a=s['attempts'][-1];publication(s['artifact'],a['reservation_id'],2*1024**2)
            _,report=inspect_output(s,read(s['artifact'],2*1024**2),read(a['request_artifact'],65536),read(a['task_artifact'],65536),root)
            check(report['audit_sha256']==s['audit_sha256'])
