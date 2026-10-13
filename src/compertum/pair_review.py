"""Compact pair-review evidence, rebuilt from two committed aggregate reviews."""
import json,re
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier,digest
from .clean_pair import read_pair
from .review_evidence import check,sha,successful_receipt,MIB
from .development_seals import validate_binding
from .runtime.campaign_environment import check_native
from .runtime.job_identity import same_process


def _artifact(a,owner,path,maximum):
    check(type(a) is dict and set(a)=={'artifact_id','task_id','path','size_bytes','sha256'})
    identifier(a['artifact_id']);digest(a['sha256'])
    check(a['task_id']==owner and a['path']==path and type(a['size_bytes']) is int and 0<a['size_bytes']<=maximum)


def validate_metadata(value,*,task,run,identity,seal,records):
    try:
        check(type(value) is dict and set(value)=={'schema','pair','pair_sha256','lanes'} and value['schema']=='synthetic-pair-review-metadata-v1')
        check(len(canonical(value))<=64*1024)
        p=read_pair(canonical(value['pair']),expected_sha256=value['pair_sha256'])
        check(p['source']['run_id']==run and canonical(p['runtime'])==canonical(identity))
        lanes=value['lanes'];check(type(lanes) is list and len(lanes)==2)
        expected=[];tasks={task,p['source']['run_id'],p['wheel']['run_id']};artifact_ids=set()
        for i,(lane,v) in enumerate(zip(('source','wheel'),lanes)):
            check(type(v) is dict and set(v)=={'lane','run_id','protocol_seal','input_artifact','clean_environment','source_state_sha256','source_history_sha256','source_controls_sha256','aggregate'})
            member=p[lane];check(v['lane']==lane and v['run_id']==member['run_id'])
            validate_binding(v['protocol_seal']);check(v['protocol_seal']['seal_id']==member['seal_id'])
            if lane=='source':check(canonical(v['protocol_seal'])==canonical(seal))
            expected_environment=dict(schema='expected-clean-campaign-v1',pair_sha256=value['pair_sha256'],manifest_sha256=member['manifest_sha256'],lane=lane,run_id=member['run_id'])
            check(canonical(v['clean_environment'])==canonical(expected_environment))
            for k in ('source_state_sha256','source_history_sha256','source_controls_sha256'):digest(v[k])
            _artifact(v['input_artifact'],member['run_id'],f"artifacts/runs/{member['run_id']}/baseline/inputs.json",20*MIB)
            a=v['aggregate'];check(type(a) is dict and set(a)=={'task_id','request_sha256','artifact','payload_sha256','payload_bytes','native_execution','job_receipt','history_sha256'})
            identifier(a['task_id']);check(a['task_id'] not in tasks);tasks.add(a['task_id'])
            for k in ('request_sha256','payload_sha256','history_sha256'):digest(a[k])
            check(type(a['payload_bytes']) is int and 0<a['payload_bytes']<16*MIB)
            path=a['artifact']['path'];check(path in [f"artifacts/runs/{a['task_id']}/review/aggregate-attempt-{n}.review" for n in (1,2)])
            _artifact(a['artifact'],a['task_id'],path,16*MIB);check(a['payload_bytes']<a['artifact']['size_bytes'])
            for artifact in (v['input_artifact'],a['artifact']):
                check(artifact['artifact_id'] not in artifact_ids);artifact_ids.add(artifact['artifact_id'])
            n=a['native_execution'];check_native(n,expected_environment)
            check(n['task_id']==a['task_id'] and n['role']=='experiment_auditor' and n['code_sha256']==identity['package_sha256'] and n['lock_sha256']==identity['lock_sha256'])
            check(successful_receipt(a['job_receipt'],n))
            if lane=='source':expected.append(dict(kind='campaign',index=None,artifact=v['input_artifact']))
            expected.append(dict(kind='aggregate',index=i,artifact=a['artifact']))
        check(not same_process(lanes[0]['aggregate']['native_execution'],lanes[1]['aggregate']['native_execution']))
        check(canonical(records)==canonical(expected))
        return value
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError):
        raise DataError('PAIR_REVIEW_UNVERIFIED') from None


def registration(reviews,task,run):
    """Revalidate lanes sequentially; never retain both complete source histories."""
    from .clean_registration import member_registration
    from .review_bundle import build_bundle
    with reviews.store._live() as guard:
        member=member_registration(reviews.store.conn,guard.project,run,kind='run_id')
        check(member is not None and member[1]=='source');pair,_=member;p=read_pair(pair.content,expected_sha256=pair.sha256)
        lanes=[];native=[];source=None
        for lane in ('source','wheel'):
            lane_run=p[lane]['run_id']
            rows=reviews.store.conn.execute("SELECT task_id FROM campaign_reviews WHERE source_run_id=? AND kind='aggregate' LIMIT 2",(lane_run,)).fetchall();check(len(rows)==1)
            aggregate=reviews.completed(rows[0][0])
            context=reviews._registration('aggregate',aggregate['task_id'],lane_run);s=context['source'];meta=json.loads(context['metadata'])
            check(s['clean_environment']['pair_sha256']==pair.sha256 and s['clean_environment']['lane']==lane)
            history=[dict(seq=n,body=b,sha256=h,previous_sha256=prev) for n,b,h,prev in reviews.store.conn.execute('SELECT seq,body,sha256,previous_sha256 FROM campaign_review_history WHERE task_id=? ORDER BY seq LIMIT 33',(aggregate['task_id'],))]
            attempt=aggregate['attempts'][-1]
            lanes.append(dict(lane=lane,run_id=lane_run,protocol_seal=s['protocol_seal'],input_artifact=s['input_artifact'],clean_environment=s['clean_environment'],
                source_state_sha256=sha(meta['final_state'].encode()),source_history_sha256=sha(canonical(meta['history'])),source_controls_sha256=sha(canonical(meta['controls'])),
                aggregate=dict(task_id=aggregate['task_id'],request_sha256=aggregate['request_sha256'],artifact=aggregate['artifact'],payload_sha256=aggregate['payload_sha256'],payload_bytes=aggregate['payload_bytes'],native_execution=attempt['native_execution'],job_receipt=attempt['job_receipt'],history_sha256=sha(canonical(history)))))
            native.extend(a['native_execution'] for a in s['attempts']+aggregate['attempts'] if a.get('native_execution') is not None);native.extend(context['native'])
            if lane=='source':source={k:s[k] for k in ('run_id','identity','protocol_seal','clean_environment','input_artifact')}
            del context,s,meta,history,aggregate
        metadata=canonical(dict(schema='synthetic-pair-review-metadata-v1',pair=p,pair_sha256=pair.sha256,lanes=lanes))
        records=[dict(kind='campaign',index=None,artifact=source['input_artifact'])]+[dict(kind='aggregate',index=i,artifact=v['aggregate']['artifact']) for i,v in enumerate(lanes)]
        raw=build_bundle(kind='pair_compare',task_id=task,source_run_id=run,identity=source['identity'],protocol_seal=source['protocol_seal'],metadata=metadata,records=records)
        return dict(source=source,metadata=metadata,records=records,exports=[],plan=[],registration_sha256=sha(raw),raw=raw,native=native)
