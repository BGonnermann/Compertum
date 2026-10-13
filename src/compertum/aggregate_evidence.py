"""Bounded aggregate evidence; coordinator verifies origins, worker checks contents."""
import json
from .data.encoding import canonical
from .evaluation_protocol import identifier
from .audit_history import reconstruct,validate_state
from .runtime.campaign_environment import check_native,check_attempt_environments
from .review_evidence import check,sha,published,successful_receipt,MIB


def expected_unit_request(source,unit):
    check(type(unit) is int and 0<=unit<63)
    outcomes={o['unit']:o for o in source['outcomes'].values()}
    result=outcomes[unit];u=result['identity']
    check(result['status']=='COMPLETED' and u['phase']=='evaluate')
    def author(index):
        selected=[a for a in source['attempts'] if a['unit']==index and a['status']=='COMPLETED'];check(len(selected)==1)
        a=selected[0];check(successful_receipt(a['job_receipt'],a['native_execution']));check_native(a['native_execution'],source.get('clean_environment'));return a['native_execution']
    fit=outcomes[u['fit_unit']] if u['fit_unit'] is not None else None
    check(fit is None or fit['status']=='COMPLETED')
    return dict(schema='native-unit-audit-request-v1',source_run_id=source['run_id'],source_state=source['state'],source_history_sha256=sha(canonical(source)),unit=unit,candidate_id=u['candidate_id'],year=u['year'],
        input_artifact=source['input_artifact'],result=result,fit=fit,author_execution=author(unit),fit_execution=author(u['fit_unit']) if fit else None,identity=source['identity'],protocol_seal=source['protocol_seal'])


def bind_unit_audit(state,source):
    validate_state(state);check(source['state']=='COMPLETED' and state['state']=='COMPLETED' and state['task_id']!=source['run_id'])
    check_attempt_environments(state['attempts'],source.get('clean_environment'))
    request=expected_unit_request(source,state['request']['unit']);check(canonical(request)==canonical(state['request']))
    attempt=state['attempts'][-1];task=attempt['task'];native=attempt['native_execution'];artifact=state['artifact']
    artifacts=[request['input_artifact'],request['result']['artifact']]+([request['fit']['artifact']] if request['fit'] else [])
    check(task['task_id']==state['task_id'] and task['role']=='experiment_auditor' and task['parent_task_id']==source['run_id'] and task['campaign_id']==source['run_id'])
    check(task['input_hashes']==[a['sha256'] for a in artifacts] and task['permissions']['filesystem_bundle']==[a['path'] for a in artifacts])
    check(task['permissions']['output_directory']==f"artifacts/runs/{state['task_id']}/audit")
    b=task['budget'];check(b['wall_seconds']==120 and b['cpu_threads']==4 and b['ram_bytes']==4*1024**3 and b['output_bytes']==16*MIB and b['max_attempts']==2)
    check(successful_receipt(attempt['job_receipt'],native) and artifact['task_id']==state['task_id'] and artifact['path']==attempt['output_path'])
    return dict(kind='unit_audit',index=request['unit'],artifact=artifact)


def collect_units(storage,source):
    needed={o['unit'] for o in source['outcomes'].values() if o['status']=='COMPLETED' and o['identity']['phase']=='evaluate'}
    db=storage.store.conn
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_runs'").fetchone():check(not needed);return [],[]
    rows=db.execute("SELECT task_id,body FROM audit_runs WHERE json_extract(body,'$.request.source_run_id')=? LIMIT 37",(source['run_id'],)).fetchall();check(len(rows)<=36)
    evidence=[];records=[];seen=set()
    for task,body in rows:
        history=[dict(seq=n,body=b,sha256=h,previous_sha256=p) for n,b,h,p in db.execute('SELECT seq,body,sha256,previous_sha256 FROM audit_history WHERE task_id=? ORDER BY seq LIMIT 33',(task,))]
        state=reconstruct(body.encode(),history);check(state['task_id']==task and state['request']['unit'] not in seen);seen.add(state['request']['unit'])
        record=bind_unit_audit(state,source);published(storage,record['artifact'],16*MIB)
        reservation=db.execute('SELECT status,manifest FROM reservations WHERE id=?',(state['attempts'][-1]['reservation_id'],)).fetchone()
        check(reservation is not None and reservation[0]=='PUBLISHED' and canonical(json.loads(reservation[1]))==canonical(record['artifact']))
        evidence.append(dict(state=state,history=history));records.append(record)
    check(seen==needed)
    return sorted(evidence,key=lambda e:e['state']['request']['unit']),sorted(records,key=lambda r:r['index'])


def encode_exports(scorecard,units):
    check(type(scorecard) is dict and type(units) is list and len(units)<=36)
    check(all(type(e) is dict and set(e)=={'state','history'} and type(e['state']) is dict and type(e['history']) is list for e in units))
    indices=[e['state']['request']['unit'] for e in units]
    check(all(type(i) is int and 0<=i<63 and i%21 not in range(3,21,2) for i in indices) and indices==sorted(set(indices)))
    values=[dict(schema='synthetic-native-audit-evidence-v1',index=0,scorecard=scorecard,unit_audits=[])]
    for entry in units:
        candidate=dict(values[-1]);candidate['unit_audits']=[*candidate['unit_audits'],entry]
        if len(canonical(candidate))>16*MIB:
            check(len(values)==1)
            candidate=dict(schema='synthetic-native-audit-evidence-v1',index=1,scorecard=None,unit_audits=[entry]);values.append(candidate)
        else:values[-1]=candidate
        check(len(canonical(values[-1]))<=16*MIB)
    result=[canonical(v) for v in values];check(all(0<len(raw)<=16*MIB for raw in result));return result


def decode_exports(raws):
    check(type(raws) is list and 1<=len(raws)<=2);units=[];scorecard=None
    for index,raw in enumerate(raws):
        check(type(raw) is bytes and 0<len(raw)<=16*MIB);v=json.loads(raw)
        check(canonical(v)==raw and set(v)=={'schema','index','scorecard','unit_audits'} and v['schema']=='synthetic-native-audit-evidence-v1' and type(v['index']) is int and v['index']==index)
        check(type(v['unit_audits']) is list and len(v['unit_audits'])<=36)
        if index==0:check(type(v['scorecard']) is dict);scorecard=v['scorecard']
        else:check(v['scorecard'] is None and v['unit_audits'])
        units.extend(v['unit_audits'])
    check(len(units)<=36 and encode_exports(scorecard,units)==raws)
    return scorecard,units


def export_plan(task,exports):
    identifier(task);decode_exports(exports)
    return [dict(role='audit_history',index=i,path=f'artifacts/runs/{task}/review/input/unit-audits-{i}.json',sha256=sha(raw),size_bytes=len(raw)) for i,raw in enumerate(exports)]
