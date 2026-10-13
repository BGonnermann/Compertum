"""Bounded snapshot lineage, published ledger closure and journal boundaries.

Readers only: no controller construction, replayed work or numerical imports.
"""
import hashlib,json,sqlite3
from types import SimpleNamespace
from .data.errors import DataError
from uuid import uuid5,NAMESPACE_URL
from .data.encoding import canonical
from .clean_registration import _text
from .evaluation_protocol import identifier,digest
from .runtime.errors import RuntimeRefused

MAX_ARTIFACTS=1024
BODY_TABLES={'final_audit_runs':24576,'final_audit_history':24576,'baseline_runs':512*1024,'baseline_history':512*1024,'audit_runs':32*1024,'audit_history':32*1024,'campaign_reviews':16*1024,'campaign_review_history':16*1024,'clean_campaign_pairs':32768,'sealed_campaigns':32768,'shortlist_tickets':32768,'final_dispatches':32768,'final_exits':4096,'final_closures':8192}


def check(ok):
    if not ok:raise RuntimeRefused('RECOVERY_LINEAGE_MISMATCH')


def exists(db,table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None


def snapshot_seals(db,project_id):
    from .evaluation_seals import replay_seal_events,MAX_EVENT_BYTES,ZERO
    rows=db.execute('SELECT sequence,'+_text('sha256',64)+','+_text('body',MAX_EVENT_BYTES)+' FROM evaluation_seal_events ORDER BY sequence LIMIT 257').fetchall() if exists(db,'evaluation_seal_events') else []
    check(len(rows)<=256);items=[]
    for seq,pin,body in rows:
        check(type(body) is str and hashlib.sha256(body.encode()).hexdigest()==pin)
        item=json.loads(body);check(canonical(item).decode()==body and seq==len(items)+1);items.append(item)
    head=dict(sequence=len(items),sha256=rows[-1][1] if rows else ZERO)
    result=replay_seal_events(project_id,items,head);check(result['status']=='VERIFIED');return result


def snapshot_consumption(db):
    from .consumption import _validate_record
    rows=db.execute('SELECT '+_text('seal_id',36)+','+_text('evaluation_id',36)+','+_text('body',8192)+' FROM consumption ORDER BY seal_id LIMIT 1025').fetchall();check(len(rows)<=1024);result={}
    for sid,eid,body in rows:
        check(type(body) is str);r=json.loads(body);_validate_record(r)
        check(canonical(r).decode()==body and (sid,eid)==(r['seal_id'],r['evaluation_id']) and sid not in result);result[sid]=r
    return result


def verify_boundary(db,project_id,manifest):
    seals=snapshot_seals(db,project_id);consumed=snapshot_consumption(db)
    if 'seal_journal' in manifest:check(manifest['seal_journal']=={k:seals[k] for k in ('sequence','sha256')})
    else:check(seals['sequence']==0)
    order=manifest.get('consumption_order')
    if order is not None:
        check(type(order) is list and len(order)==len(consumed)==len(set(order)) and set(order)==set(consumed))
        previous='0'*64
        for i,sid in enumerate(order,1):previous=hashlib.sha256(canonical(dict(schema_version=1,sequence=i,previous_sha256=previous,record=consumed[sid]))).hexdigest()
        check(manifest['consumption_guard']==dict(sequence=len(order),sha256=previous,head_event_id=str(uuid5(NAMESPACE_URL,previous)) if order else None))
    else:check(seals['sequence']==0 and manifest['consumption_guard']['sequence']==len(consumed))
    return seals,consumed


def _artifact(item):
    check(type(item) is dict and set(item)=={'artifact_id','task_id','path','size_bytes','sha256'})
    identifier(item['artifact_id']);identifier(item['task_id']);digest(item['sha256'])
    check(type(item['size_bytes']) is int and 0<=item['size_bytes']<=20*1024**2 and type(item['path']) is str and item['path'].startswith('artifacts/runs/'+item['task_id']+'/'))
    from pathlib import PurePosixPath
    check('\\' not in item['path'] and ':' not in item['path'] and '..' not in PurePosixPath(item['path']).parts and PurePosixPath(item['path']).as_posix()==item['path'])
    return {k:item[k] for k in ('artifact_id','path','size_bytes','sha256')}|{'parent_artifact_ids':[]}


def references(value,ledger,depth=0):
    check(depth<=48)
    if type(value) is dict:
        if 'artifact_id' in value or {'path','size_bytes','sha256'}<=set(value):
            check({'artifact_id','task_id','path','size_bytes','sha256'}<=set(value))
            item={k:value[k] for k in ('artifact_id','task_id','path','size_bytes','sha256')};_artifact(item)
            check(canonical(ledger.get(item['artifact_id']))==canonical(item))
        for child in value.values():references(child,ledger,depth+1)
    elif type(value) is list:
        for child in value:references(child,ledger,depth+1)


def extend_lineage(db,evaluation,project_id,config_hash,result):
    """Include all published record artifacts, including retained rejected outputs."""
    seals=snapshot_seals(evaluation,project_id);consumed=snapshot_consumption(evaluation)
    ledger={};paths=set()
    if exists(db,'reservations'):
        rows=db.execute('SELECT '+_text('task',36)+','+_text('path',1024)+','+_text('manifest',4096)+" FROM reservations WHERE category='records' AND status='PUBLISHED' ORDER BY id LIMIT 1025").fetchall();check(len(rows)<=MAX_ARTIFACTS)
        for task,path,raw in rows:
            check(type(raw) is str);item=json.loads(raw);check(canonical(item).decode()==raw and (task,path)==(item['task_id'],item['path']))
            _artifact(item);check(item['artifact_id'] not in ledger and path not in paths);ledger[item['artifact_id']]=item;paths.add(path)
    total=0;states={};state_values={}
    for table,maximum in BODY_TABLES.items():
        if not exists(db,table):continue
        count=0
        key='run_id' if table in ('baseline_runs','baseline_history','sealed_campaigns') else 'pair_id' if table in ('clean_campaign_pairs','shortlist_tickets') else 'attempt_id' if table.startswith('final_') and not table.startswith('final_audit_') else 'task_id'
        hashed=table not in ('baseline_runs','audit_runs','campaign_reviews','final_audit_runs')
        query='SELECT '+_text(key,36)+','+_text('body',maximum)+(','+_text('sha256',64) if hashed else '')+' FROM '+table+' LIMIT 4097'
        for row in db.execute(query):
            record_id,raw=row[:2];identifier(record_id);count+=1;check(count<=4096 and type(raw) is str);total+=len(raw.encode());check(total<=16*1024**2)
            value=json.loads(raw);check(canonical(value).decode()==raw);references(value,ledger)
            delta=table=='baseline_history' and value.get('schema')=='campaign-history-delta-v1'
            if hashed:check(row[2]==(value['state_sha256'] if delta else hashlib.sha256(raw.encode()).hexdigest()))
            identity=value['attempt']['attempt_id'] if table=='final_dispatches' else value['pair']['pair_id'] if table=='shortlist_tickets' else value.get(key)
            if delta:check(value['fields'].get('run_id',record_id)==record_id)
            else:check(identity==record_id)
            if table in ('baseline_runs','audit_runs','campaign_reviews','final_audit_runs'):
                check(record_id not in states);states[record_id]=value.get('state','UNVERIFIED');state_values[record_id]=(table,value,raw)
    from .final_audit_recovery import snapshot,closed
    closed(snapshot(db))
    for task,(table,value,raw) in state_values.items():
        validate_state_history(db,table,task,value,raw)
    validate_sealed_dependencies(db,project_id,seals)
    artifacts={a['artifact_id']:a for a in result['artifacts']}
    for item in ledger.values():
        entry=_artifact(item);check(entry['artifact_id'] not in artifacts or artifacts[entry['artifact_id']]==entry);artifacts[entry['artifact_id']]=entry
    check(len(artifacts)<=MAX_ARTIFACTS)
    tasks={t['task_id'] for t in result['task_states']}
    for task,status in sorted(states.items()):
        check(task not in tasks);tasks.add(task)
        state=status if status in {'REGISTERED','QUEUED','WAITING_FOR_OPERATOR','COMPLETED','FAILED','TIMED_OUT','PAUSED'} else 'UNVERIFIED'
        result['task_states'].append(dict(task_id=task,state=state,checkpoint_id=None));result['run_states'].append(dict(run_id=task,task_id=task,state=state,checkpoint_id=None))
    for sid,row in seals['seals'].items():
        references(row,ledger)
        if not row.get('final'):continue
        validate_dispatch_links(db,sid,row)
        plan=row['final']['plan'];eid=plan['evaluation_id'];cp=plan['checkpoint_id']
        check(sid in consumed and consumed[sid]['evaluation_id']==eid and consumed[sid]['inputs']==plan['inputs'] and eid not in tasks);tasks.add(eid)
        attempts=row.get('final_attempts',[]);terminal=row.get('final_complete')
        state='COMPLETED' if terminal and (not attempts or terminal['outcome']=='COMPLETED') else 'FAILED' if terminal or row['status']=='INVALIDATED' else 'UNVERIFIED'
        result['task_states'].append(dict(task_id=eid,state=state,checkpoint_id=cp));result['run_states'].append(dict(run_id=eid,task_id=eid,state=state,checkpoint_id=cp))
        result['checkpoints'].append(dict(checkpoint_id=cp,task_id=eid,run_id=eid,code_sha256=plan['runtime']['package_sha256'],config_sha256=config_hash,input_hashes=sorted(set([*plan['inputs'].values(),row['final']['plan_sha256'],hashlib.sha256(canonical(consumed[sid])).hexdigest()])),last_completed_unit='BEFORE_BATCH' if not attempts else 'ATTEMPT_'+str(len(attempts))+'_'+('CLOSED' if attempts[-1]['close'] else 'STARTED'),rng_state_artifact_id=None,artifact_ids=sorted(artifacts)))
    result['artifacts']=sorted(artifacts.values(),key=lambda x:x['artifact_id'])
    for key,identity in (('task_states','task_id'),('run_states','run_id'),('checkpoints','checkpoint_id')):result[key].sort(key=lambda x:x[identity])
    return result


def seal_references(evidence,consumed):
    return [dict(seal_id=sid,evaluation_id=r['evaluation_id'],consumption_state='CONSUMED',checkpoint_id=(evidence['seals'].get(sid,{}).get('final') or {}).get('plan',{}).get('checkpoint_id')) for sid,r in sorted(consumed.items())]


def matches_prefix(older,newer):
    return older['status']==newer['status']=='VERIFIED' and older['sequence']<=newer['sequence'] and canonical(older['events'])==canonical(newer['events'][:older['sequence']])


def reconcile_snapshot(coordinator,evaluation,project,actual,config_hash):
    """Keep the latest seal mirror; uncertain restored work remains compromised."""
    saved=snapshot_seals(evaluation,project.project_id)
    if not matches_prefix(saved,actual):return False
    with evaluation:
        evaluation.execute('CREATE TABLE IF NOT EXISTS evaluation_seal_events(sequence INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL)')
        for event in actual['events'][saved['sequence']:]:
            raw=canonical(event);evaluation.execute('INSERT INTO evaluation_seal_events VALUES(?,?,?)',(event['sequence'],hashlib.sha256(raw).hexdigest(),raw.decode()))
    try:
        from .recovery import _recovery_lineage
        _recovery_lineage(coordinator,evaluation,project,config_hash)
        return True
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,RuntimeRefused,DataError,sqlite3.Error):return False


