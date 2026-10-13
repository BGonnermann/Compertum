"""Mutual owner liveness, relayed only over the inherited supervisor channels."""
from dataclasses import asdict
import math
import time
from .owners import _owner_scope,_metadata
from .errors import RuntimeRefused


class MutualHealth:
    def __init__(self,lease,on_halt,*,required):
        if lease.identity.role not in {'execution','watchdog'}:raise RuntimeRefused('WRONG_OWNER_ROLE')
        self.lease=lease;self.on_halt=on_halt;self.required=required
        self.peer_role='watchdog' if lease.identity.role=='execution' else 'execution'
        self.peer=None;self.peer_sequence=0;self.sequence=0;self.reason=None
        self.started=self.last_mono=time.monotonic();self.last_utc=time.time();self.clock_offset=self.last_utc-self.last_mono;self.observed=None;self.observed_utc=None

    def halt(self,reason):
        if self.reason is None:
            self.reason=reason
            self.on_halt(reason)

    def _peer_live(self,identity,generation,project_id):
        with _owner_scope(self.lease) as guard:
            if project_id!=self.lease.project_id:raise RuntimeRefused('PEER_IDENTITY_CHANGED')
            actual_generation,actual=_metadata(guard.api.read_regular(guard.project.root_path/f'state/locks/{self.peer_role}.json'),guard.project,self.peer_role)
            expected=asdict(actual)
            if (type(generation) is not int or actual_generation!=generation or type(identity) is not dict or set(identity)!=set(expected)
                or any(type(identity[k]) is not type(v) or identity[k]!=v for k,v in expected.items())):raise RuntimeRefused('PEER_IDENTITY_CHANGED')
            with guard.api.open_process(actual.pid) as process:
                if (guard.api.creation_time(process)!=actual.creation_filetime or guard.api.WaitForSingleObject(process.get(),0)!=258
                    or guard.api.token_sids(process)!=(guard.project.operator_sid,guard.project.logon_sid)):
                    raise RuntimeRefused('PEER_IDENTITY_CHANGED')

    def tick(self):
        with _owner_scope(self.lease):
            mono=time.monotonic();utc=time.time();dm=mono-self.last_mono;du=utc-self.last_utc
            self.last_mono=mono;self.last_utc=utc
            if dm<0 or du<0:self.halt('CLOCK_REVERSED')
            elif dm>15 or du>15:self.halt('ELAPSED_CLOCK_GAP')
            elif abs((utc-mono)-self.clock_offset)>5:self.halt('CLOCK_MISMATCH')
            if self.required and mono-(self.observed if self.observed is not None else self.started)>15:self.halt('PEER_HEARTBEAT_STALE')
            if self.peer is not None:
                try:self._peer_live(*self.peer)
                except RuntimeRefused:self.halt('PEER_UNAVAILABLE')

    def receive(self,payload):
        """Caller must be the native-bound supervisor RPC handler, never public control."""
        self.tick()
        try:
            keys={'schema','identity','generation','project_id','sequence','observed_monotonic','observed_utc','healthy'}
            if type(payload) is not dict or set(payload)!=keys or payload['schema']!='mutual-owner-health-v1' or type(payload['healthy']) is not bool:
                raise RuntimeRefused('HEARTBEAT_INVALID')
            for key in ('observed_monotonic','observed_utc'):
                if type(payload[key]) not in (int,float) or not math.isfinite(payload[key]):raise RuntimeRefused('HEARTBEAT_INVALID')
            if type(payload['sequence']) is not int or not 1<=payload['sequence']<=2**63-1:raise RuntimeRefused('HEARTBEAT_INVALID')
            if not(0<=time.monotonic()-payload['observed_monotonic']<=15 and 0<=time.time()-payload['observed_utc']<=15):raise RuntimeRefused('HEARTBEAT_STALE')
            peer=(payload['identity'],payload['generation'],payload['project_id'])
            self._peer_live(*peer)
            if self.peer is not None and self.peer!=peer:raise RuntimeRefused('PEER_IDENTITY_CHANGED')
            if payload['sequence']<=self.peer_sequence:raise RuntimeRefused('HEARTBEAT_REPLAY')
            if self.observed is not None and (payload['observed_monotonic']<self.observed or payload['observed_utc']<self.observed_utc):raise RuntimeRefused('HEARTBEAT_REORDERED')
            # Retain original owner measurement time; relay delay never renews it.
            self.peer=(dict(payload['identity']),payload['generation'],payload['project_id']);self.peer_sequence=payload['sequence']
            self.observed=payload['observed_monotonic'];self.observed_utc=payload['observed_utc'];self.required=True
            if not payload['healthy']:self.halt('PEER_UNHEALTHY')
        except RuntimeRefused as error:
            self.halt(error.code);raise
        return self.status()

    def status(self):
        self.tick()
        return {'verified':self.peer is not None and self.reason is None,'reason':self.reason,'peer_role':self.peer_role,
                'peer_generation':self.peer[1] if self.peer else None,'peer_observed_monotonic':self.observed}

    def receipt(self,*,healthy=True):
        self.tick();self.sequence+=1
        return {'schema':'mutual-owner-health-v1','identity':asdict(self.lease.identity),'generation':self.lease.generation,
                'project_id':self.lease.project_id,'sequence':self.sequence,'observed_monotonic':time.monotonic(),
                'observed_utc':time.time(),'healthy':healthy and self.reason is None}


def disarm_execution(store,reason):
    with store._live(),store.conn:
        from compertum.events import canonical
        for key,value in (('admission','HALTED'),('armed',False),('approved_plan',None),('execution_health_halt',reason)):
            store.conn.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,canonical(value).decode()))


def execution_durable(store,reserve):
    """Actual handles and SQLite settings; no supplied readiness flags."""
    with store._live():
        r=reserve.receipt()
        if (r['capacity_bytes']!=1024**3 or r['unused_bytes']<256*1024**2 or r['allocated_bytes']<r['unused_bytes'] or r['sparse'] is not False):
            raise RuntimeRefused('JOURNAL_UNRESERVED')
        if store.conn.execute('PRAGMA journal_mode').fetchone()[0]!='wal' or store.conn.execute('PRAGMA synchronous').fetchone()[0]!=2:
            raise RuntimeRefused('DURABILITY_UNVERIFIED')
        return r
