"""Non-numerical foreground control of the single consumed synthetic final batch."""
from datetime import datetime,timezone
import json
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier
from .evaluation_seals import verify_seal_journal,reserve_seal_append
from .consumption import verify_consumption_guard
from .final_transaction import final_receipt,reserve_final
from .final_dispatch import FinalRuns,check,context
from .final_completion import record_exit,propose_close,close_through_owner,_read
from .development_seals import _caller
from .clean_registration import _text
from .review_evidence import published,sha
from .review_frame import result_binding,verify_review
from .runtime.startup_record import expected_proof
from .runtime.campaign_environment import observed_from_native
from .runtime.errors import RuntimeRefused
from .runtime.jobs import launch_bounded,job_slot_busy,preflight_campaign
from .storage import adopt_fixture_bytes

ACTIVE=frozenset({'CONSUMED_WAITING_FOR_BATCH','BATCH_RUNNING','BATCH_INTERRUPTED'})


class FinalController:
    def __init__(self,coordinator,storage,evaluation):
        self.coordinator=coordinator;self.storage=storage;self.store=storage.store
        self.evaluation=evaluation;self.runs=FinalRuns(storage);self.active=None;self.errors={};self.recovered=set()

    def _call(self,payload):
        with self.store._live() as scope:return _caller(self.evaluation,scope.project)(payload)

    def status(self,seal_id):
        identifier(seal_id)
        return self._call(dict(operation='inspect_final',seal_id=seal_id))

    def records(self):
        with self.store._live() as scope:
            evidence=verify_seal_journal(scope.project);guard=verify_consumption_guard(scope.project)
            check(evidence['status']==guard['status']=='VERIFIED')
            result=[]
            for sid,row in sorted(evidence['seals'].items()):
                if row.get('final') is None:continue
                receipt=final_receipt(scope.project.project_id,evidence,guard,sid)
                result.append(dict(seal_id=sid,evaluation_id=receipt['evaluation_id'],status=receipt['status'],recovery_error=self.errors.get(sid)))
            return result

    def _dispatches(self,seal_id):
        rows=self.store.conn.execute('SELECT '+_text('body',32768)+','+_text('sha256',64)+' FROM final_dispatches WHERE seal_id=? LIMIT 3',(seal_id,)).fetchall()
        check(len(rows)<=2);result=[]
        for raw,pin in rows:
            check(type(raw) is str and sha(raw.encode())==pin);d=json.loads(raw)
            check(canonical(d).decode()==raw and d['seal_id']==seal_id);result.append(d)
        return sorted(result,key=lambda d:d['attempt']['number'])

    def _orphan_preparation(self,receipt):
        # The first publication precedes dispatch INSERT. Never overwrite its fixed names.
        eid=receipt['evaluation_id'];number=receipt.get('attempt_count',0)+1
        prefix=f'artifacts/runs/{eid}/'
        names=[prefix+f'input/final/attempt-{number:02}.json',prefix+f'input/final/task-attempt-{number:02}.json',prefix+f'final/attempt-{number:02}.final']
        found=self.store.conn.execute("SELECT count(*) FROM reservations WHERE task=? AND category='records' AND (path IS NULL OR replace(path,char(92),'/')=? OR replace(path,char(92),'/') LIKE ? OR replace(path,char(92),'/')=? OR replace(path,char(92),'/') LIKE ? OR replace(path,char(92),'/')=? OR replace(path,char(92),'/') LIKE ?)",(eid,names[0],names[0]+'.partial-%',names[1],names[1]+'.partial-%',names[2],names[2]+'.partial-%')).fetchone()[0]
        return bool(found) or any((self.storage.root/name).exists() for name in names)

    def recover(self,seal_id):
        identifier(seal_id)
        if self.active is not None:raise RuntimeRefused('JOB_SLOT_BUSY')
        with self.store._live() as scope:
            receipt=self.status(seal_id)
            if receipt['status'] not in ACTIVE:
                from .final_completion import observe_exited
                evidence=verify_seal_journal(scope.project);attempts=evidence['seals'][seal_id].get('final_attempts',[])
                for d in self._dispatches(seal_id):
                    if d['attempt']['native_execution'] is not None and not any(a['start']['attempt']['attempt_id']==d['attempt']['attempt_id'] and a['close'] is not None for a in attempts):observe_exited(d['attempt']['native_execution'])
                self.errors.pop(seal_id,None);self.recovered.add(seal_id);return receipt
            evidence,_,_=context(scope.project,seal_id);row=evidence['seals'][seal_id];attempts=row.get('final_attempts',[])
            dispatches=self._dispatches(seal_id)
            pending=[d for d in dispatches if not any(a['start']['attempt']['attempt_id']==d['attempt']['attempt_id'] and a['close'] is not None for a in attempts)]
            check(len(pending)<=1)
            if not pending:
                check(receipt['status']!='BATCH_RUNNING')
                if self._orphan_preparation(receipt):
                    reserve_seal_append(self.storage);self._call(dict(operation='invalidate',seal_id=seal_id,reason='STATUS_UNCERTAIN'))
                    receipt=self.status(seal_id)
                self.errors.pop(seal_id,None);return receipt
            d=pending[0];aid=d['attempt']['attempt_id'];reserve_final(self.storage,seal_id)
            started=next((a for a in attempts if a['start']['attempt']['attempt_id']==aid),None)
            if started is None:
                result=self._call(dict(operation='abandon_final_preparation',seal_id=seal_id,attempt_id=aid))
            elif self.store.conn.execute('SELECT 1 FROM final_closures WHERE attempt_id=?',(aid,)).fetchone():
                proposal,pin=_read(self.store.conn,'final_closures',aid,8192)
                if proposal['mode']=='COMPLETED':self.coordinator.require_health()
                result=close_through_owner(self.runs,d,pin,evaluation=self.evaluation)
            elif self.store.conn.execute('SELECT 1 FROM final_exits WHERE attempt_id=?',(aid,)).fetchone():
                # The lost intent/publication cannot authorize a retry or acceptance.
                pin=propose_close(self.runs,d,'REJECTED')
                result=close_through_owner(self.runs,d,pin,evaluation=self.evaluation)
            else:result=self._call(dict(operation='abandon_final',seal_id=seal_id,attempt_id=aid))
            self.errors.pop(seal_id,None);return result

    def step(self,seal_id):
        identifier(seal_id)
        if self.coordinator.status()['research_state']!='RUNNING':raise RuntimeRefused('RESEARCH_PAUSED')
        self.coordinator.require_health()
        if self.active is not None or job_slot_busy(self.storage.lease):raise RuntimeRefused('JOB_SLOT_BUSY')
        preflight_campaign(self.storage.lease)
        receipt=self.recover(seal_id)
        if receipt['status'] not in {'CONSUMED_WAITING_FOR_BATCH','BATCH_INTERRUPTED'}:raise RuntimeRefused('FINAL_NOT_RESUMABLE')
        with self.store._live() as scope:
            evidence=verify_seal_journal(scope.project);check(evidence['status']=='VERIFIED')
            rows=self.store.conn.execute('SELECT '+_text('seal_id',36)+','+_text('attempt_id',36)+' FROM final_dispatches LIMIT 65').fetchall();check(len(rows)<=64)
            for sid,aid in rows:
                identifier(sid);identifier(aid)
                if sid==seal_id or sid in self.recovered:continue
                prior=evidence['seals'].get(sid,{}).get('final_attempts',[])
                if sid in self.errors or not any(a['start']['attempt']['attempt_id']==aid and a['close'] is not None for a in prior):raise RuntimeRefused('FINAL_RECOVERY_REQUIRED')
        self.recovered.discard(seal_id)
        reserve_final(self.storage,seal_id);writer=None;job=None
        try:
            d,task,writer=self.runs.prepare(seal_id,now=datetime.now(timezone.utc))
            def commit(native):
                self.coordinator.require_health();reserve_final(self.storage,seal_id)
                self.runs.begin(d,native,evaluation=self.evaluation)
            job=launch_bounded(self.storage.lease,task,['fixture','final',str(writer.destination)],writer=writer,final_request=d,before_resume=commit)
            self.active=(d,writer,job)
            return self.status(seal_id)
        except Exception as error:
            self.errors[seal_id]=getattr(error,'code','FINAL_LAUNCH_UNVERIFIED')
            self._cleanup(seal_id,writer,job)
            raise

    def _cleanup(self,seal_id,writer,job):
        failure=None
        try:
            if job is not None:job.close()
        except Exception as error:failure=error
        try:
            if writer is not None:writer.close()
        except Exception as error:
            if failure is None:failure=error
        finally:self.active=None
        if failure is not None:
            self.recovered.discard(seal_id);self.errors[seal_id]=getattr(failure,'code','FINAL_CLEANUP_UNVERIFIED')
            raise failure

    def _publication(self,d,writer,receipt):
        self.coordinator.require_health()
        request=json.loads(published(self.storage,d['request_artifact'],32768,read=True))
        with self.store._live() as scope:evidence,_,_=context(scope.project,d['seal_id'])
        runtime=evidence['seals'][d['seal_id']]['final']['plan']['runtime'];n=receipt['execution_identity']
        binding=result_binding('final',d['attempt']['evaluation_id'],request['source_artifact']['task_id'],d['request_artifact']['sha256'],runtime,n['process']['pid'],startup=expected_proof(n),environment=observed_from_native(n))
        with writer.path.open('rb') as stream:proof=verify_review(stream,binding)
        self.coordinator.require_health()
        artifact=writer.publish();check(all(artifact[k]==proof[k] for k in ('size_bytes','sha256')))
        return dict(artifact=artifact,payload_sha256=proof['payload_sha256'],payload_bytes=proof['payload_bytes'])

    def _finish(self,mode=None):
        d,writer,job=self.active;sid=d['seal_id']
        try:
            receipt=job.wait();record_exit(self.runs,d,receipt);adopt_fixture_bytes(writer,job);publication=None
            if mode is None:
                mode='REJECTED'
                if receipt['exit_code']==0 and not receipt['timed_out']:
                    try:publication=self._publication(d,writer,receipt);mode='COMPLETED'
                    except (DataError,RuntimeRefused,OSError):publication=None
            reserve_final(self.storage,sid)
            pin=propose_close(self.runs,d,mode,publication=publication)
            if mode=='COMPLETED':self.coordinator.require_health()
            result=close_through_owner(self.runs,d,pin,evaluation=self.evaluation)
            self.errors.pop(sid,None);return result
        except Exception as error:
            self.errors[sid]=getattr(error,'code','FINAL_COMPLETION_UNVERIFIED');raise
        finally:
            # Durable dispatch remains the recovery authority after handles are closed.
            self._cleanup(sid,writer,job)

    def tick(self):
        if self.active is None:return None
        d,writer,job=self.active
        try:
            if job.api.active(job.job):return None
        except (RuntimeRefused,OSError) as error:
            self.errors[d['seal_id']]=getattr(error,'code','FINAL_JOB_UNVERIFIED')
            try:self._cleanup(d['seal_id'],writer,job)
            except (RuntimeRefused,OSError):pass
            return None
        try:return self._finish()
        except (DataError,RuntimeRefused,OSError):return None

    def pause(self,reason='OPERATOR_PAUSE',*,terminal=False):
        if self.active is None:return None
        d,writer,job=self.active
        job.api.checked(job.api.TerminateJobObject(job.job.get(),125),'PauseFinalJob')
        return self._finish('STOPPED' if terminal else 'INTERRUPTED')

    def control(self,seal_id,operation):
        identifier(seal_id)
        if operation=='status':return self.status(seal_id)
        if operation in ('step','resume'):return self.step(seal_id)
        if operation=='recover':return self.recover(seal_id)
        if operation not in ('pause','stop'):raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        if self.active is not None:
            if self.active[0]['seal_id']!=seal_id:raise RuntimeRefused('RUN_NOT_ACTIVE')
            return self.pause(terminal=operation=='stop')
        receipt=self.status(seal_id)
        if operation=='stop' and receipt['status'] in ACTIVE:
            receipt=self.recover(seal_id)
            if receipt['status'] in ACTIVE:
                reserve_seal_append(self.storage);self._call(dict(operation='invalidate',seal_id=seal_id,reason='OPERATOR_INVALIDATED'))
                receipt=self.status(seal_id)
        return receipt