def validate_state_history(db,table,task,value,raw):
    """Reuse pure review validators; reconstruct campaign deltas without workers."""
    if table=='final_audit_runs':
        from .final_audit_runs import _read_state
        check(canonical(_read_state(SimpleNamespace(conn=db),task))==raw.encode());return
    if table in ('audit_runs','campaign_reviews'):
        from .shortlist_evidence import history
        records=history(db,task,audit=table=='audit_runs')
        if table=='audit_runs':
            from .audit_history import reconstruct
            reconstructed=reconstruct(raw.encode(),records)
        else:
            from .review_runs import ReviewRuns
            reconstructed=ReviewRuns.reconstruct(raw.encode(),records)
            keys=db.execute('SELECT '+_text('source_run_id',36)+','+_text('kind',16)+' FROM campaign_reviews WHERE task_id=?',(task,)).fetchall()
            check(keys==[(value['source_run_id'],value['kind'])])
        check(canonical(reconstructed)==canonical(value));return
    check('input_artifact' in value)
    if value['input_artifact'] is None:check(value['state'] in ('PREPARING','FAILED'))
    else:_artifact(value['input_artifact'])
    rows=db.execute('SELECT seq,'+_text('body',512*1024)+','+_text('sha256',64)+' FROM baseline_history WHERE run_id=? ORDER BY seq LIMIT 1025',(task,)).fetchall()
    check(0<len(rows)<=1024);state={}
    for number,(seq,body,pin) in enumerate(rows,1):
        check(type(body) is str and seq==number);event=json.loads(body);check(canonical(event).decode()==body)
        if value.get('input_kind')=='synthetic-campaign':
            check(event.get('schema')=='campaign-history-delta-v1' and event['previous_sha256']==(hashlib.sha256(canonical(state)).hexdigest() if state else None))
            state.update(event['fields']);state.setdefault('attempts',[]);state.setdefault('outcomes',{})
            for i,a in sorted(event['attempts'].items(),key=lambda x:int(x[0])):
                i=int(i);check(0<=i<=len(state['attempts']))
                if i==len(state['attempts']):state['attempts'].append(a)
                else:state['attempts'][i]=a
            state['outcomes'].update(event['outcomes']);check(hashlib.sha256(canonical(state)).hexdigest()==event['state_sha256']==pin)
        else:state=event;check(hashlib.sha256(body.encode()).hexdigest()==pin and state['run_id']==task)
    check(canonical(state).decode()==raw)
    if value.get('input_kind')=='synthetic-campaign':
        from .simulation.campaign_runs import validate_state
        validate_state(value)


