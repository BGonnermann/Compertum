"""Lightweight coordinator observations for immutable native review evidence."""
import hashlib,json,os
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier
from .clean_registration import _text
from .development_seals import check_campaign_seal
from .persistence import checked_path
from .runtime.job_identity import validate_execution_identity
from .runtime.campaign_environment import check_native

MIB=1024**2


def check(value):
    if not value:raise DataError('REVIEW_EVIDENCE_UNVERIFIED')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def successful_receipt(receipt,native):
    validate_execution_identity(native)
    ints={'pid','exit_code','active_processes','affinity','memory_limit','peak_job_memory'}
    bools={'timed_out','assigned_before_resume','observed_children_exited'}
    check(type(receipt) is dict and set(receipt)==ints|bools|{'observed_child_pids','execution_identity'})
    check(all(type(receipt[k]) is int and 0<=receipt[k]<2**64 for k in ints) and all(type(receipt[k]) is bool for k in bools))
    check(canonical(receipt['execution_identity'])==canonical(native) and receipt['pid']==native['process']['pid'])
    children=receipt['observed_child_pids'];check(type(children) is list and len(children)<=3 and all(type(p) is int and 0<p<2**32 for p in children))
    return (receipt['exit_code']==0 and not receipt['timed_out'] and receipt['active_processes']==0 and receipt['assigned_before_resume']
        and receipt['observed_children_exited'] and receipt['memory_limit']==4*1024**3 and 0<receipt['peak_job_memory']<=4*1024**3
        and 0<receipt['affinity'].bit_count()<=4)


def published(storage,artifact,maximum,*,read=False):
    check(type(artifact) is dict and set(artifact)=={'artifact_id','task_id','path','size_bytes','sha256'})
    identifier(artifact['artifact_id']);identifier(artifact['task_id'])
    check(type(artifact['size_bytes']) is int and 0<artifact['size_bytes']<=maximum)
    rows=storage.store.conn.execute("SELECT "+_text('manifest',4096)+" FROM reservations WHERE task=? AND path=? AND status='PUBLISHED' LIMIT 2",(artifact['task_id'],artifact['path'])).fetchall()
    check(len(rows)==1 and type(rows[0][0]) is str and canonical(json.loads(rows[0][0]))==canonical(artifact))
    path=checked_path(storage.root,storage.root/artifact['path']);digest=hashlib.sha256();chunks=[];left=artifact['size_bytes']
    with path.open('rb') as stream:
        check(os.fstat(stream.fileno()).st_size==left)
        while left:
            chunk=stream.read(min(MIB,left));check(0<len(chunk)<=left);digest.update(chunk);left-=len(chunk)
            if read:chunks.append(chunk)
        check(stream.read(1)==b'')
    check(digest.hexdigest()==artifact['sha256'])
    return b''.join(chunks) if read else None


def source_snapshot(storage,run):
    """Pin all history/control rows and stream source hashes, never model payloads."""
    identifier(run);store=storage.store
    row=store.conn.execute('SELECT body FROM baseline_runs WHERE run_id=?',(run,)).fetchone()
    check(row is not None and len(row[0].encode())<=512*1024);raw=row[0].encode();state=json.loads(raw)
    check(canonical(state)==raw and state['run_id']==run and state['state']=='COMPLETED' and state['input_kind']=='synthetic-campaign')
    seal=check_campaign_seal(store,state);check(seal is not None)
    outcomes=state['outcomes'];check(type(outcomes) is dict and len(outcomes)==63 and sorted(o['unit'] for o in outcomes.values())==list(range(63)))
    history=[dict(seq=s,body=b,sha256=h) for s,b,h in store.conn.execute('SELECT seq,body,sha256 FROM baseline_history WHERE run_id=? ORDER BY seq LIMIT 1025',(run,))]
    controls=[dict(request_id=r,action=a,receipt=c) for r,a,c in store.conn.execute('SELECT request_id,action,receipt FROM baseline_controls WHERE run_id=? ORDER BY request_id LIMIT 129',(run,))]
    check(0<len(history)<=1024 and len(controls)<=128 and [r['seq'] for r in history]==list(range(1,len(history)+1)) and history[-1]['sha256']==sha(raw))
    check(all(len(r['body'].encode())<=512*1024 for r in history) and sum(len(canonical(r)) for r in history)<=16*MIB)
    primary=state['input_artifact'];published(storage,primary,20*MIB)
    check(primary['sha256']==state['request_sha256'])
    records=[dict(kind='campaign',index=None,artifact=primary)]
    for o in sorted(outcomes.values(),key=lambda o:o['unit']):
        if o['status']!='COMPLETED':continue
        matches=[a for a in state['attempts'] if a['unit']==o['unit'] and a['status']=='COMPLETED'];check(len(matches)==1)
        a=matches[0];n=a.get('native_execution');validate_execution_identity(n);check_native(n,state.get('clean_environment'))
        check(n['role']=='experiment_runner' and n['task_id']==run and n['code_sha256']==state['identity']['package_sha256'] and n['lock_sha256']==state['identity']['lock_sha256'])
        check('job_receipt' in a and successful_receipt(a['job_receipt'],n))
        check(a['output_path']==o['artifact']['path']);published(storage,o['artifact'],16*MIB)
        records.append(dict(kind='frame',index=o['unit'],artifact=o['artifact']))
    check(sum(r['artifact']['size_bytes'] for r in records)<=state['maximum_bytes']<=128*MIB)
    return state,canonical(dict(final_state=raw.decode(),history=history,controls=controls)),records
