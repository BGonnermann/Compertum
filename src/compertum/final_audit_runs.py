"""Coordinator-owned independent Final audit: immutable inputs and at most two Jobs."""
from copy import deepcopy
from datetime import datetime,timezone
import io,json,os
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier
from .clean_registration import _text
from .completed_final_evidence import completed_final
from .environment_manifest import read_manifest
from .final_audit_request import artifact,build_request,read_request
from .final_audit_task import build_task,validate_task,inspect_recorded_task
from .final_audit_history import check,validate_state,transition,reconstruct,closed_receipt,validate_unbound,MAXIMUM
from .review_evidence import published,sha,successful_receipt
from .review_frame import result_binding,verify_review
from .runtime.auditor_environment import expected_from_manifest,observed_from_native
from .runtime.identity_pins import runtime_identity
from .runtime.job_identity import validate_execution_identity,same_process
from .runtime.startup_record import expected_proof
from .runtime.owners import require_live_owner
from .persistence import checked_path

MIB=1024**2


def _key(evaluation,runtime,lane):return sha(canonical(dict(evaluation_id=evaluation,runtime=runtime,lane=lane)))
def _now():return datetime.now(timezone.utc).isoformat()
def summary(s):return dict(task_id=s['task_id'],seal_id=s['seal_id'],evaluation_id=s['evaluation_id'],state=s['state'],attempt_count=len(s['attempts']),reason=s['attempts'][-1]['reason'] if s['attempts'] else None,artifact=s['artifact'],audit_sha256=s['audit_sha256'],financial_accepted=False,full_M3=False)