def validate_sealed_dependencies(db,project_id,seals):
    from .clean_registration import read_registration
    from .development_seals import read_ticket
    from .shortlist_evidence import load_review
    from .shortlist_ticket import review_pin
    project=SimpleNamespace(project_id=project_id)
    for sid,row in seals['seals'].items():
        protocol=row['creation']['protocol'];clean=protocol.get('clean_pair')
        if clean:
            pair=read_registration(db,project,clean['record']['pair_id'])
            check(pair.content==canonical(clean['record']) and pair.sha256==clean['sha256'])
            admitted=read_ticket(db,project,protocol['development_run_id']) if exists(db,'sealed_campaigns') else None
            if row['admission'] is not None:check(admitted is not None and admitted['sha256']==row['admission']['ticket_sha256'])
            if admitted is not None:check(admitted['body']['seal_id']==sid and canonical(admitted['protocol'])==canonical(protocol))
        if row['freeze'] is not None:
            ticket=row['freeze']['ticket']
            saved=db.execute('SELECT '+_text('body',32768)+','+_text('sha256',64)+' FROM shortlist_tickets WHERE seal_id=?',(sid,)).fetchall()
            check(saved==[(canonical(ticket).decode(),row['freeze']['ticket_sha256'])])
            for pin in ticket['reviews'].values():
                state,records=load_review(db,pin['task_id']);check(canonical(review_pin(state,records))==canonical(pin))


