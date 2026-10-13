"""Read-only, bounded proof checks used only by the evaluation shortlist owner.

Coordinator preparation rechecks all large campaign payloads. This reader checks
committed lineage, current histories, native request/output proofs and all unit
review dependencies, without importing the numerical engine.
"""
import hashlib,json,time
from types import SimpleNamespace
from .data.encoding import canonical
from .data.errors import DataError
from .clean_registration import _text
from .review_evidence import check,sha,published,successful_receipt,MIB
from .review_runs import ReviewRuns
from .review_frame import result_binding,verify_review
from .review_bundle import read_bundle,MAX_HEADER,_records
from .shortlist_ticket import review_pin
from .persistence import checked_path
from .runtime.campaign_environment import check_native,observed_from_native
from .runtime.startup_record import expected_proof
from .runtime.job_identity import same_process

COMPACT_BYTES=256*1024


def _time(deadline):
    if time.monotonic()>=deadline:raise DataError('SHORTLIST_EVIDENCE_DEADLINE')


def history(db,task,*,audit=False):
    table='audit_history' if audit else 'campaign_review_history';maximum=32*1024 if audit else 16*1024
    rows=[dict(seq=n,body=b,sha256=h,previous_sha256=p) for n,b,h,p in db.execute('SELECT seq,'+','.join(_text(k,m) for k,m in [('body',maximum),('sha256',64),('previous_sha256',64)])+' FROM '+table+' WHERE task_id=? ORDER BY seq LIMIT 33',(task,))]
    check(0<len(rows)<=32 and all(type(r['body']) is str for r in rows));return rows


def load_review(db,task):
    row=db.execute('SELECT '+','.join(_text(k,m) for k,m in [('source_run_id',36),('kind',16),('body',16*1024)])+' FROM campaign_reviews WHERE task_id=?',(task,)).fetchone()
    check(row is not None and type(row[2]) is str);records=history(db,task);s=ReviewRuns.reconstruct(row[2].encode(),records)
    check(s['task_id']==task and s['source_run_id']==row[0] and s['kind']==row[1] and s['state']=='COMPLETED')
    return s,records


def _reservation(db,artifact,*,reservation=None):
    if reservation is None:
        rows=db.execute('SELECT '+_text('manifest',4096)+" FROM reservations WHERE task=? AND path=? AND status='PUBLISHED' LIMIT 2",(artifact['task_id'],artifact['path'])).fetchall()
    else:
        rows=db.execute('SELECT '+_text('manifest',4096)+" FROM reservations WHERE id=? AND task=? AND path=? AND status='PUBLISHED' LIMIT 2",(reservation,artifact['task_id'],artifact['path'])).fetchall()
    check(len(rows)==1 and type(rows[0][0]) is str and canonical(json.loads(rows[0][0]))==canonical(artifact))


def _published(storage,artifact,maximum,*,read=False):
    _reservation(storage.store.conn,artifact)
    return published(storage,artifact,maximum,read=read)


def request_header(storage,s):
    a=s['request_artifact'];task=s['task_id']
    check(a['task_id']==task and a['path']==f'artifacts/runs/{task}/review/input/request.review' and a['sha256']==s['request_sha256'])
    _published(storage,a,16*MIB)
    path=checked_path(storage.root,storage.root/a['path'])
    if s['kind']=='pair_compare':
        check(a['size_bytes']<=128*1024)
        with path.open('rb') as f:raw=f.read(128*1024+1)
        check(len(raw)==a['size_bytes'] and sha(raw)==a['sha256'])
        h,m=read_bundle(raw,expected_sha256=s['request_sha256'],expected_kind=s['kind'],expected_task_id=task,expected_source_run_id=s['source_run_id'],expected_identity=s['identity'])
        return h,json.loads(m)
    # Large metadata remains in the committed worker input. Stream its exact
    # hash here; the two live history digests are checked separately below.
    with path.open('rb') as f:
        line=f.readline(MAX_HEADER+1);check(0<len(line)<=MAX_HEADER and line.endswith(b'\n'));h=json.loads(line[:-1])
        check(canonical(h)+b'\n'==line and set(h)=={'schema','kind','task_id','source_run_id','identity','protocol_seal','records','metadata_bytes','metadata_sha256','financial_accepted'})
        check(h['schema']=='synthetic-campaign-review-bundle-v1' and h['kind']==s['kind'] and h['task_id']==task and h['source_run_id']==s['source_run_id'] and h['identity']==s['identity'] and h['financial_accepted'] is False)
        check(type(h['metadata_bytes']) is int and 0<h['metadata_bytes']<=16*MIB-len(line) and a['size_bytes']==len(line)+h['metadata_bytes'])
        _records(h['records'],s['kind'],task,s['source_run_id']);whole=hashlib.sha256(line);meta=hashlib.sha256();left=h['metadata_bytes']
        while left:
            chunk=f.read(min(MIB,left));check(bool(chunk));left-=len(chunk);whole.update(chunk);meta.update(chunk)
        check(f.read(1)==b'' and whole.hexdigest()==a['sha256'] and meta.hexdigest()==h['metadata_sha256'])
    return h,None


