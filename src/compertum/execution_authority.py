"""Execution-owned fake session and native operator-presence receipts.

No order, plan authorization or financial capability is granted by this module.
"""
from datetime import timedelta
import hashlib,json,math,re,time
from .domain import ExecutionCalendar,ExecutionInputs,ContractError
from .events import canonical,uuid
from .execution_contracts import instant,record_sha256
from .persistence import StateStore
from .storage import JournalReserve
from .runtime.execution_health import MutualHealth,execution_durable
from .runtime.owners import require_live_owner
from .runtime.errors import RuntimeRefused

MAX_REQUESTS=1024
MAX_SESSIONS=32
KEY='fake_operator_state'
STATE_KEYS={'owner_instance','owner_generation','session_id','anchor_mono','anchor_utc','ack_mono','ack_utc','armed','halted','reason'}


def _decode(raw,maximum=65536):
    if type(raw) is not str or not 0<len(raw.encode())<=maximum:raise RuntimeRefused('OPERATOR_STATE_CORRUPT')
    try:
        def pairs(items):
            value={}
            for k,v in items:
                if k in value:raise ValueError()
                value[k]=v
            return value
        return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except (ValueError,RecursionError):raise RuntimeRefused('OPERATOR_STATE_CORRUPT') from None


class ExecutionAuthority:
    def __init__(self,store,reserve,health):
        if type(store) is not StateStore or type(reserve) is not JournalReserve or type(health) is not MutualHealth:raise RuntimeRefused('WRONG_OWNER_ROLE')
        require_live_owner(store.lease,'execution')
        if reserve.lease!=store.lease or health.lease!=store.lease:raise RuntimeRefused('OWNER_UNVERIFIED')
        self.store=store;self.reserve=reserve;self.health=health;self.db=store.conn;self.last_tick=None;self.plan_owner=None
        with store._live(),self.db:
            presence=tuple(self.db.execute(query).fetchone() is not None for query in (
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fake_operator_requests'",
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fake_operator_profiles'",
                "SELECT 1 FROM state WHERE key='fake_operator_state'",
                "SELECT 1 FROM state WHERE key='fake_operator_version'"))
            if any(presence) and not all(presence):raise RuntimeRefused('OPERATOR_STATE_CORRUPT')
            if all(presence):
                if self.db.execute("SELECT value='1' FROM state WHERE key='fake_operator_version'").fetchone()!=(1,):raise RuntimeRefused('OPERATOR_STATE_CORRUPT')
            else:self._state_value('fake_operator_version',1)
            self.db.execute('CREATE TABLE IF NOT EXISTS fake_operator_requests(request_id TEXT PRIMARY KEY,binding TEXT NOT NULL,generation INTEGER NOT NULL,result TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS fake_operator_profiles(session_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL)')
            row=self.db.execute('SELECT 1 FROM state WHERE key=?',(KEY,)).fetchone()
            state=self._read_state() if row is not None else None
            if state is None or state['owner_instance']!=store.lease.identity.process_instance_id or state['owner_generation']!=store.lease.generation:
                self._write(dict(owner_instance=store.lease.identity.process_instance_id,owner_generation=store.lease.generation,
                    session_id=state['session_id'] if state else None,anchor_mono=None,anchor_utc=None,ack_mono=None,ack_utc=None,
                    armed=False,halted=True,reason='PROCESS_START'))

    def _read_state(self):
        row=self.db.execute('SELECT CASE WHEN length(value)<=65536 THEN value ELSE NULL END FROM state WHERE key=?',(KEY,)).fetchone()
        state=_decode(row[0]) if row else None
        if type(state) is not dict or set(state)!=STATE_KEYS:raise RuntimeRefused('OPERATOR_STATE_CORRUPT')
        try:
            uuid(state['owner_instance'])
            if state['session_id'] is not None:uuid(state['session_id'])
            if type(state['owner_generation']) is not int or state['owner_generation']<1:raise ValueError()
            for k in ('anchor_mono','anchor_utc','ack_mono','ack_utc'):
                if state[k] is not None and (type(state[k]) not in (int,float) or not math.isfinite(state[k]) or state[k]<0):raise ValueError()
            if any(type(state[k]) is not bool for k in ('armed','halted')) or type(state['reason']) is not str or len(state['reason'])>128:raise ValueError()
            if (state['anchor_mono'] is None)!=(state['anchor_utc'] is None) or (state['ack_mono'] is None)!=(state['ack_utc'] is None):raise ValueError()
        except (ValueError,TypeError,RuntimeRefused):raise RuntimeRefused('OPERATOR_STATE_CORRUPT') from None
        return state

    def _state_value(self,key,value):
        raw=canonical(value).decode()
        changed=self.db.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,raw))
        observed=self.db.execute('SELECT CASE WHEN length(value)<=65536 THEN value ELSE NULL END FROM state WHERE key=?',(key,)).fetchone()
        if changed.rowcount!=1 or observed!=(raw,):raise RuntimeRefused('OPERATOR_WRITE_UNVERIFIED')

    def plan_epoch(self):
        row=self.db.execute("SELECT CASE WHEN length(value)<=32 THEN value END FROM state WHERE key='fake_plan_epoch'").fetchone()
        if row is None:raise RuntimeRefused('PLAN_STATE_CORRUPT')
        value=_decode(row[0],32)
        if type(value) is not int or not 0<=value<2**63-1:raise RuntimeRefused('PLAN_STATE_CORRUPT')
        return value

    def _write(self,state):
        if self.db.execute("SELECT 1 FROM state WHERE key='fake_plan_epoch'").fetchone() is not None:
            epoch=self.plan_epoch();prior=self._read_state()
            invalidated=any(prior[k]!=state[k] for k in ('owner_instance','owner_generation','session_id')) or prior['ack_mono'] is not None and state['ack_mono'] is None
            if invalidated:self._state_value('fake_plan_epoch',epoch+1)
        self._state_value(KEY,state)
        for k,v in (('armed',state['armed']),('admission','HALTED' if state['halted'] else 'DISARMED')):self._state_value(k,v)
        if not state['armed']:self._state_value('approved_plan',None)

    def _validated_profile(self,value):
        if type(value) is not dict or set(value)!={'calendar','inputs','fixture_at','account_alias'}:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        try:
            calendar=ExecutionCalendar(value['calendar']);inputs=ExecutionInputs(value['inputs']);at=instant(value['fixture_at'])
            c=calendar.to_payload();i=inputs.to_payload()
            if (type(value['account_alias']) is not str or not re.fullmatch(r'fake-[a-z0-9_-]{1,48}',value['account_alias'])
                or i['calendar_sha256']!=record_sha256(calendar) or i['session_date']!=c['session_date']
                or i['arm_expires_at']!=c['session_close_at'] or at.date().isoformat()!=c['session_date']):raise RuntimeRefused('SESSION_INPUTS_CHANGED')
            result=dict(calendar=c,inputs=i,fixture_at=value['fixture_at'],account_alias=value['account_alias'])
            if len(canonical(result))>65536:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
            return result
        except (ContractError,ValueError,TypeError):raise RuntimeRefused('SESSION_INPUTS_CHANGED') from None

    def _profile(self,session_id):
        row=self.db.execute('SELECT CASE WHEN length(sha256)=64 THEN sha256 ELSE NULL END,CASE WHEN length(body)<=65536 THEN body ELSE NULL END FROM fake_operator_profiles WHERE session_id=?',(session_id,)).fetchone()
        if row is None:raise RuntimeRefused('OPERATOR_STATE_CORRUPT')
        value=self._validated_profile(_decode(row[1]))
        if hashlib.sha256(canonical(value)).hexdigest()!=row[0]:raise RuntimeRefused('OPERATOR_STATE_CORRUPT')
        return value,row[0]

    def _ready(self):
        if self.health.status()['verified'] is not True:raise RuntimeRefused('EXECUTION_HEALTH_UNVERIFIED')
        execution_durable(self.store,self.reserve)

    def _market_at(self,state,profile):
        if state['anchor_mono'] is None:return None
        elapsed=time.monotonic()-state['anchor_mono']
        if elapsed<0:raise RuntimeRefused('CLOCK_REVERSED')
        return (instant(profile['fixture_at'])+timedelta(seconds=elapsed)).isoformat()

    def tick(self,*,force=False):
        now=time.monotonic()
        if not force and self.last_tick is not None and 0<=now-self.last_tick<.5:return
        self.last_tick=now
        with self.store._live(),self.db:
            state=self._read_state();before=canonical(state)
            try:self._ready()
            except RuntimeRefused as error:state.update(armed=False,halted=True,ack_mono=None,ack_utc=None,reason=error.code)
            if state['ack_mono'] is not None and not(0<=now-state['ack_mono']<=300 and 0<=time.time()-state['ack_utc']<=300):state.update(armed=False,halted=True,ack_mono=None,ack_utc=None,reason='SUPERVISION_EXPIRED')
            if state['session_id'] is not None and state['anchor_mono'] is not None:
                profile,_=self._profile(state['session_id'])
                if state['reason']!='SUPERVISION_EXPIRED' and instant(self._market_at(state,profile))>=instant(profile['calendar']['session_close_at']):state.update(armed=False,halted=True,reason='SESSION_CLOSED')
            if canonical(state)!=before:self._write(state)

    def status(self):
        self.tick(force=True)
        with self.store._live():
            state=self._read_state();profile,pin=self._profile(state['session_id']) if state['session_id'] else (None,None)
            supervised=state['ack_mono'] is not None and 0<=time.monotonic()-state['ack_mono']<=300 and 0<=time.time()-state['ack_utc']<=300
            return dict(scope='DETERMINISTIC_FAKE',financial_accepted=False,session_id=state['session_id'],profile_sha256=pin,
                generation=self.store.lease.generation,armed=state['armed'],halted=state['halted'],supervised=supervised,
                reason=state['reason'],market_at=self._market_at(state,profile) if profile else None)

    def require_supervised(self):
        self.tick(force=True);self._ready()
        with self.store._live():
            state=self._read_state()
            if state['session_id'] is None:raise RuntimeRefused('SESSION_REQUIRED')
            if state['anchor_mono'] is None:raise RuntimeRefused('SESSION_RESTARTED')
            if state['ack_mono'] is None:raise RuntimeRefused('SUPERVISION_EXPIRED' if state['reason']=='SUPERVISION_EXPIRED' else 'SUPERVISION_REQUIRED')
            if not(0<=time.monotonic()-state['ack_mono']<=300 and 0<=time.time()-state['ack_utc']<=300):raise RuntimeRefused('SUPERVISION_EXPIRED')
            profile,pin=self._profile(state['session_id'])
            return dict(session_id=state['session_id'],profile_sha256=pin,profile=profile,market_at=self._market_at(state,profile))

    def observation_context(self):
        """Map verified native timestamps into the explicitly invented session."""
        context=self.require_supervised()
        with self.store._live():
            state=self._read_state();lease=self.store.lease
            if state['owner_instance']!=lease.identity.process_instance_id or state['owner_generation']!=lease.generation:
                raise RuntimeRefused('SESSION_RESTARTED')
            base=instant(context['profile']['fixture_at'])
            def stamp(value):return (base+timedelta(seconds=value-state['anchor_mono'])).isoformat()
            return dict(context,market_at=stamp(time.monotonic()),watchdog_at=stamp(self.health.observed),
                supervision_at=stamp(state['ack_mono']),halted=state['halted'],
                owner_instance=lease.identity.process_instance_id,generation=lease.generation)

    def handle(self,packet):
        if type(packet) is not dict or set(packet)!={'request_id','subject_key','command'}:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        uuid(packet['request_id'])
        if type(packet['subject_key']) is not str or not re.fullmatch('[0-9a-f]{64}',packet['subject_key']):raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        command=packet['command']
        if type(command) is not dict or type(command.get('operation')) is not str:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        operation=command['operation'];plan_keys={'prepare_plan':{'operation','kind'},'inspect_plan':{'operation','plan_id'},'approve_plan':{'operation','plan_id','plan_sha256'},'start_plan':{'operation','plan_id','plan_sha256'},'advance_plan':{'operation','plan_id','plan_sha256'},'reconcile_plan':{'operation','plan_id','plan_sha256'},'operation_status':{'operation','plan_id'}}
        keys=plan_keys.get(operation,{'operation','session_id','profile'} if operation=='open_session' else {'operation'})
        if operation not in {'status','open_session','supervise','halt','resume'}|set(plan_keys) or set(command)!=keys:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        raw=canonical(packet)
        if len(raw)>65536:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        if self.db.in_transaction:raise RuntimeRefused('OPERATOR_TRANSACTION_OPEN')
        self.tick(force=True)
        if operation=='resume':return self._resume(packet)
        if operation in plan_keys:
            if self.plan_owner is None:
                from .execution_plan_owner import SavedPlanOwner
                self.plan_owner=SavedPlanOwner(self)
            return self.plan_owner.handle(packet)
        if operation=='status':return self.status()
        binding=hashlib.sha256(raw).hexdigest()
        with self.store._live(),self.db:
            old=self.db.execute('SELECT CASE WHEN length(binding)=64 THEN binding ELSE NULL END,CASE WHEN length(result)<=8192 THEN result ELSE NULL END FROM fake_operator_requests WHERE request_id=?',(packet['request_id'],)).fetchone()
            if old:
                if old[0] is None:raise RuntimeRefused('OPERATOR_STATE_CORRUPT')
                if old[0]!=binding:raise RuntimeRefused('REQUEST_CONFLICT')
                return _decode(old[1],8192)
            if self.db.execute('SELECT count(*) FROM fake_operator_requests').fetchone()[0]>=MAX_REQUESTS:raise RuntimeRefused('OPERATOR_REQUEST_BOUND')
            state=self._read_state()
            if operation=='open_session':
                uuid(command['session_id']);profile=self._validated_profile(command['profile']);body=canonical(profile).decode();pin=hashlib.sha256(body.encode()).hexdigest()
                existing=self.db.execute('SELECT CASE WHEN length(sha256)=64 THEN sha256 ELSE NULL END FROM fake_operator_profiles WHERE session_id=?',(command['session_id'],)).fetchone()
                if existing:
                    if existing[0]!=pin:raise RuntimeRefused('SESSION_CONFLICT')
                    if state['session_id']!=command['session_id'] or state['anchor_mono'] is None:raise RuntimeRefused('SESSION_RESTARTED')
                else:
                    if self.db.execute('SELECT count(*) FROM fake_operator_profiles').fetchone()[0]>=MAX_SESSIONS:raise RuntimeRefused('OPERATOR_SESSION_BOUND')
                    changed=self.db.execute('INSERT INTO fake_operator_profiles VALUES(?,?,?)',(command['session_id'],pin,body))
                    if changed.rowcount!=1 or self._profile(command['session_id'])!=(profile,pin):raise RuntimeRefused('OPERATOR_WRITE_UNVERIFIED')
                    state.update(session_id=command['session_id'],anchor_mono=time.monotonic(),anchor_utc=time.time(),ack_mono=None,ack_utc=None,armed=False,halted=True,reason='SESSION_OPENED')
            elif operation=='supervise':
                self._ready()
                if state['session_id'] is None:raise RuntimeRefused('SESSION_REQUIRED')
                if state['anchor_mono'] is None:raise RuntimeRefused('SESSION_RESTARTED')
                state.update(ack_mono=time.monotonic(),ack_utc=time.time(),reason='SESSION_CLOSED' if state['reason']=='SESSION_CLOSED' else 'OPERATOR_PRESENT')
            else:state.update(armed=False,halted=True,ack_mono=None,ack_utc=None,reason='OPERATOR_HALT')
            self._write(state)
            result=dict(scope='DETERMINISTIC_FAKE',financial_accepted=False,receipt_only=True,operation=operation,request_id=packet['request_id'],
                generation=self.store.lease.generation,owner_instance=self.store.lease.identity.process_instance_id,session_id=state['session_id'],
                recorded_monotonic=time.monotonic(),recorded_utc=time.time(),armed=False)
            row=(packet['request_id'],binding,self.store.lease.generation,canonical(result).decode())
            changed=self.db.execute('INSERT INTO fake_operator_requests VALUES(?,?,?,?)',row)
            observed=self.db.execute('SELECT CASE WHEN length(binding)=64 THEN binding ELSE NULL END,generation,CASE WHEN length(result)<=8192 THEN result ELSE NULL END FROM fake_operator_requests WHERE request_id=?',(packet['request_id'],)).fetchone()
            if changed.rowcount!=1 or observed!=row[1:] or self._read_state()!=state:raise RuntimeRefused('OPERATOR_WRITE_UNVERIFIED')
            return result

    def _resume(self,packet):
        """Fresh fake reconciliation clears only operator halt, never arming."""
        from .execution_plan_owner import SavedPlanOwner
        from .execution_risk import control_health
        binding=hashlib.sha256(canonical(packet)).hexdigest()
        with self.store._live():
            if self.plan_owner is None:self.plan_owner=SavedPlanOwner(self)
            old=self.plan_owner._request(packet,binding)
            if old is not None:return old
            if self.db.execute('SELECT count(*) FROM fake_operator_requests').fetchone()[0]>=MAX_REQUESTS:raise RuntimeRefused('OPERATOR_REQUEST_BOUND')
            def saved_epoch():
                try:self.plan_owner._schema(create=False)
                except RuntimeRefused as error:
                    if error.code!='PLAN_NOT_FOUND':raise
                    return None
                return self.plan_epoch()
            epoch=saved_epoch()
            observation,context=self.plan_owner.observations.read()
            current=self.observation_context()
            if any(current[k]!=context[k] for k in ('owner_instance','generation','session_id','profile_sha256')):raise RuntimeRefused('SESSION_INPUTS_CHANGED')
            reasons=control_health(observation,now=current['market_at'],calendar=context['calendar'])
            if reasons:raise RuntimeRefused(reasons[0])
            o=observation.to_payload();at=instant(current['market_at'])
            if not instant(o['clock']['session_open_at'])<=at<instant(o['clock']['session_close_at']):raise RuntimeRefused('REGULAR_SESSION_REQUIRED')
            def fresh(state):
                # Pure time checks only: transaction-owning helpers must not run
                # between the transition writes and their atomic commit.
                if state['ack_mono'] is None or not(0<=time.monotonic()-state['ack_mono']<=300 and 0<=time.time()-state['ack_utc']<=300):raise RuntimeRefused('SUPERVISION_EXPIRED')
                now=self._market_at(state,context['profile'])
                causes=control_health(observation,now=now,calendar=context['calendar'])
                if causes:raise RuntimeRefused(causes[0])
                if not instant(o['clock']['session_open_at'])<=instant(now)<instant(o['clock']['session_close_at']):raise RuntimeRefused('REGULAR_SESSION_REQUIRED')
            with self.db:
                state=self._read_state()
                if state['owner_instance']!=current['owner_instance'] or state['owner_generation']!=current['generation'] or state['session_id']!=current['session_id']:raise RuntimeRefused('SESSION_INPUTS_CHANGED')
                if saved_epoch()!=epoch:raise RuntimeRefused('PLAN_CONTEXT_CHANGED')
                fresh(state)
                if epoch is not None:self._state_value('fake_plan_epoch',epoch+1)
                state.update(halted=False,armed=False,reason='RESUMED_DISARMED');self._write(state)
                result=dict(scope='DETERMINISTIC_FAKE',financial_accepted=False,receipt_only=True,effects_enabled=False,operation='resume',request_id=packet['request_id'],
                    generation=self.store.lease.generation,owner_instance=self.store.lease.identity.process_instance_id,session_id=state['session_id'],
                    recorded_monotonic=time.monotonic(),recorded_utc=time.time(),armed=False,halted=False,admission='DISARMED',observation_sha256=record_sha256(observation),reconciled_at=o['account']['reconciled_at'])
                self.plan_owner._save_request(packet,binding,result)
                if self._read_state()!=state:raise RuntimeRefused('OPERATOR_WRITE_UNVERIFIED')
                fresh(state)
                return result