def verify_file_dependencies(db,lineage,root,supplied=None):
    """Inspect bounded request headers and TaskSpecs, never result/model payloads."""
    from .persistence import checked_path
    from .final_audit_recovery import verify_artifacts
    verify_artifacts(db,lineage,root,supplied)
    ledger={a['artifact_id']:{k:a[k] for k in ('artifact_id','path','size_bytes','sha256')}|{'task_id':a['path'].split('/')[2]} for a in lineage['artifacts'] if a['path'].startswith('artifacts/runs/')}
    paths={a['path']:a for a in ledger.values()}
    for a in ledger.values():
        path=a['path'];name=path.rsplit('/',1)[-1]
        review=path.endswith('/review/input/request.review')
        task='/input/' in path and name.startswith('task') and name.endswith('.json')
        final='/input/final/' in path and name.startswith('attempt-') and name.endswith('.json')
        if not (review or task or final):continue
        actual=a if supplied is None else supplied.get(a['artifact_id']);check(actual is not None)
        with checked_path(root,root/actual['path']).open('rb') as stream:
            raw=stream.readline(65537) if review else stream.read(65537)
        check(0<len(raw)<=65536)
        if review:check(raw.endswith(b'\n'));raw=raw[:-1]
        value=json.loads(raw);check(canonical(value)==raw);references(value,ledger)
        if review:
            for record in value['records']:
                kind=record['kind'];owner=record['artifact']['task_id']
                if kind in ('unit_audit','scorecard','aggregate'):
                    table='audit_runs' if kind=='unit_audit' else 'campaign_reviews'
                    check(exists(db,table) and db.execute('SELECT count(*) FROM '+table+' WHERE task_id=?',(owner,)).fetchone()==(1,))
        if task:
            inputs=value['permissions']['filesystem_bundle'];pins=value['input_hashes']
            check(type(inputs) is list and type(pins) is list and len(inputs)==len(pins) and all(p in paths for p in inputs))
            check(sorted(paths[p]['sha256'] for p in inputs)==sorted(pins))