def verified_review(storage,pin,environment,seal,deadline,*,compact=False):
    _time(deadline);s,records=load_review(storage.store.conn,pin['task_id']);check(review_pin(s,records)==pin)
    check(s['source_run_id']==environment['run_id'])
    for a in s['attempts']:
        if a['native_execution'] is not None:check_native(a['native_execution'],environment)
    a=s['attempts'][-1];n=a['native_execution'];check(successful_receipt(a['job_receipt'],n))
    h,meta=request_header(storage,s);check(h['protocol_seal']==seal)
    for r in h['records']:_reservation(storage.store.conn,r['artifact'])
    task_artifact=a['task_artifact'];check(task_artifact['task_id']==s['task_id'] and task_artifact['path']==f"artifacts/runs/{s['task_id']}/review/input/task-attempt-{a['number']}.json")
    task_raw=_published(storage,task_artifact,64*1024,read=True);task=json.loads(task_raw)
    check(canonical(task)==task_raw and sha(task_raw)==n['task_sha256']);ReviewRuns._payload(s,task,h)
    artifact=s['artifact'];check(artifact['task_id']==s['task_id'] and artifact['path']==a['output_path'])
    _reservation(storage.store.conn,artifact,reservation=a['reservation_id'])
    check(type(artifact['size_bytes']) is int and 0<artifact['size_bytes']<=16*MIB)
    path=checked_path(storage.root,storage.root/artifact['path'])
    binding=result_binding(s['kind'],s['task_id'],s['source_run_id'],s['request_sha256'],s['identity'],n['process']['pid'],startup=expected_proof(n),environment=observed_from_native(n))
    with path.open('rb') as f:result=verify_review(f,binding)
    check(all(result[k]==artifact[k] for k in ('sha256','size_bytes')) and result['payload_sha256']==pin['payload_sha256'] and result['payload_bytes']==pin['payload_bytes'])
    payload=None
    if compact:
        check(artifact['size_bytes']<=COMPACT_BYTES)
        with path.open('rb') as f:raw=f.read(COMPACT_BYTES+1)
        check(len(raw)==artifact['size_bytes'] and sha(raw)==artifact['sha256']);body=raw.split(b'\n',1)[1];payload=json.loads(body);check(canonical(payload)==body)
    _time(deadline);return s,h,meta,payload


def _list_digest(rows,maximum,deadline):
    digest=hashlib.sha256(b'[');total=2;count=0
    for r in rows:
        _time(deadline);raw=canonical(r);total+=len(raw)+(count>0);check(total<=maximum)
        if count:digest.update(b',')
        digest.update(raw);count+=1
    digest.update(b']');return digest.hexdigest(),count