class FinalAuditRuns:
    def __init__(self,storage):
        self.storage=storage;self.store=storage.store;self.owner=storage.lease.identity.process_instance_id
        with self.store._live(),self.store.conn:
            require_live_owner(storage.lease,'coordinator')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS final_audit_runs(task_id TEXT PRIMARY KEY,audit_key TEXT NOT NULL UNIQUE,body TEXT NOT NULL)')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS final_audit_history(task_id TEXT NOT NULL,seq INTEGER NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL,previous_sha256 TEXT,PRIMARY KEY(task_id,seq))')
            rows=self.store.conn.execute('SELECT task_id FROM final_audit_runs LIMIT 65').fetchall();check(len(rows)<=64)
            for (task,) in rows:
                s=self._load(task)
                if s['owner']!=self.owner and s['state'] in ('PREPARED','RUNNING') and s['attempts'][-1]['job_receipt'] is None:
                    s['attempts'][-1].update(status='EXIT_UNVERIFIED',reason='OWNER_RESTART');s['state']='EXIT_UNVERIFIED';self._save(s,'OWNER_RESTART')

    def _load(self,task):
        return _read_state(self.store,task)

    def _save(self,s,reason):
        s.update(updated_at=_now(),last_transition=reason);validate_state(s)
        exists=self.store.conn.execute('SELECT 1 FROM final_audit_runs WHERE task_id=?',(s['task_id'],)).fetchone()
        before=self._load(s['task_id']) if exists else None;transition(before,s)
        prior=self.store.conn.execute('SELECT seq,sha256 FROM final_audit_history WHERE task_id=? ORDER BY seq DESC LIMIT 1',(s['task_id'],)).fetchone();n=prior[0]+1 if prior else 1;check(n<=32)
        raw=canonical(s);key=_key(s['evaluation_id'],s['auditor_runtime'],s['auditor_environment']['lane'])
        self.store.conn.execute('INSERT INTO final_audit_runs VALUES(?,?,?) ON CONFLICT(task_id) DO UPDATE SET body=excluded.body',(s['task_id'],key,raw.decode()))
        self.store.conn.execute('INSERT INTO final_audit_history VALUES(?,?,?,?,?)',(s['task_id'],n,raw.decode(),sha(raw),prior[1] if prior else None))

    def _publish(self,task,path,raw):
        # Fixed names deliberately refuse existing/orphaned publications.
        grant=self.storage.reserve_bytes(task,'records',len(raw));writer=self.storage.open_artifact(grant,path)
        try:writer.write(raw);return writer.publish()
        finally:writer.close()

    def publish_manifest(self,task,raw):
        """Private owner preparation; not a public control accepting caller bytes."""
        identifier(task)
        with self.store._live():
            value=read_manifest(raw,expected_sha256=sha(raw));check(canonical(value['runtime'])==canonical(runtime_identity()))
            return self._publish(task,f'artifacts/runs/{task}/final_audit/input/environment.json',raw)

    def _manifest(self,task,reference):
        identifier(task);identifier(reference)
        rows=self.store.conn.execute("SELECT "+_text('manifest',4096)+" FROM reservations WHERE task=? AND path=? AND status='PUBLISHED' LIMIT 2",(task,f'artifacts/runs/{task}/final_audit/input/environment.json')).fetchall()
        check(len(rows)==1 and type(rows[0][0]) is str);a=json.loads(rows[0][0]);artifact(a,4*MIB);check(a['artifact_id']==reference)
        raw=published(self.storage,a,4*MIB,read=True);v=read_manifest(raw,expected_sha256=a['sha256']);return a,raw,v

    def register(self,task,seal,manifest_reference):
        identifier(task);identifier(seal)
        with self.store._live():
            original=completed_final(self.storage,seal);check(task not in (original['evaluation_id'],original['source_artifact']['task_id']))
            a,raw,v=self._manifest(task,manifest_reference);check(canonical(v['runtime'])==canonical(runtime_identity()))
            expected=expected_from_manifest(raw,a['sha256'],task);key=_key(original['evaluation_id'],v['runtime'],v['lane'])
            matches=self.store.conn.execute('SELECT task_id FROM final_audit_runs WHERE audit_key=?',(key,)).fetchall();check(not matches or matches==[(task,)])
            if self.store.conn.execute('SELECT 1 FROM final_audit_runs WHERE task_id=?',(task,)).fetchone():
                s=self._load(task);check(s['seal_id']==seal and s['original_sha256']==sha(canonical(original)) and s['manifest']==a and s['auditor_environment']==expected and canonical(s['auditor_runtime'])==canonical(v['runtime']))
                return self.completed(task) if s['state']=='COMPLETED' else s
            check(self.store.conn.execute('SELECT count(*) FROM final_audit_runs').fetchone()[0]<64)
            s=dict(schema='consumed-final-audit-state-v1',task_id=task,seal_id=seal,evaluation_id=original['evaluation_id'],original_sha256=sha(canonical(original)),manifest=a,auditor_environment=expected,auditor_runtime=v['runtime'],owner=self.owner,state='READY',attempts=[],artifact=None,audit_sha256=None,financial_accepted=False,full_M3=False)
            with self.store.conn:self._save(s,'REGISTERED')
            return s

    def current(self,s):
        original=completed_final(self.storage,s['seal_id']);check(sha(canonical(original))==s['original_sha256'] and original['evaluation_id']==s['evaluation_id'])
        a,raw,v=self._manifest(s['task_id'],s['manifest']['artifact_id']);check(a==s['manifest'] and expected_from_manifest(raw,a['sha256'],s['task_id'])==s['auditor_environment'] and canonical(v['runtime'])==canonical(s['auditor_runtime']))
        for attempt in s['attempts']:
            if attempt['native_execution'] is not None:check(not same_process(attempt['native_execution'],original['author']))
        return original,raw

    def status(self,task):
        with self.store._live():return self._load(task)

    def records(self):
        with self.store._live():
            rows=self.store.conn.execute('SELECT task_id FROM final_audit_runs ORDER BY task_id LIMIT 65').fetchall();check(len(rows)<=64)
            return [summary(self._load(t)) for (t,) in rows]

    def barrier(self):
        require_closed_audits(self.store,self.owner)

    def record_unbound(self,prepared,proof):
        with self.store._live(),self.store.conn:
            s=self._load(prepared['task_id']);a=s['attempts'][-1]
            check(s['owner']==self.owner and s['state'] in ('PREPARED','EXIT_UNVERIFIED') and a['native_execution'] is None)
            check(prepared==dict(task_id=s['task_id'],**{k:a[k] for k in ('number','request_artifact','task_artifact','reservation_id','output_path')}))
            validate_unbound(proof,s['task_id'],a)
            a.update(status='BLOCKED',reason='LAUNCH_FAILED',closed_unbound=deepcopy(proof));s['state']='BLOCKED';self._save(s,'UNBOUND_CLOSED');return s

    def prepare(self,task,*,now):
        with self.store._live():
            self.barrier();s=self._load(task);check(s['state']=='READY' and len(s['attempts'])<2)
            original,manifest_raw=self.current(s);check(canonical(runtime_identity())==canonical(s['auditor_runtime']))
            n=len(s['attempts'])+1;raw=build_request(task,n,original,s['manifest'],manifest_raw)
            a=self._publish(task,f'artifacts/runs/{task}/final_audit/input/attempt-{n:02}.json',raw)
            spec=build_task(self.storage.root,raw,a,now=now);payload=spec.to_payload();ta=self._publish(task,f'artifacts/runs/{task}/final_audit/input/task-attempt-{n:02}.json',canonical(payload))
            grant=self.storage.reserve_bytes(task,'records',2*MIB);path=f'artifacts/runs/{task}/final_audit/attempt-{n:02}.audit';writer=self.storage.open_artifact(grant,path)
            try:
                attempt=dict(number=n,status='PREPARED',request_artifact=a,task_artifact=ta,reservation_id=grant.grant_id,output_path=path,native_execution=None,job_receipt=None,exit_observation=None,closed_unbound=None,started_at=payload['created_at'],reason=None)
                s['attempts'].append(attempt);s.update(state='PREPARED',owner=self.owner)
                with self.store.conn:self._save(s,'PREPARED')
                return dict(task_id=task,number=n,request_artifact=a,task_artifact=ta,reservation_id=grant.grant_id,output_path=path),spec,writer
            except BaseException:writer.close();raise

    def verify_launch(self,prepared,payload,reservation_id,*,execution_identity=None):
        with self.store._live():
            s=self._load(prepared['task_id']);original,_=self.current(s);a=s['attempts'][-1]
            check(s['owner']==self.owner and prepared==dict(task_id=s['task_id'],**{k:a[k] for k in ('number','request_artifact','task_artifact','reservation_id','output_path')}) and reservation_id==a['reservation_id'])
            raw=published(self.storage,a['request_artifact'],65536,read=True);request=read_request(raw,expected_sha256=a['request_artifact']['sha256'])
            check(canonical(request['original'])==canonical(original) and request['attempt']==a['number'] and request['manifest_artifact']==s['manifest'] and canonical(request['auditor_runtime'])==canonical(s['auditor_runtime']))
            traw=published(self.storage,a['task_artifact'],65536,read=True);check(canonical(payload)==traw);validate_task(self.storage.root,payload,raw,a['request_artifact'])
            row=self.store.conn.execute('SELECT task,path,status,maximum FROM reservations WHERE id=?',(reservation_id,)).fetchone()
            check(row is not None and row[0]==s['task_id'] and row[1].replace('\\','/')==a['output_path']+'.partial-'+reservation_id and row[2]=='OPEN' and type(row[3]) is int and row[3]==2*MIB)
            if execution_identity is None:check(s['state']=='PREPARED' and a['native_execution'] is None)
            else:check(s['state']=='RUNNING' and a['native_execution']==execution_identity)
            return s,[a['request_artifact'],original['frame'],s['manifest']]

    def bind_native(self,prepared,native):
        # Called immediately after observation, before fallible full pre-resume checks.
        with self.store._live(),self.store.conn:
            s=self._load(prepared['task_id']);a=s['attempts'][-1];check(s['state']=='PREPARED' and s['owner']==self.owner and a['number']==prepared['number'] and a['reservation_id']==prepared['reservation_id'])
            validate_execution_identity(native);a.update(native_execution=native,status='RUNNING');s['state']='RUNNING';self._save(s,'NATIVE_BOUND')

    def uncertain(self,task,cause):
        with self.store._live(),self.store.conn:
            s=self._load(task)
            if s['state']=='EXIT_UNVERIFIED':return s
            check(s['state'] in ('PREPARED','RUNNING') and s['owner']==self.owner and s['attempts'][-1]['job_receipt'] is None)
            s['attempts'][-1].update(status='EXIT_UNVERIFIED',reason=cause);s['state']='EXIT_UNVERIFIED';self._save(s,'EXIT_UNVERIFIED');return s

    def record_exit(self,task,receipt):
        with self.store._live(),self.store.conn:
            s=self._load(task);a=s['attempts'][-1];check(s['owner']==self.owner and s['state'] in ('RUNNING','EXIT_UNVERIFIED'))
            closed_receipt(receipt,a['native_execution'])
            if a['job_receipt'] is not None:check(a['job_receipt']==receipt);return s
            a.update(job_receipt=deepcopy(receipt),status='RUNNING',reason=None);s['state']='RUNNING';self._save(s,'EXIT_RECORDED');return s

    def interrupt(self,task,cause,*,stop=False):
        with self.store._live(),self.store.conn:
            s=self._load(task);a=s['attempts'][-1];check(s['state']=='RUNNING');r=a['job_receipt'];closed_receipt(r,a['native_execution'])
            terminal=not r['timed_out'] and r['exit_code'] not in (0,5,125)
            if terminal:state='FAILED' if r['exit_code']==4 else 'BLOCKED';cause='AUDIT_REJECTED' if state=='FAILED' else 'AUDIT_INTEGRITY_FAILURE'
            elif cause in ('AUDIT_INTEGRITY_FAILURE','PUBLICATION_FAILED','BOOKKEEPING_FAILED','LAUNCH_FAILED'):state='BLOCKED'
            elif stop:state='STOPPED';cause='OPERATOR_STOP'
            else:state='INTERRUPTED' if len(s['attempts'])<2 else 'FAILED'
            a.update(status=state,reason=cause);s['state']=state;self._save(s,state);return s

    def stop_idle(self,task):
        with self.store._live(),self.store.conn:
            self.barrier();s=self._load(task)
            if s['state'] in ('STOPPED','COMPLETED','FAILED','BLOCKED'):return s
            check(s['state'] in ('READY','INTERRUPTED'))
            if s['attempts']:s['attempts'][-1].update(status='STOPPED',reason='OPERATOR_STOP')
            s.update(state='STOPPED',owner=self.owner);self._save(s,'CANCELLED');return s

    def resume(self,task):
        with self.store._live(),self.store.conn:
            self.barrier();s=self._load(task);self.current(s);check(s['state']=='INTERRUPTED' and len(s['attempts'])==1)
            s.update(state='READY',owner=self.owner);self._save(s,'RESUMED');return s

    def recover_exit(self,task):
        from .final_completion import observe_exited
        with self.store._live(),self.store.conn:
            s=self._load(task);check(s['state']=='EXIT_UNVERIFIED');a=s['attempts'][-1];check(a['native_execution'] is not None)
            # Single-process Job enforced by launcher. Root disappearance proves closure only.
            proof=observe_exited(a['native_execution']);a.update(status='BLOCKED',exit_observation=proof);s['state']='BLOCKED';self._save(s,'EXIT_OBSERVED');return s

    def inspect_output(self,s,raw):
        a=s['attempts'][-1];check(successful_receipt(a['job_receipt'],a['native_execution']))
        request_raw=published(self.storage,a['request_artifact'],65536,read=True)
        task_raw=published(self.storage,a['task_artifact'],65536,read=True)
        return inspect_output(s,raw,request_raw,task_raw,self.storage.root)

    def _output(self,s,a):
        attempt=s['attempts'][-1];artifact(a,2*MIB);check(a['task_id']==s['task_id'] and a['path']==attempt['output_path'])
        row=self.store.conn.execute("SELECT category,maximum,written,status,"+_text('manifest',4096)+" FROM reservations WHERE id=? AND task=? AND path=?",(attempt['reservation_id'],s['task_id'],a['path'])).fetchone()
        check(row is not None and row[:4]==('records',2*MIB,a['size_bytes'],'PUBLISHED') and type(row[1]) is type(row[2]) is int and json.loads(row[4])==a)
        raw=published(self.storage,a,2*MIB,read=True);return self.inspect_output(s,raw)[1]

    def accept(self,task,a):
        with self.store._live(),self.store.conn:
            s=self._load(task);check(s['state']=='RUNNING');self.current(s);v=self._output(s,a)
            s['attempts'][-1].update(status='COMPLETED',reason=None);s.update(state='COMPLETED',artifact=a,audit_sha256=v['audit_sha256']);self._save(s,'COMPLETED');return s

    def completed(self,task):
        with self.store._live():
            s=self._load(task);check(s['state']=='COMPLETED');self.current(s);v=self._output(s,s['artifact']);check(v['audit_sha256']==s['audit_sha256']);return s


