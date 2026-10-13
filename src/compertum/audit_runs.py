"""Coordinator-owned native audit requests, attempts and immutable results.

This local trusted-template ledger is not a hostile same-user filesystem boundary.
"""
from datetime import datetime,timezone
import hashlib,json,os
from uuid import UUID
from .data.encoding import canonical
from .data.errors import DataError
from .persistence import checked_path
from .simulation.runs import SavedRuns
from .simulation.campaign_runs import history,validate_receipt
from .simulation.campaign_record import verify_result
from .runtime.startup_record import expected_proof,check_report
from .runtime.campaign_environment import check_native,observed_from_native
from .development_seals import expected_environment
from .campaign_contract import UNITS
from .runtime.job_identity import validate_execution_identity,same_process
from .development_seals import check_campaign_seal
from .audit_history import reconstruct,validate_state as validate_audit_state,transition as audit_transition,receipt_terminal

MIB=1024**2
FIELDS={'schema','task_id','role','worker_pid','unit','candidate_id','year','input_sha256','result_frame_sha256','result_payload_sha256','fit_frame_sha256','fit_payload_sha256','runtime_identity','audit_sha256','audit','native_authority','financial_accepted'}


def _check(value,code='AUDITOR_ADMISSION_UNVERIFIED'):
    if not value:raise DataError(code)


def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _hash(value):return _sha(canonical(value))
def _uuid(value):_check(type(value) is str and str(UUID(value))==value)


def successful_exit(receipt):
    validate_receipt(receipt)
    return (receipt['exit_code']==0 and receipt['timed_out'] is False and receipt['active_processes']==0
        and receipt['assigned_before_resume'] is True and receipt['observed_children_exited'] is True
        and receipt['memory_limit']==4*1024**3 and 0<receipt['peak_job_memory']<=4*1024**3
        and 0<receipt['affinity'].bit_count()<=4)


def source_request(runs,run_id,unit):
    _uuid(run_id);_check(type(unit) is int and 0<=unit<63 and UNITS[unit].phase=='evaluate')
    state=history(runs,run_id);_check(state['state'] in ('COMPLETED','STOPPED'))
    seal=check_campaign_seal(runs.store,state);_check(seal is not None,'AUDITOR_SEAL_REQUIRED')
    u=UNITS[unit]
    def committed(index):
        record=state['outcomes'].get(UNITS[index].key);_check(record is not None and record['status']=='COMPLETED')
        matches=[a for a in state['attempts'] if a['unit']==index and a['status']=='COMPLETED'];_check(len(matches)==1)
        a=matches[0];native=a.get('native_execution');_check(native is not None and 'job_receipt' in a,'AUDITOR_AUTHOR_UNVERIFIED')
        validate_execution_identity(native);check_native(native,state.get('clean_environment'));_check(native['role']=='experiment_runner' and native['task_id']==run_id and a['job_receipt'].get('execution_identity')==native and successful_exit(a['job_receipt']),'AUDITOR_AUTHOR_UNVERIFIED')
        row=runs.store.conn.execute("SELECT manifest FROM reservations WHERE task=? AND path=? AND status='PUBLISHED'",(run_id,record['artifact']['path'])).fetchone()
        _check(row is not None and json.loads(row[0])==record['artifact'])
        raw=runs._read(run_id,record['artifact'],16*MIB);body=verify_result(raw,state['request_sha256'],index,record['dependency_sha256'],expected_startup=expected_proof(native),expected_environment=observed_from_native(native))
        _check(_sha(body)==record['payload_sha256'])
        return record,native
    result,author=committed(unit);fit,fit_author=committed(u.fit_unit) if u.fit_unit is not None else (None,None)
    _check(result['dependency_sha256']==(fit['payload_sha256'] if fit else None))
    artifact=state['input_artifact'];raw=runs._read(run_id,artifact,20*MIB);_check(_sha(raw)==state['request_sha256'])
    row=runs.store.conn.execute("SELECT manifest FROM reservations WHERE task=? AND path=? AND status='PUBLISHED'",(run_id,artifact['path'])).fetchone()
    _check(row is not None and json.loads(row[0])==artifact)
    return dict(schema='native-unit-audit-request-v1',source_run_id=run_id,source_state=state['state'],source_history_sha256=_hash(state),unit=unit,candidate_id=u.candidate_id,year=u.year,
        input_artifact=artifact,result=result,fit=fit,author_execution=author,fit_execution=fit_author,identity=state['identity'],protocol_seal=seal)


