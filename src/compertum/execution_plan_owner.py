"""Execution-owned immutable fake plans and no-effect approval/start receipts."""
import hashlib
from .domain import ExecutionObservation,ExecutionPlan,ExecutionAuthorization,ExecutionStart,ExecutionCalendar,ContractError
from .execution_authority import ExecutionAuthority,_decode,MAX_REQUESTS
from .execution_observations import FakeObservationOwner
from .execution_plans import build_plan,authorize_fake_plan,start_operation,digest
from .execution_risk import snapshot_sha256
from .events import canonical,uuid
from .runtime.errors import RuntimeRefused

MAX_PLANS=32
CORE_BYTES=131072
PHASE_BYTES=98304
CONTEXT_KEYS=('session_id','profile_sha256','owner_instance','generation')


def _encode(value,maximum):
    raw=canonical(value).decode()
    if len(raw.encode())>maximum:raise RuntimeRefused('SAVED_PLAN_RECORD_BOUND')
    return raw,hashlib.sha256(raw.encode()).hexdigest()


def _value(row,maximum):
    if row is None:return None
    pin,raw=row
    try:
        value=_decode(raw,maximum)
        if _encode(value,maximum)!=(raw,pin):raise ValueError()
        return value
    except (ValueError,TypeError,RuntimeRefused):raise RuntimeRefused('PLAN_STATE_CORRUPT') from None