def _read_state(store,task):
    identifier(task)
    row=store.conn.execute('SELECT '+_text('body',MAXIMUM)+','+_text('audit_key',64)+' FROM final_audit_runs WHERE task_id=?',(task,)).fetchone();check(row is not None and type(row[0]) is str)
    records=[dict(seq=n,body=b,sha256=h,previous_sha256=p) for n,b,h,p in store.conn.execute('SELECT seq,'+_text('body',MAXIMUM)+','+_text('sha256',64)+','+_text('previous_sha256',64)+' FROM final_audit_history WHERE task_id=? ORDER BY seq LIMIT 33',(task,))]
    s=reconstruct(row[0].encode(),records);check(s['task_id']==task and row[1]==_key(s['evaluation_id'],s['auditor_runtime'],s['auditor_environment']['lane']));return s


def require_closed_audits(store,owner,prepared=None):
    """All worker modes honor unresolved audit ownership across owner restarts."""
    with store._live():
        if not store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='final_audit_runs'").fetchone():return
        rows=store.conn.execute('SELECT task_id FROM final_audit_runs LIMIT 65').fetchall();check(len(rows)<=64)
        for (task,) in rows:
            s=_read_state(store,task)
            for a in s['attempts']:
                if a['job_receipt'] is not None or a['exit_observation'] is not None or a['closed_unbound'] is not None:continue
                check(prepared is not None and a is s['attempts'][-1] and s['state']=='PREPARED' and s['owner']==owner and prepared==dict(task_id=task,**{k:a[k] for k in ('number','request_artifact','task_artifact','reservation_id','output_path')}))