def validate_dispatch_links(db,sid,row):
    """Every durable final transition retains its exact coordinator preparation."""
    from .final_dispatch import FIELDS
    attempts=[(v['start']['attempt'],v['close']) for v in row.get('final_attempts',[])]
    lost=row.get('invalidation')
    if lost and lost['operation']=='ABANDON_FINAL_PREPARATION':attempts.append((lost['attempt'],None))
    for a,close in attempts:
        check(exists(db,'final_dispatches'))
        saved=db.execute('SELECT '+_text('body',32768)+','+_text('sha256',64)+' FROM final_dispatches WHERE seal_id=? AND attempt_id=?',(sid,a['attempt_id'])).fetchall()
        check(len(saved)==1 and type(saved[0][0]) is str and hashlib.sha256(saved[0][0].encode()).hexdigest()==saved[0][1])
        d=json.loads(saved[0][0]);check(type(d) is dict and set(d)==FIELDS and d['schema']=='synthetic-final-dispatch-v1' and d['seal_id']==sid and canonical(d).decode()==saved[0][0] and canonical(d['attempt'])==canonical(a))
        if lost and lost['operation']=='ABANDON_FINAL_PREPARATION' and lost['attempt']['attempt_id']==a['attempt_id']:check(saved[0][1]==lost['dispatch_sha256'])
        _artifact(d['request_artifact']);_artifact(d['task_artifact'])
        check(d['task_artifact']['sha256']==a['task_sha256'])
        if close and 'job_receipt' in close:
            from .final_completion import _exit,_read,MODES
            value,exit_pin=_exit(db,a);check(canonical(value['job_receipt'])==canonical(close['job_receipt']))
            proposal,_=_read(db,'final_closures',a['attempt_id'],8192)
            check(type(proposal) is dict and set(proposal)=={'schema','seal_id','attempt_id','exit_sha256','mode','publication'} and proposal['schema']=='synthetic-final-closure-v1' and proposal['seal_id']==sid and proposal['attempt_id']==a['attempt_id'] and proposal['exit_sha256']==exit_pin and proposal['mode'] in MODES)
            if proposal['mode']=='COMPLETED':
                from .final_attempts import _publication
                _publication(proposal['publication'],a)
            else:check(proposal['publication'] is None)
            if close['publication'] is not None:check(canonical(close['publication'])==canonical(proposal['publication']))


def final_evidence(db):
    result={}
    for table,limit in (('final_dispatches',32768),('final_exits',4096),('final_closures',8192)):
        result[table]={}
        if not exists(db,table):continue
        rows=db.execute('SELECT '+_text('attempt_id',36)+','+_text('body',limit)+','+_text('sha256',64)+' FROM '+table+' ORDER BY attempt_id LIMIT 65').fetchall();check(len(rows)<=64)
        for aid,raw,pin in rows:
            identifier(aid);check(type(raw) is str and hashlib.sha256(raw.encode()).hexdigest()==pin);value=json.loads(raw);check(canonical(value).decode()==raw)
            check((value['attempt']['attempt_id'] if table=='final_dispatches' else value['attempt_id'])==aid);result[table][aid]=value
    return result


def final_evidence_prefix(older,newer):
    """Dispatch may acquire its native identity once; exits/closures are immutable."""
    from copy import deepcopy
    for table,records in older.items():
        for aid,old in records.items():
            new=newer[table].get(aid)
            if new is None:return False
            if table=='final_dispatches':
                old=deepcopy(old);new=deepcopy(new);before=old['attempt'].pop('native_execution');after=new['attempt'].pop('native_execution')
                if before is not None and canonical(before)!=canonical(after):return False
            if canonical(old)!=canonical(new):return False
    return True
