"""Compact coordinator ledger for bounded native campaign review attempts."""
from compertum.runtime.startup_record import expected_proof
from compertum.runtime.campaign_environment import check_native,observed_from_native
from compertum.development_seals import expected_environment

from datetime import datetime,timezone
import json,re
from copy import deepcopy
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier,identity,digest
from .persistence import checked_path
from .review_bundle import build_bundle,read_bundle
from .review_frame import result_binding,verify_review
from .review_evidence import check,sha,published,source_snapshot,successful_receipt,MIB
from .runtime.job_identity import validate_execution_identity,same_process
from .runtime.errors import RuntimeRefused


class ReviewRuns:
    def __init__(self,storage):
        self.storage=storage;self.store=storage.store;self.owner=storage.lease.identity.process_instance_id
        with self.store._live(),self.store.conn:
            self.store.conn.executescript('''CREATE TABLE IF NOT EXISTS campaign_reviews(task_id TEXT PRIMARY KEY,source_run_id TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,UNIQUE(source_run_id,kind));
                CREATE TABLE IF NOT EXISTS campaign_review_history(task_id TEXT NOT NULL,seq INTEGER NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL,previous_sha256 TEXT,PRIMARY KEY(task_id,seq));''')
            for (task,) in self.store.conn.execute('SELECT task_id FROM campaign_reviews').fetchall():
                s=self._load(task)
                if s['owner']!=self.owner and s['state'] in ('REGISTERING','PREPARING','RUNNING'):
                    if s['state']=='REGISTERING':s['state']='BLOCKED'
                    else:
                        s['state']=self._recovery_state(s)
                        s['attempts'][-1].update(status=s['state'],reason='OWNER_RESTART')
                    self._save(s,'OWNER_RESTART')

    @staticmethod
    def _validate(s):
        check(type(s) is dict and set(s)=={'task_id','source_run_id','kind','identity','registration_sha256','preparation_artifacts','request_sha256','request_artifact','state','owner','attempts','artifact','payload_sha256','payload_bytes','financial_accepted','last_transition','updated_at'})
        identifier(s['task_id']);identifier(s['source_run_id']);digest(s['registration_sha256']);check(s['task_id']!=s['source_run_id'] and s['kind'] in ('scorecard','aggregate','pair_compare'));identity(s['identity'])
        if s['request_sha256'] is None:check(s['kind']=='aggregate' and s['state'] in ('REGISTERING','INTERRUPTED','BLOCKED') and s['request_artifact'] is None and not s['attempts'])
        else:digest(s['request_sha256'])
        check(type(s['preparation_artifacts']) is list and len(s['preparation_artifacts'])<=2)
        if s['kind'] in ('scorecard','pair_compare'):check(s['preparation_artifacts']==[] and s['request_sha256']==s['registration_sha256'])
        for i,a in enumerate(s['preparation_artifacts']):
            check(type(a) is dict and set(a)=={'artifact_id','task_id','path','sha256','size_bytes'});identifier(a['artifact_id']);digest(a['sha256'])
            check(a['task_id']==s['task_id'] and a['path']==f"artifacts/runs/{s['task_id']}/review/input/unit-audits-{i}.json" and type(a['size_bytes']) is int and 0<a['size_bytes']<=16*MIB)
        check(s['state'] in ('REGISTERING','READY','PREPARING','RUNNING','INTERRUPTED','BLOCKED','FAILED','COMPLETED') and s['financial_accepted'] is False and type(s['attempts']) is list and len(s['attempts'])<=2)
        for number,a in enumerate(s['attempts'],1):
            check(set(a)=={'number','status','owner','output_path','task_artifact','reservation_id','native_execution','job_receipt','reason'})
            check(type(a['number']) is int and a['number']==number and a['status'] in ('PREPARING','RUNNING','INTERRUPTED','BLOCKED','FAILED','COMPLETED'))
            check(a['output_path']==f"artifacts/runs/{s['task_id']}/review/{s['kind']}-attempt-{number}.review")
            check(a['reason'] is None or type(a['reason']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',a['reason']) is not None)
            n=a['native_execution']
            if n is not None:
                validate_execution_identity(n);check(n['task_id']==s['task_id'] and n['role']==('experiment_runner' if s['kind']=='scorecard' else 'experiment_auditor') and n['code_sha256']==s['identity']['package_sha256'] and n['lock_sha256']==s['identity']['lock_sha256'])
                check(a['task_artifact'] is not None and n['task_sha256']==a['task_artifact']['sha256'] and a['reservation_id'] is not None)
            if a['job_receipt'] is not None:successful_receipt(a['job_receipt'],n)
            if a['status']=='RUNNING':check(n is not None)
            if a['status']=='COMPLETED':check(n is not None and successful_receipt(a['job_receipt'],n))
        if s['state'] in ('PREPARING','RUNNING','COMPLETED'):check(s['attempts'] and s['attempts'][-1]['status']==s['state'])
        if s['state']=='COMPLETED':check(s['artifact'] is not None and type(s['payload_bytes']) is int and s['payload_bytes']>0 and type(s['payload_sha256']) is str)
        else:check(s['artifact'] is None and s['payload_bytes'] is None and s['payload_sha256'] is None)

    @staticmethod
    def _integrity_exit(receipt):
        return receipt is not None and not receipt['timed_out'] and receipt['exit_code'] not in (0,5,125)

    @staticmethod
    def _recovery_state(s):
        if ReviewRuns._integrity_exit(s['attempts'][-1]['job_receipt']):return 'BLOCKED'
        return 'FAILED' if len(s['attempts'])==2 else 'INTERRUPTED'

    @staticmethod
    def _transition(before,after):
        reason=after['last_transition']
        if before is None:
            check(reason=='REGISTERED' and after['state']=='REGISTERING' and after['request_artifact'] is None and after['attempts']==[] and after['preparation_artifacts']==[]);return
        check(datetime.fromisoformat(after['updated_at'])>=datetime.fromisoformat(before['updated_at']))
        expected=deepcopy(before);expected.update(updated_at=after['updated_at'],last_transition=reason)
        if reason=='EXPORT_PUBLISHED':
            check(before['state']=='REGISTERING' and before['kind']=='aggregate' and before['request_sha256'] is None and len(after['preparation_artifacts'])==len(before['preparation_artifacts'])+1)
            expected['preparation_artifacts'].append(after['preparation_artifacts'][-1])
        elif reason=='BUNDLE_BOUND':
            check(before['state']=='REGISTERING' and before['kind']=='aggregate' and before['request_sha256'] is None and after['request_sha256'] is not None and before['preparation_artifacts'])
            expected['request_sha256']=after['request_sha256']
        elif reason=='INPUTS_PUBLISHED':
            check(before['state']=='REGISTERING' and before['request_sha256'] is not None and before['request_artifact'] is None and after['request_artifact'] is not None)
            expected.update(state='READY',request_artifact=after['request_artifact'])
        elif reason in ('REGISTRATION_CAPACITY','REGISTRATION_FAILED'):
            check(before['state']=='REGISTERING' and not before['attempts'])
            if reason=='REGISTRATION_CAPACITY':check(after['request_artifact'] is None)
            expected.update(state='INTERRUPTED' if reason=='REGISTRATION_CAPACITY' else 'BLOCKED',request_artifact=after['request_artifact'])
        elif reason=='REGISTRATION_RETRY':
            check(before['state']=='INTERRUPTED' and before['last_transition']=='REGISTRATION_CAPACITY' and before['request_artifact'] is None and not before['attempts'])
            expected.update(state='REGISTERING',owner=after['owner'])
        elif reason=='ATTEMPT_PREPARED':
            check(before['state']=='READY' and before['request_artifact'] is not None and len(before['attempts'])<2 and len(after['attempts'])==len(before['attempts'])+1)
            a=after['attempts'][-1];check(a['status']=='PREPARING' and a['owner']==after['owner'] and all(a[k] is None for k in ('task_artifact','reservation_id','native_execution','job_receipt','reason')))
            expected['attempts'].append(a);expected.update(state='PREPARING',owner=after['owner'])
        elif reason=='TASK_BOUND':
            check(before['state']=='PREPARING' and before['attempts'][-1]['task_artifact'] is None and after['attempts'][-1]['task_artifact'] is not None)
            expected['attempts'][-1]['task_artifact']=after['attempts'][-1]['task_artifact']
        elif reason=='NATIVE_EXECUTION_BOUND':
            check(before['state']=='PREPARING' and before['attempts'][-1]['task_artifact'] is not None and before['attempts'][-1]['native_execution'] is None and before['attempts'][-1]['reservation_id'] is None)
            expected.update(state='RUNNING');a=after['attempts'][-1]
            expected['attempts'][-1].update(status='RUNNING',native_execution=a['native_execution'],reservation_id=a['reservation_id'])
        elif reason=='EXIT_RECORDED':
            check(before['state']=='RUNNING' and before['attempts'][-1]['job_receipt'] is None and after['attempts'][-1]['job_receipt'] is not None)
            expected['attempts'][-1]['job_receipt']=after['attempts'][-1]['job_receipt']
        elif reason=='INTERRUPTED':
            check(before['state'] in ('PREPARING','RUNNING') and after['state'] in ('INTERRUPTED','FAILED','BLOCKED'))
            check(after['state']!='INTERRUPTED' or len(before['attempts'])<2)
            check(after['state']!='FAILED' or len(before['attempts'])==2)
            cause=after['attempts'][-1]['reason'];receipt=before['attempts'][-1]['job_receipt']
            check(cause is not None)
            if ReviewRuns._integrity_exit(receipt):check(after['state']=='BLOCKED')
            if cause=='REVIEW_REJECTED':check(ReviewRuns._integrity_exit(receipt) and after['state']=='BLOCKED')
            elif cause=='WORKER_FAILED':check(receipt is not None and receipt['exit_code']==5 and not receipt['timed_out'])
            elif cause=='JOB_TIMEOUT':check(receipt is not None and receipt['timed_out'])
            elif cause=='OPERATOR_PAUSE':check(receipt is not None and receipt['exit_code'] in (0,125) and not receipt['timed_out'])
            elif cause in ('LAUNCH_FAILED','LAUNCH_RETRYABLE'):check(receipt is None)
            elif cause not in ('REVIEW_ACCEPTANCE_FAILED','PAUSE_BOOKKEEPING_FAILURE','REVIEW_ACCEPTANCE_IO_FAILURE','PAUSE_IO_FAILURE'):raise DataError('REVIEW_HISTORY_TRANSITION_INVALID')
            if cause in ('LAUNCH_FAILED','REVIEW_ACCEPTANCE_FAILED','PAUSE_BOOKKEEPING_FAILURE'):check(after['state']=='BLOCKED')
            expected['state']=after['state'];expected['attempts'][-1].update(status=after['state'],reason=after['attempts'][-1]['reason'])
        elif reason=='RESUMED':
            check(before['state']=='INTERRUPTED' and before['request_artifact'] is not None and 0<len(before['attempts'])<2);expected['state']='READY'
        elif reason=='COMPLETED':
            check(before['state']=='RUNNING' and before['attempts'][-1]['job_receipt'] is not None)
            expected['attempts'][-1]['status']='COMPLETED'
            expected.update(state='COMPLETED',artifact=after['artifact'],payload_sha256=after['payload_sha256'],payload_bytes=after['payload_bytes'])
        elif reason=='OWNER_RESTART':
            check(before['state'] in ('REGISTERING','PREPARING','RUNNING'))
            if before['state']=='REGISTERING':expected['state']='BLOCKED'
            else:
                expected['state']=ReviewRuns._recovery_state(before)
                expected['attempts'][-1].update(status=expected['state'],reason='OWNER_RESTART')
        else:raise DataError('REVIEW_HISTORY_TRANSITION_INVALID')
        check(canonical(after)==canonical(expected))

    @staticmethod
    def reconstruct(final_state,records):
        check(type(final_state) is bytes and 0<len(final_state)<=16*1024 and type(records) is list and 0<len(records)<=32)
        before=None;previous=None
        for number,r in enumerate(records,1):
            check(type(r) is dict and set(r)=={'seq','body','sha256','previous_sha256'} and type(r['body']) is str)
            raw=r['body'].encode()
            check(type(r['seq']) is int and r['seq']==number and 0<len(raw)<=16*1024 and r['previous_sha256']==previous and sha(raw)==r['sha256']);previous=r['sha256']
            current=json.loads(raw);check(canonical(current)==raw);ReviewRuns._validate(current);ReviewRuns._transition(before,current);before=current
        check(canonical(before)==final_state);return before

    def _load(self,task):
        identifier(task);row=self.store.conn.execute('SELECT source_run_id,kind,body FROM campaign_reviews WHERE task_id=?',(task,)).fetchone();check(row is not None)
        records=[dict(seq=n,body=b,sha256=h,previous_sha256=p) for n,b,h,p in self.store.conn.execute('SELECT seq,body,sha256,previous_sha256 FROM campaign_review_history WHERE task_id=? ORDER BY seq LIMIT 33',(task,))]
        s=self.reconstruct(row[2].encode(),records)
        check(s['task_id']==task and s['source_run_id']==row[0] and s['kind']==row[1]);return s

    def _save(self,s,transition):
        s.update(last_transition=transition,updated_at=datetime.now(timezone.utc).isoformat());self._validate(s);raw=canonical(s);check(len(raw)<=16*1024)
        row=self.store.conn.execute('SELECT body FROM campaign_reviews WHERE task_id=?',(s['task_id'],)).fetchone()
        self._transition(self._load(s['task_id']) if row is not None else None,s)
        last=self.store.conn.execute('SELECT seq,sha256 FROM campaign_review_history WHERE task_id=? ORDER BY seq DESC LIMIT 1',(s['task_id'],)).fetchone();seq=last[0]+1 if last else 1;check(seq<=32)
        self.store.conn.execute('INSERT INTO campaign_reviews VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET body=excluded.body',(s['task_id'],s['source_run_id'],s['kind'],raw.decode()))
        self.store.conn.execute('INSERT INTO campaign_review_history VALUES(?,?,?,?,?)',(s['task_id'],seq,raw.decode(),sha(raw),last[1] if last else None))

    def _publish(self,task,path,raw):
        grant=self.storage.reserve_bytes(task,'records',len(raw))
        writer=self.storage.open_artifact(grant,path)
        try:
            for start in range(0,len(raw),8*MIB):writer.write(raw[start:start+8*MIB])
            return writer.publish()
        finally:writer.close()

    def _registration(self,kind,task,run):
        if kind=='pair_compare':
            from .pair_review import registration
            return registration(self,task,run)
        source,metadata,records=source_snapshot(self.storage,run)
        if kind=='scorecard':
            raw=build_bundle(kind=kind,task_id=task,source_run_id=run,identity=source['identity'],protocol_seal=source['protocol_seal'],metadata=metadata,records=records)
            return dict(source=source,metadata=metadata,records=records,exports=[],plan=[],registration_sha256=sha(raw),raw=raw,native=[])
        from .aggregate_evidence import collect_units,encode_exports,export_plan
        from uuid import uuid4
        cards=self.store.conn.execute("SELECT task_id FROM campaign_reviews WHERE source_run_id=? AND kind='scorecard'",(run,)).fetchall();check(len(cards)==1)
        card=self.completed(cards[0][0]);card_attempt=card['attempts'][-1]
        task_raw=published(self.storage,card_attempt['task_artifact'],64*1024,read=True)
        card_history=[dict(seq=n,body=b,sha256=h,previous_sha256=p) for n,b,h,p in self.store.conn.execute('SELECT seq,body,sha256,previous_sha256 FROM campaign_review_history WHERE task_id=? ORDER BY seq LIMIT 33',(card['task_id'],))]
        units,unit_records=collect_units(self.storage,source)
        exports=encode_exports(dict(state=card,history=card_history,task=json.loads(task_raw)),units);plan=export_plan(task,exports)
        records=records+unit_records+[dict(kind='scorecard',index=None,artifact=card['artifact'])]
        intent=sha(canonical(dict(schema='aggregate-registration-intent-v1',task_id=task,source_run_id=run,identity=source['identity'],protocol_seal=source['protocol_seal'],metadata_sha256=sha(metadata),records=records,exports=plan)))
        # Preflight exact byte/handle bounds. Random IDs are placeholders only;
        # the published request later contains actual reservation manifests.
        placeholders=[dict(artifact_id=str(uuid4()),task_id=task,path=p['path'],sha256=p['sha256'],size_bytes=p['size_bytes']) for p in plan]
        prepared=records[:-1]+[dict(kind='audit_history',index=i,artifact=a) for i,a in enumerate(placeholders)]+records[-1:]
        build_bundle(kind=kind,task_id=task,source_run_id=run,identity=source['identity'],protocol_seal=source['protocol_seal'],metadata=metadata,records=prepared)
        native=[a['native_execution'] for s in [card,*[u['state'] for u in units]] for a in s['attempts'] if a.get('native_execution') is not None]
        return dict(source=source,metadata=metadata,records=records,exports=exports,plan=plan,registration_sha256=intent,raw=None,native=native)

    def _prepared_request(self,s,context):
        check(s['registration_sha256']==context['registration_sha256'])
        check(len(s['preparation_artifacts'])==len(context['plan']))
        for a,p in zip(s['preparation_artifacts'],context['plan']):
            check(a['task_id']==s['task_id'] and all(a[k]==p[k] for k in ('path','sha256','size_bytes')));published(self.storage,a,16*MIB)
        if s['kind'] in ('scorecard','pair_compare'):return context['raw']
        records=context['records'][:-1]+[dict(kind='audit_history',index=i,artifact=a) for i,a in enumerate(s['preparation_artifacts'])]+context['records'][-1:]
        return build_bundle(kind=s['kind'],task_id=s['task_id'],source_run_id=s['source_run_id'],identity=s['identity'],protocol_seal=context['source']['protocol_seal'],metadata=context['metadata'],records=records)

    def _known_registration(self,s,context):
        if not self._unpublished_request(s) or len(s['preparation_artifacts'])>len(context['plan']):return False
        for i,p in enumerate(context['plan']):
            if i<len(s['preparation_artifacts']):
                a=s['preparation_artifacts'][i];check(a['task_id']==s['task_id'] and all(a[k]==p[k] for k in ('path','sha256','size_bytes')));published(self.storage,a,16*MIB)
            elif (checked_path(self.storage.root,self.storage.root/p['path']).exists()
                    or self.store.conn.execute("SELECT 1 FROM reservations WHERE task=? AND path=? AND status='PUBLISHED'",(s['task_id'],p['path'])).fetchone()):return False
        return True

    def register(self,task,run,kind):
        identifier(task);identifier(run);check(task!=run and kind in ('scorecard','aggregate','pair_compare'))
        with self.store._live():
            found=self.store.conn.execute('SELECT task_id FROM campaign_reviews WHERE source_run_id=? AND kind=?',(run,kind)).fetchone()
            if found:
                check(found[0]==task);s=self._load(task)
                if s['state']=='COMPLETED':return self.completed(task)
                if s['state']=='INTERRUPTED' and s['request_artifact'] is None and s['last_transition']=='REGISTRATION_CAPACITY':
                    context=self._registration(kind,task,run);check(context['registration_sha256']==s['registration_sha256'])
                    s.update(state='REGISTERING',owner=self.owner)
                    with self.store.conn:self._save(s,'REGISTRATION_RETRY')
                    return self._publish_registration(s,context)
                if s['request_artifact'] is not None:self.current(s)
                return s
            check(not self.store.conn.execute('SELECT 1 FROM campaign_reviews WHERE task_id=?',(task,)).fetchone() and self.store.conn.execute('SELECT count(*) FROM campaign_reviews').fetchone()[0]<128)
            context=self._registration(kind,task,run)
            s=dict(task_id=task,source_run_id=run,kind=kind,identity=context['source']['identity'],registration_sha256=context['registration_sha256'],preparation_artifacts=[],request_sha256=sha(context['raw']) if context['raw'] else None,request_artifact=None,state='REGISTERING',owner=self.owner,attempts=[],artifact=None,payload_sha256=None,payload_bytes=None,financial_accepted=False)
            with self.store.conn:self._save(s,'REGISTERED')
            return self._publish_registration(s,context)

    def _unpublished_request(self,s):
        path=f"artifacts/runs/{s['task_id']}/review/input/request.review"
        return (not self.store.conn.execute("SELECT 1 FROM reservations WHERE task=? AND path=? AND status='PUBLISHED'",(s['task_id'],path)).fetchone()
            and not checked_path(self.storage.root,self.storage.root/path).exists())

    def _publish_registration(self,s,context):
        try:
            check(s['registration_sha256']==context['registration_sha256'] and self._known_registration(s,context))
            for i in range(len(s['preparation_artifacts']),len(context['exports'])):
                artifact=self._publish(s['task_id'],context['plan'][i]['path'],context['exports'][i]);s['preparation_artifacts'].append(artifact)
                with self.store.conn:self._save(s,'EXPORT_PUBLISHED')
            raw=self._prepared_request(s,context)
            if s['request_sha256'] is None:
                s['request_sha256']=sha(raw)
                with self.store.conn:self._save(s,'BUNDLE_BOUND')
            else:check(s['request_sha256']==sha(raw))
            s['request_artifact']=self._publish(s['task_id'],f"artifacts/runs/{s['task_id']}/review/input/request.review",raw)
            s['state']='READY'
            with self.store.conn:self._save(s,'INPUTS_PUBLISHED')
        except Exception as error:
            retry=False
            if isinstance(error,RuntimeRefused) and error.code=='STORAGE_CAPACITY' and s['request_artifact'] is None:
                try:retry=self._known_registration(s,context)
                except Exception:retry=False
            # Reload the last durable state; a failed publication/commit is not
            # allowed to invent a remembered export or request artifact.
            s=self._load(s['task_id']);s['state']='INTERRUPTED' if retry else 'BLOCKED'
            with self.store.conn:self._save(s,'REGISTRATION_CAPACITY' if retry else 'REGISTRATION_FAILED')
            raise
        return s

    def status(self,task):
        with self.store._live():return self._load(task)

    def bundle(self,s):
        artifact=s['request_artifact'];check(artifact is not None and artifact['task_id']==s['task_id'] and artifact['path']==f"artifacts/runs/{s['task_id']}/review/input/request.review" and artifact['sha256']==s['request_sha256'])
        raw=published(self.storage,artifact,16*MIB,read=True)
        return read_bundle(raw,expected_sha256=s['request_sha256'],expected_kind=s['kind'],expected_task_id=s['task_id'],expected_source_run_id=s['source_run_id'],expected_identity=s['identity'])

    def current(self,s):
        context=self._registration(s['kind'],s['task_id'],s['source_run_id']);header,metadata=self.bundle(s)
        raw=self._prepared_request(s,context)
        check(sha(raw)==s['request_sha256'] and context['metadata']==metadata and canonical(context['source']['protocol_seal'])==canonical(header['protocol_seal']))
        expected=expected_environment(self.store,s['source_run_id'])
        for attempt in s['attempts']:
            if attempt.get('native_execution') is not None:check_native(attempt['native_execution'],expected)
        return header

    def prepare(self,task):
        with self.store._live(),self.store.conn:
            s=self._load(task);self.current(s);check(s['state']=='READY' and len(s['attempts'])<2)
            number=len(s['attempts'])+1;path=f"artifacts/runs/{task}/review/{s['kind']}-attempt-{number}.review"
            s['attempts'].append(dict(number=number,status='PREPARING',owner=self.owner,output_path=path,task_artifact=None,reservation_id=None,native_execution=None,job_receipt=None,reason=None));s.update(state='PREPARING',owner=self.owner)
            self._save(s,'ATTEMPT_PREPARED');return dict(task_id=task,number=number,request_sha256=s['request_sha256'],output_path=path)

    @staticmethod
    def _payload(s,payload,header):
        artifacts=[s['request_artifact']]+[r['artifact'] for r in header['records']]
        check(payload['task_id']==s['task_id'] and payload['role']==('experiment_runner' if s['kind']=='scorecard' else 'experiment_auditor') and payload['parent_task_id']==s['source_run_id'] and payload['campaign_id']==s['source_run_id'])
        check(payload['code_sha256']==s['identity']['package_sha256'] and payload['lock_sha256']==s['identity']['lock_sha256'])
        check(payload['input_hashes']==[a['sha256'] for a in artifacts] and payload['permissions']['filesystem_bundle']==[a['path'] for a in artifacts] and payload['permissions']['output_directory']==f"artifacts/runs/{s['task_id']}/review")
        b=payload['budget'];check(b['wall_seconds']==120 and b['cpu_threads']==4 and b['ram_bytes']==4*1024**3 and b['output_bytes']==16*MIB and b['max_attempts']==2)
        return artifacts

    def bind_task(self,prepared,payload):
        with self.store._live():
            s=self._load(prepared['task_id']);header=self.current(s);a=s['attempts'][-1]
            check(s['state']=='PREPARING' and s['owner']==self.owner and a['task_artifact'] is None and prepared==dict(task_id=s['task_id'],number=a['number'],request_sha256=s['request_sha256'],output_path=a['output_path']))
            self._payload(s,payload,header);raw=canonical(payload);check(len(raw)<=64*1024)
            a['task_artifact']=self._publish(s['task_id'],f"artifacts/runs/{s['task_id']}/review/input/task-attempt-{a['number']}.json",raw)
            with self.store.conn:self._save(s,'TASK_BOUND')

    def verify_launch(self,prepared,payload,reservation,*,execution_identity=None):
        with self.store._live():
            s=self._load(prepared['task_id']);header=self.current(s);a=s['attempts'][-1]
            check(prepared==dict(task_id=s['task_id'],number=a['number'],request_sha256=s['request_sha256'],output_path=a['output_path']))
            check(s['owner']==self.owner and s['state']==('PREPARING' if execution_identity is None else 'RUNNING'))
            check(a['task_artifact'] is not None and published(self.storage,a['task_artifact'],64*1024,read=True)==canonical(payload))
            artifacts=self._payload(s,payload,header)
            row=self.store.conn.execute('SELECT task,path,status,maximum FROM reservations WHERE id=?',(reservation,)).fetchone()
            check(row is not None and row[0]==s['task_id'] and row[1].replace('\\','/')==a['output_path']+'.partial-'+reservation and row[2]=='OPEN' and row[3]==16*MIB)
            if execution_identity is not None:check(canonical(a['native_execution'])==canonical(execution_identity) and a['reservation_id']==reservation)
            return s,artifacts

    def begin(self,prepared,payload,reservation,native):
        with self.store._live(),self.store.conn:
            s,_=self.verify_launch(prepared,payload,reservation);validate_execution_identity(native)
            check(native['task_sha256']==sha(canonical(payload)));check_native(native,expected_environment(self.store,s['source_run_id']))
            state,_,_=source_snapshot(self.storage,s['source_run_id'])
            for a in state['attempts']:
                if a.get('native_execution') is not None:check(not same_process(native,a['native_execution']))
            if s['kind'] in ('aggregate','pair_compare'):
                for prior in self._registration(s['kind'],s['task_id'],s['source_run_id'])['native']:check(not same_process(native,prior))
            s['attempts'][-1].update(status='RUNNING',reservation_id=reservation,native_execution=native);s['state']='RUNNING';self._save(s,'NATIVE_EXECUTION_BOUND')

    def record_exit(self,task,receipt):
        with self.store._live(),self.store.conn:
            s=self._load(task);check(s['state']=='RUNNING' and s['owner']==self.owner);a=s['attempts'][-1];check(a['job_receipt'] is None)
            successful_receipt(receipt,a['native_execution']);a['job_receipt']=receipt;self._save(s,'EXIT_RECORDED')

    def interrupt(self,task,reason,*,retry=False):
        with self.store._live(),self.store.conn:
            s=self._load(task);check(s['state'] in ('PREPARING','RUNNING') and s['owner']==self.owner)
            if self._integrity_exit(s['attempts'][-1]['job_receipt']):retry=False
            s['state']='INTERRUPTED' if retry and len(s['attempts'])<2 else 'FAILED' if retry else 'BLOCKED'
            s['attempts'][-1].update(status=s['state'],reason=reason);self._save(s,'INTERRUPTED');return s

    def resume(self,task):
        with self.store._live(),self.store.conn:
            s=self._load(task);self.current(s);check(s['state']=='INTERRUPTED' and len(s['attempts'])<2);s['state']='READY';self._save(s,'RESUMED');return s

    def _output(self,s,artifact):
        a=s['attempts'][-1];n=a['native_execution'];check(successful_receipt(a['job_receipt'],n))
        task_artifact=a['task_artifact'];check(task_artifact['task_id']==s['task_id'] and task_artifact['path']==f"artifacts/runs/{s['task_id']}/review/input/task-attempt-{a['number']}.json")
        task_raw=published(self.storage,task_artifact,64*1024,read=True);payload=json.loads(task_raw)
        check(canonical(payload)==task_raw and sha(task_raw)==n['task_sha256'])
        header,_=self.bundle(s);self._payload(s,payload,header)
        row=self.store.conn.execute('SELECT status,manifest FROM reservations WHERE id=?',(a['reservation_id'],)).fetchone()
        check(row is not None and row[0]=='PUBLISHED' and canonical(json.loads(row[1]))==canonical(artifact) and artifact['path']==a['output_path'] and artifact['task_id']==s['task_id'])
        published(self.storage,artifact,16*MIB)
        path=checked_path(self.storage.root,self.storage.root/artifact['path'])
        binding=result_binding(s['kind'],s['task_id'],s['source_run_id'],s['request_sha256'],s['identity'],n['process']['pid'],startup=expected_proof(n),environment=observed_from_native(n))
        with path.open('rb') as stream:result=verify_review(stream,binding)
        check(result['sha256']==artifact['sha256'] and result['size_bytes']==artifact['size_bytes']);return result

    def accept(self,task,artifact):
        with self.store._live(),self.store.conn:
            s=self._load(task);check(s['state']=='RUNNING' and s['owner']==self.owner);self.current(s);result=self._output(s,artifact)
            s['attempts'][-1]['status']='COMPLETED';s.update(state='COMPLETED',artifact=artifact,payload_sha256=result['payload_sha256'],payload_bytes=result['payload_bytes']);self._save(s,'COMPLETED');return s

    def completed(self,task):
        with self.store._live():
            s=self._load(task);check(s['state']=='COMPLETED');self.current(s);result=self._output(s,s['artifact'])
            check(result['payload_sha256']==s['payload_sha256'] and result['payload_bytes']==s['payload_bytes']);return s