class AuditRuns:
    def __init__(self,storage):
        self.storage=storage;self.store=storage.store;self.source=SavedRuns(storage);self.owner=storage.lease.identity.process_instance_id
        with self.store._live(),self.store.conn:
            self.store.conn.executescript('''CREATE TABLE IF NOT EXISTS audit_runs(task_id TEXT PRIMARY KEY,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit_history(task_id TEXT NOT NULL,seq INTEGER NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL,previous_sha256 TEXT,PRIMARY KEY(task_id,seq));
                CREATE TRIGGER IF NOT EXISTS audit_request_insert BEFORE INSERT ON audit_runs
                WHEN EXISTS(SELECT 1 FROM audit_runs WHERE task_id!=NEW.task_id
                    AND json_extract(body,'$.request.source_run_id')=json_extract(NEW.body,'$.request.source_run_id')
                    AND json_extract(body,'$.request.unit')=json_extract(NEW.body,'$.request.unit'))
                BEGIN SELECT RAISE(ABORT,'AUDITOR_REQUEST_CONFLICT'); END;
                CREATE TRIGGER IF NOT EXISTS audit_request_update BEFORE UPDATE OF body ON audit_runs
                WHEN EXISTS(SELECT 1 FROM audit_runs WHERE task_id!=NEW.task_id
                    AND json_extract(body,'$.request.source_run_id')=json_extract(NEW.body,'$.request.source_run_id')
                    AND json_extract(body,'$.request.unit')=json_extract(NEW.body,'$.request.unit'))
                BEGIN SELECT RAISE(ABORT,'AUDITOR_REQUEST_CONFLICT'); END;''')
            for (task,) in self.store.conn.execute('SELECT task_id FROM audit_runs').fetchall():
                s=self._load(task)
                if s['state']=='RUNNING' and s['owner']!=self.owner:
                    terminal=self._receipt_terminal(s['attempts'][-1].get('job_receipt'));exhausted=len(s['attempts'])==2
                    s['state']=terminal or ('FAILED' if exhausted else 'INTERRUPTED')
                    cause=('AUDIT_REJECTED' if terminal=='FAILED' else 'AUDIT_INTEGRITY_FAILURE') if terminal else ('TRANSIENT_ATTEMPTS_EXHAUSTED' if exhausted else 'OWNER_RESTART')
                    s['attempts'][-1].update(status=s['state'],reason=cause);self._save(s,'OWNER_RESTART')

    _receipt_terminal=staticmethod(receipt_terminal)

    def _load(self,task):
        _uuid(task);row=self.store.conn.execute('SELECT body FROM audit_runs WHERE task_id=?',(task,)).fetchone();_check(row is not None,'AUDITOR_NOT_FOUND')
        current=json.loads(row[0]);self._unique(current['request']['source_run_id'],current['request']['unit'],task)
        records=[dict(seq=n,body=b,sha256=h,previous_sha256=p) for n,b,h,p in self.store.conn.execute('SELECT seq,body,sha256,previous_sha256 FROM audit_history WHERE task_id=? ORDER BY seq LIMIT 33',(task,))]
        s=reconstruct(row[0].encode(),records);_check(s['task_id']==task);return s

    def _unique(self,run,unit,task):
        matches=self.store.conn.execute("SELECT task_id FROM audit_runs WHERE json_extract(body,'$.request.source_run_id')=? AND json_extract(body,'$.request.unit')=? LIMIT 2",(run,unit)).fetchall()
        _check(not matches or matches==[(task,)],'AUDITOR_REQUEST_CONFLICT')

    _validate=staticmethod(validate_audit_state)

    def _save(self,s,reason):
        s.update(updated_at=datetime.now(timezone.utc).isoformat(),last_transition=reason);self._validate(s);raw=canonical(s);_check(len(raw)<=32*1024,'AUDITOR_STATE_BOUND')
        existing=self.store.conn.execute('SELECT 1 FROM audit_runs WHERE task_id=?',(s['task_id'],)).fetchone()
        audit_transition(self._load(s['task_id']) if existing else None,s)
        prior=self.store.conn.execute('SELECT seq,sha256 FROM audit_history WHERE task_id=? ORDER BY seq DESC LIMIT 1',(s['task_id'],)).fetchone();seq=prior[0]+1 if prior else 1
        _check(seq<=32,'AUDITOR_HISTORY_BOUND')
        self.store.conn.execute('INSERT INTO audit_runs VALUES(?,?) ON CONFLICT(task_id) DO UPDATE SET body=excluded.body',(s['task_id'],raw.decode()))
        self.store.conn.execute('INSERT INTO audit_history VALUES(?,?,?,?,?)',(s['task_id'],seq,raw.decode(),_sha(raw),prior[1] if prior else None))

    def current(self,s):
        with self.store._live():
            _check(source_request(self.source,s['request']['source_run_id'],s['request']['unit'])==s['request'],'AUDITOR_SOURCE_CHANGED')
            expected=expected_environment(self.store,s['request']['source_run_id'])
            for attempt in s['attempts']:check_native(attempt.get('native_execution'),expected)

    def register(self,task,run,unit):
        _uuid(task);_check(task!=run)
        with self.store._live(),self.store.conn:
            request=source_request(self.source,run,unit);self._unique(run,unit,task)
            if self.store.conn.execute('SELECT 1 FROM audit_runs WHERE task_id=?',(task,)).fetchone():
                s=self._load(task);_check(s['request']==request,'AUDITOR_REQUEST_CONFLICT')
                if s['state']=='COMPLETED':return self.completed(task)
                return s
            _check(self.store.conn.execute('SELECT count(*) FROM audit_runs').fetchone()[0]<128,'AUDITOR_TASK_BOUND')
            s=dict(task_id=task,request=request,request_sha256=_hash(request),state='READY',owner=self.owner,attempts=[],artifact=None,audit_sha256=None,financial_accepted=False)
            self._save(s,'REGISTERED');return s

    def status(self,task):
        with self.store._live():return self._load(task)

    def prepare(self,task):
        with self.store._live():
            s=self._load(task);self.current(s);_check(s['state']=='READY' and len(s['attempts'])<2,'AUDITOR_NOT_READY')
            return dict(task_id=task,request=s['request'],request_sha256=s['request_sha256'],number=len(s['attempts'])+1,output_path=f"artifacts/runs/{task}/audit/attempt-{len(s['attempts'])+1}.json")

    def verify_launch(self,prepared,payload,reservation_id,*,execution_identity=None):
        with self.store._live():
            s=self._load(prepared['task_id']);self.current(s);r=s['request'];artifacts=[r['input_artifact'],r['result']['artifact']]+([r['fit']['artifact']] if r['fit'] else [])
            _check(prepared['request']==r and prepared['request_sha256']==s['request_sha256'])
            _check(payload['role']=='experiment_auditor' and payload['task_id']==s['task_id'] and payload['parent_task_id']==r['source_run_id'] and payload['campaign_id']==r['source_run_id'])
            _check(payload['code_sha256']==r['identity']['package_sha256'] and payload['lock_sha256']==r['identity']['lock_sha256'])
            _check(payload['input_hashes']==[a['sha256'] for a in artifacts] and payload['permissions']['filesystem_bundle']==[a['path'] for a in artifacts] and payload['permissions']['output_directory']==f"artifacts/runs/{s['task_id']}/audit")
            b=payload['budget'];_check(b['wall_seconds']==120 and b['cpu_threads']==4 and b['ram_bytes']==4*1024**3 and b['output_bytes']==16*MIB and b['max_attempts']==2)
            row=self.store.conn.execute('SELECT task,path,status,maximum FROM reservations WHERE id=?',(reservation_id,)).fetchone()
            _check(row is not None and row[0]==s['task_id'] and row[1].replace('\\','/')==prepared['output_path']+'.partial-'+reservation_id and row[2]=='OPEN' and row[3]==16*MIB)
            if execution_identity is None:_check(self.prepare(s['task_id'])==prepared)
            else:
                _check(s['state']=='RUNNING' and s['owner']==self.owner)
                a=s['attempts'][-1];_check(a['native_execution']==execution_identity and a['task']==payload and a['reservation_id']==reservation_id and a['output_path']==prepared['output_path'] and a['number']==prepared['number'])

    def begin(self,prepared,payload,reservation_id,execution_identity):
        with self.store._live(),self.store.conn:
            self.verify_launch(prepared,payload,reservation_id);s=self._load(prepared['task_id'])
            check_native(execution_identity,expected_environment(self.store,s['request']['source_run_id']))
            s['attempts'].append(dict(number=prepared['number'],status='RUNNING',output_path=prepared['output_path'],reservation_id=reservation_id,task=payload,native_execution=execution_identity))
            s.update(state='RUNNING',owner=self.owner);self._save(s,'ATTEMPT_STARTED')

    def record_exit(self,task,receipt):
        with self.store._live(),self.store.conn:
            s=self._load(task);_check(s['state']=='RUNNING' and s['owner']==self.owner)
            a=s['attempts'][-1];_check('job_receipt' not in a and receipt.get('execution_identity')==a['native_execution']);validate_receipt(receipt)
            a['job_receipt']=receipt;self._save(s,'EXIT_RECORDED')

    def interrupt(self,task,reason,*,retry=False):
        with self.store._live(),self.store.conn:
            s=self._load(task);_check(s['state']=='RUNNING' and s['owner']==self.owner)
            state=self._receipt_terminal(s['attempts'][-1].get('job_receipt')) or ('INTERRUPTED' if retry and len(s['attempts'])<2 else ('FAILED' if retry or reason=='AUDIT_REJECTED' else 'BLOCKED'))
            s['state']=state;s['attempts'][-1].update(status=state,reason=reason);self._save(s,state);return s

    def resume(self,task):
        with self.store._live(),self.store.conn:
            s=self._load(task);self.current(s);_check(s['state']=='INTERRUPTED' and len(s['attempts'])<2,'AUDITOR_NOT_RETRIABLE')
            s['state']='READY';self._save(s,'RESUMED');return s

    def _verified_output(self,s,artifact):
        task=s['task_id']
        a=s['attempts'][-1];r=s['request'];_check('job_receipt' in a and successful_exit(a['job_receipt']))
        row=self.store.conn.execute('SELECT status,manifest FROM reservations WHERE id=?',(a['reservation_id'],)).fetchone()
        _check(row is not None and row[0]=='PUBLISHED' and json.loads(row[1])==artifact and artifact['path']==a['output_path'] and artifact['task_id']==task)
        _check(type(artifact['size_bytes']) is int and 0<artifact['size_bytes']<=16*MIB)
        path=checked_path(self.storage.root,self.storage.root/artifact['path'])
        with path.open('rb') as stream:
            _check(os.fstat(stream.fileno()).st_size==artifact['size_bytes']);raw=stream.read(artifact['size_bytes']+1)
        _check(len(raw)==artifact['size_bytes'] and _sha(raw)==artifact['sha256']);v=json.loads(raw)
        _check(canonical(v)==raw);check_report(v,FIELDS,a['native_execution'])
        expected=dict(task_id=task,role='experiment_auditor',worker_pid=a['native_execution']['process']['pid'],unit=r['unit'],candidate_id=r['candidate_id'],year=r['year'],input_sha256=r['input_artifact']['sha256'],result_frame_sha256=r['result']['artifact']['sha256'],result_payload_sha256=r['result']['payload_sha256'],fit_frame_sha256=r['fit']['artifact']['sha256'] if r['fit'] else None,fit_payload_sha256=r['fit']['payload_sha256'] if r['fit'] else None,runtime_identity=r['identity'],native_authority='AWAITING_COORDINATOR_RECEIPT',financial_accepted=False)
        _check(canonical({k:v[k] for k in expected})==canonical(expected) and v['audit_sha256']==_hash(v['audit']) and v['audit']['status']=='VERIFIED_PASS' and v['audit']['candidate_sha256']==r['result']['payload_sha256'] and v['audit']['financial_accepted'] is False and v['audit']['full_M3'] is False)
        return v

    def completed(self,task):
        with self.store._live():
            s=self._load(task);_check(s['state']=='COMPLETED');self.current(s)
            try:v=self._verified_output(s,s['artifact'])
            except (OSError,ValueError,TypeError,KeyError):raise DataError('AUDITOR_OUTPUT_UNVERIFIED') from None
            _check(v['audit_sha256']==s['audit_sha256']);return s

    def accept(self,task,artifact):
        with self.store._live(),self.store.conn:
            s=self._load(task);self.current(s);_check(s['state']=='RUNNING' and s['owner']==self.owner)
            v=self._verified_output(s,artifact)
            s['attempts'][-1]['status']='COMPLETED';s.update(state='COMPLETED',artifact=artifact,audit_sha256=v['audit_sha256']);self._save(s,'COMPLETED');return s