class SavedPlanOwner:
    def __init__(self,authority):
        if type(authority) is not ExecutionAuthority:raise RuntimeRefused('WRONG_OWNER_ROLE')
        self.authority=authority;self.store=authority.store;self.db=self.store.conn
        self.observations=FakeObservationOwner(authority)

    def _schema(self,*,create):
        presence=tuple(self.db.execute(q).fetchone() is not None for q in (
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fake_saved_plans'",
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fake_saved_plan_phases'",
            "SELECT 1 FROM state WHERE key='fake_saved_plan_version'",
            "SELECT 1 FROM state WHERE key='fake_plan_epoch'"))
        if any(presence) and not all(presence):raise RuntimeRefused('PLAN_STATE_CORRUPT')
        if all(presence):
            if self.db.execute("SELECT value='1' FROM state WHERE key='fake_saved_plan_version'").fetchone()!=(1,):raise RuntimeRefused('PLAN_STATE_CORRUPT')
            self.authority.plan_epoch();return
        if not create:raise RuntimeRefused('PLAN_NOT_FOUND')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('CREATE TABLE fake_saved_plans(plan_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL)')
            self.db.execute('CREATE TABLE fake_saved_plan_phases(plan_id TEXT NOT NULL REFERENCES fake_saved_plans(plan_id),phase TEXT NOT NULL,sha256 TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(plan_id,phase))')
            self.authority._state_value('fake_saved_plan_version',1)
            self.authority._state_value('fake_plan_epoch',0)

    def _context(self,value):
        return dict({k:value[k] for k in CONTEXT_KEYS},epoch=self.authority.plan_epoch())

    def _core(self,plan_id):
        row=self.db.execute('SELECT CASE WHEN length(sha256)=64 THEN sha256 END,CASE WHEN length(CAST(body AS BLOB))<=? THEN body END FROM fake_saved_plans WHERE plan_id=?',(CORE_BYTES,plan_id)).fetchone()
        core=_value(row,CORE_BYTES)
        if core is None:raise RuntimeRefused('PLAN_NOT_FOUND')
        try:
            if type(core) is not dict or set(core)!={'request_id','context','observation','plan'}:raise ValueError()
            context=core['context']
            if type(context) is not dict or set(context)!=set(CONTEXT_KEYS)|{'epoch'}:raise ValueError()
            uuid(context['session_id']);uuid(context['owner_instance'])
            if type(context['epoch']) is not int or not 0<=context['epoch']<2**63:raise ValueError()
            plan=ExecutionPlan(core['plan']);observation=ExecutionObservation(core['observation']);p=plan.to_payload();o=observation.to_payload()
            if p['plan_id']!=plan_id or p['generation']!=o['generation'] or p['generation']!=context['generation'] or p['account_alias']!=o['account_alias'] or p['snapshot_sha256']!=snapshot_sha256(observation):raise ValueError()
            profile,pin=self.authority._profile(context['session_id'])
            if pin!=context['profile_sha256']:raise ValueError()
            receipts=self._evidence(plan_id,'prepare_plan')
            expected=self._receipt(dict(request_id=core['request_id'],command={'operation':'prepare_plan'}),plan,context,plan,'PREPARED',p['created_at'],row[0])
            if receipts!=[expected]:raise ValueError()
            return core,plan,observation
        except (ValueError,TypeError,KeyError,ContractError,RuntimeRefused):raise RuntimeRefused('PLAN_STATE_CORRUPT') from None

    def _evidence(self,plan_id,operation):
        rows=self.db.execute('SELECT request_id,generation,CASE WHEN length(CAST(result AS BLOB))<=8192 THEN result END FROM fake_operator_requests LIMIT ?',(MAX_REQUESTS+1,)).fetchall()
        if len(rows)>MAX_REQUESTS:raise RuntimeRefused('OPERATOR_REQUEST_BOUND')
        matches=[]
        for key,generation,raw in rows:
            try:
                value=_decode(raw,8192)
                if type(value) is not dict or value.get('request_id')!=key or value.get('operation') not in {'open_session','supervise','halt','resume','prepare_plan','approve_plan','start_plan','advance_plan','reconcile_plan'}:raise ValueError()
                if (plan_id is None or value.get('plan_id')==plan_id) and value['operation']==operation:
                    if value.get('context',{}).get('generation')!=generation:raise ValueError()
                    matches.append(value)
            except (RuntimeRefused,ValueError,TypeError,AttributeError):raise RuntimeRefused('PLAN_STATE_CORRUPT') from None
        return matches

    def _phase(self,plan_id,phase):
        row=self.db.execute('SELECT CASE WHEN length(sha256)=64 THEN sha256 END,CASE WHEN length(CAST(body AS BLOB))<=? THEN body END FROM fake_saved_plan_phases WHERE plan_id=? AND phase=?',(PHASE_BYTES,plan_id,phase)).fetchone()
        value=_value(row,PHASE_BYTES);operation='approve_plan' if phase=='APPROVAL' else 'start_plan';receipts=self._evidence(plan_id,operation)
        if value is None:
            if receipts:raise RuntimeRefused('PLAN_STATE_CORRUPT')
            return None
        try:
            if type(value) is not dict or set(value)!={'request_id','context','observation','observation_sha256','record'}:raise ValueError()
            observation=ExecutionObservation(value['observation'])
            if digest(observation)!=value['observation_sha256']:raise ValueError()
            core,plan,original=self._core(plan_id)
            if value['context']!=core['context']:raise ValueError()
            profile,_=self.authority._profile(core['context']['session_id']);calendar=ExecutionCalendar(profile['calendar'])
            record=(ExecutionAuthorization if phase=='APPROVAL' else ExecutionStart)(value['record']);r=record.to_payload()
            now=r['authorized_at'] if phase=='APPROVAL' else r['started_at']
            if observation.to_payload()['observed_at']!=now:raise ValueError()
            if phase=='APPROVAL':
                expected=authorize_fake_plan(plan,original,now=now,calendar=calendar,current_observation=observation).to_payload()
                expected['authorization_id']=r['authorization_id']
            else:
                approval=self._phase(plan_id,'APPROVAL')
                if approval is None:raise ValueError()
                expected=start_operation(plan,approval[1],observation,now=now,calendar=calendar).to_payload();expected['start_id']=r['start_id']
            if expected!=r:raise ValueError()
            expected_receipt=self._receipt(dict(request_id=value['request_id'],command={'operation':operation}),plan,value['context'],record,'APPROVED' if phase=='APPROVAL' else 'STARTED_NO_DISPATCH',now,row[0])
            if receipts!=[expected_receipt]:raise ValueError()
            return value,record
        except (ValueError,TypeError,KeyError,ContractError,RuntimeRefused):raise RuntimeRefused('PLAN_STATE_CORRUPT') from None

    def _request(self,packet,binding):
        old=self.db.execute('SELECT CASE WHEN length(binding)=64 THEN binding END,CASE WHEN length(CAST(result AS BLOB))<=8192 THEN result END FROM fake_operator_requests WHERE request_id=?',(packet['request_id'],)).fetchone()
        if old is None:return None
        if old[0] is None:raise RuntimeRefused('OPERATOR_STATE_CORRUPT')
        if old[0]!=binding:raise RuntimeRefused('REQUEST_CONFLICT')
        return _decode(old[1],8192)

    def _save_request(self,packet,binding,result):
        raw,_=_encode(result,8192);row=(packet['request_id'],binding,self.store.lease.generation,raw)
        changed=self.db.execute('INSERT INTO fake_operator_requests VALUES(?,?,?,?)',row)
        actual=self.db.execute('SELECT request_id,binding,generation,CASE WHEN length(CAST(result AS BLOB))<=8192 THEN result END FROM fake_operator_requests WHERE request_id=?',(row[0],)).fetchone()
        if changed.rowcount!=1 or actual!=row:raise RuntimeRefused('OPERATOR_WRITE_UNVERIFIED')

    def handle(self,packet):
        command=packet['command'];operation=command['operation']
        with self.store._live():
            if self.db.in_transaction:raise RuntimeRefused('OPERATOR_TRANSACTION_OPEN')
            self._schema(create=operation not in {'inspect_plan','operation_status'})
            if operation=='inspect_plan':
                uuid(command['plan_id']);core,plan,_=self._core(command['plan_id'])
                result=dict(scope='DETERMINISTIC_FAKE',financial_accepted=False,plan_id=command['plan_id'],plan_sha256=digest(plan),plan=plan.to_payload())
                _encode(result,65536);return result
            if operation in {'advance_plan','reconcile_plan','operation_status'}:
                from .execution_operation_owner import FakeOperationOwner
                return FakeOperationOwner(self).handle(packet)
            binding=hashlib.sha256(canonical(packet)).hexdigest();old=self._request(packet,binding)
            if old is not None:return old
            if self.db.execute('SELECT count(*) FROM fake_operator_requests').fetchone()[0]>=MAX_REQUESTS:raise RuntimeRefused('OPERATOR_REQUEST_BOUND')
            try:return self._prepare(packet,binding) if operation=='prepare_plan' else self._advance(packet,binding)
            except ContractError as error:raise RuntimeRefused(str(error)) from None

    def _receipt(self,packet,plan,context,record,status,now,evidence_sha256):
        return dict(scope='DETERMINISTIC_FAKE',receipt_only=True,effects_enabled=False,financial_accepted=False,
            request_id=packet['request_id'],operation=packet['command']['operation'],status=status,plan_id=plan.to_payload()['plan_id'],
            plan_sha256=digest(plan),record_sha256=digest(record),evidence_sha256=evidence_sha256,context=context,recorded_at=now)

    def _prepare(self,packet,binding):
        if packet['command']['kind'] not in ('CANCEL','CLOSE_LONG'):raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        if self.db.execute('SELECT count(*) FROM fake_saved_plans').fetchone()[0]>=MAX_PLANS:raise RuntimeRefused('SAVED_PLAN_BOUND')
        observation,current=self.observations.read();context=self._context(current);now=current['market_at']
        plan=build_plan(observation,kind=packet['command']['kind'],now=now,calendar=current['calendar']);plan_id=plan.to_payload()['plan_id']
        core=dict(request_id=packet['request_id'],context=context,observation=observation.to_payload(),plan=plan.to_payload());raw,pin=_encode(core,CORE_BYTES)
        result=self._receipt(packet,plan,context,plan,'PREPARED',now,pin)
        # All owner/journal/broker calls finished before this transaction.
        with self.db:
            changed=self.db.execute('INSERT INTO fake_saved_plans VALUES(?,?,?)',(plan_id,pin,raw))
            if changed.rowcount!=1:raise RuntimeRefused('PLAN_WRITE_UNVERIFIED')
            self._save_request(packet,binding,result)
            if self._core(plan_id)[0]!=core:raise RuntimeRefused('PLAN_WRITE_UNVERIFIED')
        return result

    def _advance(self,packet,binding):
        command=packet['command'];uuid(command['plan_id']);core,plan,original=self._core(command['plan_id'])
        if command['plan_sha256']!=digest(plan):raise RuntimeRefused('PLAN_DIGEST_CHANGED')
        phase='APPROVAL' if command['operation']=='approve_plan' else 'START'
        if self._phase(command['plan_id'],phase) is not None:raise RuntimeRefused('PLAN_ALREADY_APPROVED' if phase=='APPROVAL' else 'PLAN_ALREADY_STARTED')
        approval=self._phase(command['plan_id'],'APPROVAL')
        if phase=='START' and approval is None:raise RuntimeRefused('PLAN_APPROVAL_REQUIRED')
        current,details=self.observations.read();context=self._context(details);now=details['market_at']
        if context!=core['context'] or approval is not None and approval[0]['context']!=context:raise RuntimeRefused('PLAN_CONTEXT_CHANGED')
        record=authorize_fake_plan(plan,original,now=now,calendar=details['calendar'],current_observation=current) if phase=='APPROVAL' else start_operation(plan,approval[1],current,now=now,calendar=details['calendar'])
        value=dict(request_id=packet['request_id'],context=context,observation=current.to_payload(),observation_sha256=digest(current),record=record.to_payload());raw,pin=_encode(value,PHASE_BYTES)
        result=self._receipt(packet,plan,context,record,'APPROVED' if phase=='APPROVAL' else 'STARTED_NO_DISPATCH',now,pin)
        with self.db:
            changed=self.db.execute('INSERT INTO fake_saved_plan_phases VALUES(?,?,?,?)',(command['plan_id'],phase,pin,raw))
            if changed.rowcount!=1:raise RuntimeRefused('PLAN_WRITE_UNVERIFIED')
            self._save_request(packet,binding,result)
            if self._phase(command['plan_id'],phase)[0]!=value:raise RuntimeRefused('PLAN_WRITE_UNVERIFIED')
        return result