def inspect_output(s,raw,request_raw,task_raw,root):
    a=s['attempts'][-1];n=a['native_execution'];check(successful_receipt(a['job_receipt'],n))
    b=result_binding('final_audit',s['task_id'],s['evaluation_id'],a['request_artifact']['sha256'],s['auditor_runtime'],n['process']['pid'],startup=expected_proof(n),auditor_environment=observed_from_native(n))
    proof=verify_review(io.BytesIO(raw),b,maximum=2*MIB);body=raw.split(b'\n',1)[1];v=json.loads(body)
    check(canonical(v)==body and set(v)=={'schema','original_evidence_sha256','audit_sha256','audit','financial_accepted','full_M3'} and v['schema']=='consumed-final-independent-report-v1')
    check(v['original_evidence_sha256']==s['original_sha256'] and v['audit_sha256']==sha(canonical(v['audit'])) and v['financial_accepted'] is False and v['full_M3'] is False)
    request=read_request(request_raw,expected_sha256=a['request_artifact']['sha256']);old=request['original'];report=v['audit']
    task=json.loads(task_raw)
    check(canonical(task)==task_raw and sha(task_raw)==n['task_sha256'] and sha(canonical(old))==s['original_sha256'] and request['manifest_artifact']==s['manifest'] and canonical(request['auditor_runtime'])==canonical(s['auditor_runtime']))
    inspect_recorded_task(root,task,request_raw,a['request_artifact'])
    check(report['schema']=='generated-final-independent-audit-v1' and report['status']=='VERIFIED_PASS' and report['evaluation_id']==s['evaluation_id'] and report['plan_sha256']==old['plan_sha256'] and report['payload_sha256']==old['payload_sha256'] and report['financial_accepted'] is False and report['full_M3'] is False)
    return proof,v