def source_state(db,lane,deadline):
    run=lane['run_id'];row=db.execute('SELECT '+_text('body',512*1024)+' FROM baseline_runs WHERE run_id=?',(run,)).fetchone()
    check(row is not None and type(row[0]) is str);raw=row[0].encode();s=json.loads(raw)
    check(canonical(s)==raw and sha(raw)==lane['source_state_sha256'] and s['run_id']==run and s['state']=='COMPLETED' and s['input_kind']=='synthetic-campaign')
    check(s['input_artifact']==lane['input_artifact'] and s['request_sha256']==lane['input_artifact']['sha256'] and s['protocol_seal']==lane['protocol_seal'] and s['clean_environment']==lane['clean_environment'])
    outcomes=s['outcomes'];check(type(outcomes) is dict and len(outcomes)==63 and sorted(o['unit'] for o in outcomes.values())==list(range(63)) and all(o['status'] in ('COMPLETED','FAILED','SKIPPED') for o in outcomes.values()))
    def rows():
        previous=0;last=None
        for n,b,pin in db.execute('SELECT seq,'+_text('body',512*1024)+','+_text('sha256',64)+' FROM baseline_history WHERE run_id=? ORDER BY seq LIMIT 1025',(run,)):
            check(type(b) is str and type(n) is int and n==previous+1)
            delta=json.loads(b);check(type(delta) is dict and set(delta)=={'schema','previous_sha256','fields','attempts','outcomes','state_sha256'} and canonical(delta).decode()==b)
            check(delta['schema']=='campaign-history-delta-v1' and delta['state_sha256']==pin and delta['previous_sha256']==last)
            previous=n;last=pin
            yield dict(seq=n,body=b,sha256=pin)
        check(last==sha(raw))
    digest,count=_list_digest(rows(),16*MIB,deadline);check(0<count<=1024 and digest==lane['source_history_sha256'])
    def controls():
        for r,a,c in db.execute('SELECT '+','.join(_text(k,m) for k,m in [('request_id',36),('action',16),('receipt',64*1024)])+' FROM baseline_controls WHERE run_id=? ORDER BY request_id LIMIT 129',(run,)):
            check(all(type(v) is str for v in (r,a,c)));yield dict(request_id=r,action=a,receipt=c)
    digest,count=_list_digest(controls(),16*MIB,deadline);check(count<=128 and digest==lane['source_controls_sha256'])
    return s


def _unit_dependencies(storage,source,aggregate,deadline):
    from .audit_history import reconstruct
    from .aggregate_evidence import bind_unit_audit
    db=storage.store.conn;expected={o['unit'] for o in source['outcomes'].values() if o['status']=='COMPLETED' and o['identity']['phase']=='evaluate'}
    pins=aggregate['unit_audits'];check(type(pins) is list and len(pins)==len(expected) and aggregate['required_unit_audits']==len(expected));seen=set();native=[]
    for pin in pins:
        _time(deadline);task=pin['task_id'];row=db.execute('SELECT '+_text('body',32*1024)+' FROM audit_runs WHERE task_id=?',(task,)).fetchone()
        check(row is not None and type(row[0]) is str);records=history(db,task,audit=True);check(sha(canonical(records))==pin['history_sha256']);s=reconstruct(row[0].encode(),records)
        record=bind_unit_audit(s,source);unit=record['index'];check(unit in expected and unit not in seen and pin['unit']==unit and s['task_id']==task and s['artifact']['sha256']==pin['artifact_sha256'] and s['audit_sha256']==pin['audit_sha256'] and len(s['attempts'])==pin['attempts']);seen.add(unit)
        _reservation(db,s['artifact'],reservation=s['attempts'][-1]['reservation_id']);_published(storage,s['artifact'],16*MIB)
        native.extend(a['native_execution'] for a in s['attempts']);_time(deadline)
    check(seen==expected)
    if expected or db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_runs'").fetchone():
        rows=db.execute("SELECT "+_text('task_id',36)+" FROM audit_runs WHERE json_extract(body,'$.request.source_run_id')=? LIMIT 37",(source['run_id'],)).fetchall()
        check({r[0] for r in rows}=={p['task_id'] for p in pins} and len(rows)==len(pins))
    return native


