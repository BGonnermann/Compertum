"""Research-only durable coordinator. No broker or provider transport."""
from datetime import datetime,timezone
import json
import time
from .domain import validate_record
from .events import canonical
from .runtime.errors import RuntimeRefused
from .runtime.owners import require_live_owner

CONTROL_ACTIONS=frozenset({'pause_research','resume_research','stop_research','shutdown','checkpoint'})

def utc_now(): return datetime.now(timezone.utc).isoformat()

class Coordinator:
    def __init__(self,store,*,health=None,refresh_health=None,halt=None,checkpoint=None,stop_run=None):
        require_live_owner(store.lease,'coordinator')
        self.store=store;self.health=health;self.refresh_health=refresh_health;self.halt=halt;self.checkpoint=checkpoint;self.stop_run=stop_run
        with store._live(),store.conn:
            store.conn.execute('''CREATE TABLE IF NOT EXISTS control_requests(
                request_id TEXT PRIMARY KEY,subject TEXT NOT NULL,payload_hash TEXT NOT NULL,
                generation INTEGER NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL,receipt TEXT NOT NULL)''')
            # Every start is paused, including a restart with an old RUNNING record.
            self._state('research_state','PAUSED')

    def _state(self,key,value):
        self.store.conn.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,canonical(value).decode()))

    def status(self):
        with self.store._live():
            return {'research_state':self.store.get_state('research_state') or 'PAUSED',
                    'broker_state':'NOT_CONFIGURED','strategy_state':'NOT_EVALUATED',
                    'order_admission':'DISARMED','execution_process':'NOT_ACTIVE',
                    'generation':self.store.lease.generation,'attempts':self.store.attempts()}

    def require_health(self,*,refresh=False):
        if refresh and self.refresh_health is not None:self.refresh_health()
        if self.health is None: raise RuntimeRefused('HEALTH_UNVERIFIED')
        result=self.health()
        if (result.get('status')!='HEALTHY' or not isinstance(result.get('observed_monotonic'),(int,float))
                or not 0<=time.monotonic()-result['observed_monotonic']<=5):
            raise RuntimeRefused('HEALTH_UNVERIFIED')
        return result

    def register_reviewed_campaign(self, decision, payload, *, controller, bridge, prepared_raw, evaluation):
        """Register exact reviewed inputs, paused. Execution needs its own control."""
        from .ai.registration import register
        return register(self, decision, payload, controller=controller, bridge=bridge,
            prepared_raw=prepared_raw, evaluation=evaluation)

    def start_reviewed_campaign(self, decision, payload, *, controller):
        """Start one approved first unit. Repeated requests never dispatch again."""
        from .ai.start import start
        return start(self, decision, payload, controller=controller)

    def control_research_cycle(self, decision, payload, *, cycle):
        """Apply an authenticated cycle decision without widening transport access."""
        from .ai.cycle import ResearchCycleController
        if not isinstance(cycle, ResearchCycleController) or cycle.coordinator is not self:
            raise RuntimeRefused('CYCLE_OWNER_MISMATCH')
        return cycle.control(decision, payload)

    def control(self,decision,action,payload):
        if action not in CONTROL_ACTIONS: raise RuntimeRefused('COMMAND_DENIED')
        if not isinstance(payload,dict): raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        if payload:
            if action=='pause_research' and set(payload)=={'reason'} and isinstance(payload['reason'],str) and 1<=len(payload['reason'])<=256: pass
            elif action=='stop_research' and set(payload)=={'run_id'}:
                from .events import uuid
                uuid(payload['run_id'])
            else: raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        with self.store._live():
            binding=(decision.subject_key,decision.payload_hash,decision.target_generation,action,canonical(payload).decode())
            old=self.store.conn.execute('SELECT subject,payload_hash,generation,action,payload,receipt FROM control_requests WHERE request_id=?',(decision.request_id,)).fetchone()
            if old:
                if old[:5]!=binding: raise RuntimeRefused('REQUEST_CONFLICT')
                return json.loads(old[5])
            if self.store.conn.execute('SELECT count(*) FROM control_requests').fetchone()[0]>=10000:
                raise RuntimeRefused('CONTROL_LEDGER_FULL')
            artifacts=[]
            if action=='resume_research': self.require_health();state='RUNNING';reason='RESEARCH_RESUMED'
            else:
                # Stop verified native children before claiming the effect. A crash
                # between stop and commit leaves the same conservative pause intent.
                if action=='stop_research' and payload:
                    if self.stop_run is None: raise RuntimeRefused('RUN_STOP_UNAVAILABLE')
                    self.stop_run(payload['run_id'])
                elif self.halt is not None: self.halt(action)
                state='STOPPED' if action in {'shutdown','stop_research'} else 'PAUSED'
                reason={'pause_research':'RESEARCH_PAUSED','stop_research':'RESEARCH_STOPPED','shutdown':'SHUTDOWN_CHECKPOINTED','checkpoint':'CHECKPOINT_PUBLISHED'}[action]
                if action in {'checkpoint','shutdown'}:
                    if self.checkpoint is None: raise RuntimeRefused('CHECKPOINT_UNAVAILABLE')
                    artifacts=self.checkpoint()
            now=utc_now()
            receipt={'schema_version':'1','record_type':'ControlReceipt','request_id':decision.request_id,
                     'action':action,'target':'research','state':'CONFIRMED','evidence_label':'VERIFIED_PASS',
                     'confirmed':True,'generation':decision.target_generation,'requested_at':now,'observed_at':now,
                     'exit_code':0,'reason':reason,'artifacts':artifacts}
            validate_record('control_receipt.v1',receipt,project_root=self.store.root)
            with self.store.conn:
                self._state('research_state',state)
                if action=='pause_research' and payload: self._state('pause_reason',payload['reason'])
                self.store.conn.execute('INSERT INTO control_requests VALUES(?,?,?,?,?,?,?)',(decision.request_id,*binding,canonical(receipt).decode()))
            return receipt