def validate_committed(db,project,ticket,evidence,*,deadline=None):
    from .development_seals import read_ticket as development_ticket,_protocol_expected
    from .evaluation_seals import _freeze_ticket,seal_receipt
    from .campaign_comparison import compare_indices
    if deadline is None:deadline=time.monotonic()+4
    _freeze_ticket(project.project_id,evidence['seals'],ticket['pair']['source']['seal_id'],ticket,sha(canonical(ticket)))
    storage=SimpleNamespace(root=project.root_path,store=SimpleNamespace(conn=db));p=ticket['pair'];lanes={}
    for lane in ('source','wheel'):
        run=p[lane]['run_id']
        # Preflight legacy reader strings before it materializes a row.
        row=db.execute('SELECT '+','.join(_text(k,n) for k,n in [('body',2048),('protocol',24*1024),('receipt',4096)])+' FROM sealed_campaigns WHERE run_id=?',(run,)).fetchone();check(row is not None and all(type(v) is str for v in row))
        admitted=development_ticket(db,project,run);r=seal_receipt(project.project_id,evidence,p[lane]['seal_id']);check(admitted['receipt']==canonical(r).decode() and r['status']=='SEALED' and r['development_admitted'] and admitted['sha256']==r['ticket_sha256'])
        check(admitted['protocol']==evidence['seals'][p[lane]['seal_id']]['creation']['protocol'])
        seal=dict(seal_id=p[lane]['seal_id'],protocol_sha256=r['protocol_sha256'],ticket_sha256=r['ticket_sha256'],admission_event_sha256=r['admission_event_sha256'])
        lanes[lane]=dict(environment=_protocol_expected(admitted['protocol']),seal=seal)
    comparison,h,meta,payload=verified_review(storage,ticket['reviews']['comparison'],**lanes['source'],deadline=deadline,compact=True)
    check(payload==ticket['comparison'] and meta['pair']==p and meta['pair_sha256']==ticket['pair_sha256'])
    compare_native=[a['native_execution'] for a in comparison['attempts'] if a['native_execution'] is not None];all_dependencies=[];indices=[]
    for lane,metadata in zip(('source','wheel'),meta['lanes']):
        _time(deadline);check(metadata['protocol_seal']==lanes[lane]['seal'] and metadata['clean_environment']==lanes[lane]['environment'])
        source=source_state(db,metadata,deadline);check(source['identity']==p['runtime'])
        aggregate,header,_,report=verified_review(storage,ticket['reviews'][lane+'_aggregate'],**lanes[lane],deadline=deadline,compact=True)
        a=aggregate['attempts'][-1];pin=metadata['aggregate'];expected=dict(task_id=aggregate['task_id'],request_sha256=aggregate['request_sha256'],artifact=aggregate['artifact'],payload_sha256=aggregate['payload_sha256'],payload_bytes=aggregate['payload_bytes'],native_execution=a['native_execution'],job_receipt=a['job_receipt'],history_sha256=ticket['reviews'][lane+'_aggregate']['history_sha256']);check(pin==expected)
        check(report['schema']=='synthetic-native-campaign-audit-v1' and report['status']=='VERIFIED_PASS' and report['scope']=='HISTORY_AGGREGATE_AND_COMMITTED_UNIT_AUDIT_CONSISTENCY' and report['source_run_id']==metadata['run_id'] and report['request_sha256']==aggregate['request_sha256'] and report['financial_accepted'] is False and report['full_M3'] is False)
        hist=report['history_audit']['history'];check(hist['final_state_sha256']==metadata['source_state_sha256'] and all(hist[k]==metadata['source_'+k] for k in ('history_sha256','controls_sha256')))
        card_pin=report['scorecard_review'];check(card_pin['task_id']==report['scorecard_task_id'] and card_pin['payload_sha256']==report['scorecard_sha256'])
        if lane=='source':check(card_pin==ticket['reviews']['scorecard'])
        card,card_header,_,_=verified_review(storage,card_pin,**lanes[lane],deadline=deadline)
        check(card['kind']=='scorecard' and card_header['records']==[r for r in header['records'] if r['kind'] in ('campaign','frame')])
        check([r['artifact'] for r in header['records'] if r['kind']=='scorecard']==[card['artifact']])
        unit_native=_unit_dependencies(storage,source,report,deadline)
        authors=[a['native_execution'] for a in source['attempts'] if a.get('native_execution') is not None]
        card_native=[a['native_execution'] for a in card['attempts'] if a.get('native_execution') is not None]
        check(all(not same_process(n,old) for n in card_native for old in authors))
        prior=authors+card_native+unit_native
        aggregate_native=[a['native_execution'] for a in aggregate['attempts'] if a['native_execution'] is not None]
        check(all(not same_process(n,old) for n in aggregate_native for old in prior))
        all_dependencies.extend(prior+aggregate_native);indices.append(report['comparison_index']);_time(deadline)
    check(all(not same_process(n,old) for n in compare_native for old in all_dependencies))
    expected=compare_indices(*indices);expected.update(pair_sha256=ticket['pair_sha256'],source_run_id=p['source']['run_id'],wheel_run_id=p['wheel']['run_id'],aggregate_payloads={lane:ticket['reviews'][lane+'_aggregate']['payload_sha256'] for lane in ('source','wheel')})
    check(expected==payload);_time(deadline)
