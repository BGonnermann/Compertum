"""Coordinator-owned saved synthetic replays, checkpointed between complete units."""
from datetime import datetime,timezone
import hashlib
import json,os
from pathlib import Path

from compertum.data.errors import DataError
from compertum.data.encoding import canonical
from compertum.events import uuid
from compertum.persistence import checked_path
from compertum.recovery import _package_hash
from . import replay
from .policy import fixed_decimal

MIB=1024*1024
UNITS=tuple((h,c) for c in (10,20) for h in (1,5,21))
TERMINAL={'COMPLETED','STOPPED','FAILED'}


def unit_schedule(state):
    if state.get('input_kind')=='synthetic-campaign':
        from compertum.campaign_contract import UNITS as campaign_units
        return campaign_units
    return UNITS+tuple((h,None) for h in (1,5,21)) if state.get('scoring_as_of') is not None else UNITS


def attempt_seconds(state):return 90 if state.get('scoring_as_of') is not None else 120


from compertum.runtime.identity_pins import runtime_identity


def compute_unit(bundle,index):
    """Shared trusted compute for owner-held steps and inherited-handle workers."""
    h,cost=unit_schedule(bundle)[index]
    kind=bundle.get('input_kind','synthetic')
    if kind=='provider-diagnostic':
        from compertum.data.alpaca import read_bar_evidence
        from compertum.data.provider_snapshot import build_provider_snapshot
        from .provider_replay import read_scenario,replay_provider
        if bundle.get('schema_version')!='provider-diagnostic-v1' or cost is None or bundle.get('scoring_as_of') is not None:raise DataError('RUN_INPUT_KIND')
        evidence=bundle['provider_evidence_utf8']
        if not isinstance(evidence,list) or not 1<=len(evidence)<=64:raise DataError('INPUT_BOUND')
        if any(not isinstance(v,str) for v in evidence):raise DataError('RUN_INPUT_KIND')
        chunks=tuple(read_bar_evidence(v.encode('utf-8')) for v in evidence)
        snapshot=build_provider_snapshot(chunks,start=bundle['start'],end=bundle['end'],feed='sip')
        if snapshot.sha256!=bundle['snapshot_sha256']:raise DataError('RUN_ARTIFACT_CORRUPT')
        return replay_provider(snapshot,read_scenario(canonical(bundle['scenario'])),h,cost_bps=cost)
    if kind!='synthetic':raise DataError('RUN_INPUT_KIND')
    from compertum.data.snapshot import validate_snapshot
    chunks=tuple(validate_snapshot(canonical(v)) for v in bundle['snapshots'])
    if cost is None:
        from .prediction import score_predictions
        return score_predictions(chunks,bundle['sectors'],bundle['start'],bundle['end'],h,scoring_as_of=bundle['scoring_as_of'])
    return replay(chunks,bundle['sectors'],bundle['start'],bundle['end'],h,cost_bps=cost)


class SavedRuns:
    """Each public operation holds the native coordinator guard.

    step is synchronous. Pause/stop are acknowledged only between whole replays.
    No method starts threads, processes, providers, services or automatic retries.
    """
    def __init__(self,storage):
        self.storage=storage;self.store=storage.store
        self.owner=storage.lease.identity.process_instance_id
        from compertum.development_seals import initialize
        initialize(self.store)
        from compertum.clean_registration import initialize as initialize_pairs
        initialize_pairs(self.store)
        with self.store._live(),self.store.conn:
            self.store.conn.executescript('''
                CREATE TABLE IF NOT EXISTS baseline_runs(run_id TEXT PRIMARY KEY,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS baseline_history(run_id TEXT NOT NULL,seq INTEGER NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(run_id,seq));
                CREATE TABLE IF NOT EXISTS baseline_controls(run_id TEXT NOT NULL,request_id TEXT NOT NULL,action TEXT NOT NULL,receipt TEXT NOT NULL,PRIMARY KEY(run_id,request_id));
            ''')
            for (run_id,) in self.store.conn.execute('SELECT run_id FROM baseline_runs').fetchall():
                # Verify the last committed checkpoint before changing recovery state.
                # Never make a corrupt body valid by attaching a fresh history hash.
                state=self._load(run_id)
                if state['state'] in ('RUNNING','PREPARING') and state['active_owner']!=self.owner:
                    state['state']='INTERRUPTED' if state['input_artifact'] else 'FAILED'
                    if state['attempts'] and state['attempts'][-1]['status']=='RUNNING':
                        state['attempts'][-1].update(status='INTERRUPTED',reason='OWNER_RESTART')
                    self._save(state,'OWNER_RESTART')

    def _load(self,run_id):
        uuid(run_id)
        row=self.store.conn.execute('SELECT body FROM baseline_runs WHERE run_id=?',(run_id,)).fetchone()
        if row is None:raise DataError('RUN_NOT_FOUND')
        raw=row[0]
        if len(raw)>512*1024:raise DataError('RUN_STATE_CORRUPT')
        state=json.loads(raw)
        if state.get('input_kind')=='synthetic-campaign':
            from .campaign_runs import validate_state
            validate_state(state)
        elif len(raw)>128*1024:raise DataError('RUN_STATE_CORRUPT')
        latest=self.store.conn.execute('SELECT sha256 FROM baseline_history WHERE run_id=? ORDER BY seq DESC LIMIT 1',(run_id,)).fetchone()
        if latest is None or hashlib.sha256(raw.encode()).hexdigest()!=latest[0]:raise DataError('RUN_STATE_CORRUPT')
        return state

    def _save(self,state,reason):
        state['updated_at']=datetime.now(timezone.utc).isoformat();state['last_transition']=reason
        raw=canonical(state);campaign=state.get('input_kind')=='synthetic-campaign';history_raw=raw
        if campaign:
            from .campaign_runs import validate_state,history_delta
            validate_state(state)
            row=self.store.conn.execute('SELECT body FROM baseline_runs WHERE run_id=?',(state['run_id'],)).fetchone()
            history_raw=history_delta(json.loads(row[0]) if row else None,state)
        if len(raw)>(512 if campaign else 128)*1024:raise DataError('RUN_STATE_BOUND')
        seq=self.store.conn.execute('SELECT count(*) FROM baseline_history WHERE run_id=?',(state['run_id'],)).fetchone()[0]+1
        if seq>(1024 if campaign else 256):raise DataError('RUN_HISTORY_BOUND')
        self.store.conn.execute('INSERT INTO baseline_runs VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET body=excluded.body',(state['run_id'],raw.decode()))
        self.store.conn.execute('INSERT INTO baseline_history VALUES(?,?,?,?)',(state['run_id'],seq,history_raw.decode(),hashlib.sha256(raw).hexdigest()))

    def _view(self,state):
        if state.get('input_kind')=='synthetic-campaign':
            from .campaign_runs import view
            return view(state)
        return {'run_id':state['run_id'],'state':state['state'],'completed_units':len(state['results']),
            'total_units':len(unit_schedule(state)),'results':state['results'],'attempts':state['attempts'],'input_artifact':state['input_artifact'],
            'scoring_as_of':state.get('scoring_as_of'),
            'request_sha256':state['request_sha256'],'maximum_bytes':state['maximum_bytes'],'last_transition':state['last_transition'],
            **({'input_kind':state['input_kind']} if 'input_kind' in state else {}),
            'financial_acceptance':'UNVERIFIED','control_boundary':'BETWEEN_COMPLETE_REPLAYS'}

    def _read(self,run_id,artifact,maximum):
        size=artifact['size_bytes'];relative=artifact['path']
        if type(size) is not int or not 0<size<=maximum or not relative.startswith(f'artifacts/runs/{run_id}/baseline/'):
            raise DataError('RUN_ARTIFACT_CORRUPT')
        path=checked_path(self.storage.root,self.storage.root/relative)
        try:
            with path.open('rb') as f:
                if os.fstat(f.fileno()).st_size!=size:raise DataError('RUN_ARTIFACT_CORRUPT')
                raw=f.read(size+1)
        except OSError:raise DataError('RUN_ARTIFACT_CORRUPT') from None
        if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=artifact['sha256']:raise DataError('RUN_ARTIFACT_CORRUPT')
        return raw

    def _verify(self,state,*,decode=True):
        from compertum.development_seals import check_campaign_seal
        check_campaign_seal(self.store,state)
        if state['identity']!=json.loads(canonical(runtime_identity())):raise DataError('RUN_IDENTITY_CHANGED')
        if state['input_artifact'] is None:raise DataError('RUN_INPUT_INCOMPLETE')
        raw=self._read(state['run_id'],state['input_artifact'],20*MIB)
        if hashlib.sha256(raw).hexdigest()!=state['request_sha256']:raise DataError('RUN_ARTIFACT_CORRUPT')
        if state.get('input_kind')=='synthetic-campaign':
            from .campaign_runs import verify
            return verify(self,state,raw,decode=decode)
        for index,result in enumerate(state['results']):
            if (result['horizon'],result['cost_bps'])!=unit_schedule(state)[index]:raise DataError('RUN_STATE_CORRUPT')
            self._read(state['run_id'],result['artifact'],16*MIB)
        return json.loads(raw) if decode else None

    def _publish(self,state,name,raw):
        # A crash may persist bytes before SQLite records writer.written. Keep the
        # entire allowance charged for abandoned/open reservations, including orphans.
        used=self.store.conn.execute("SELECT COALESCE(sum(CASE WHEN status='PUBLISHED' THEN written ELSE maximum END),0) FROM reservations WHERE task=? AND category='records' AND status!='SPLIT'",(state['run_id'],)).fetchone()[0]
        if used+len(raw)>state['maximum_bytes']:raise DataError('RUN_BUDGET')
        relative=f"artifacts/runs/{state['run_id']}/baseline/{name}"
        if checked_path(self.storage.root,self.storage.root/relative).exists():raise DataError('RUN_OUTPUT_EXISTS')
        grant=self.storage.reserve_bytes(state['run_id'],'records',len(raw))
        writer=self.storage.open_artifact(grant,relative)
        try:
            for offset in range(0,len(raw),8*MIB):writer.write(raw[offset:offset+8*MIB])
            artifact=writer.publish()
        finally:writer.close()
        self._read(state['run_id'],artifact,max(20*MIB,len(raw)))
        return artifact

    @fixed_decimal
    def create(self,run_id,chunks,sectors,start,end,*,maximum_bytes=64*MIB,scoring_as_of=None):
        from compertum.data.calendar import session_times,utc_time
        from .market import load_market
        uuid(run_id)
        if type(maximum_bytes) is not int or not 1<=maximum_bytes<=128*MIB:raise DataError('RUN_BUDGET')
        session_times(start);session_times(end)
        if scoring_as_of is not None:scoring_as_of=utc_time(scoring_as_of).isoformat()
        if end<start:raise DataError('INVALID_SEGMENT')
        dates=start
        for count in range(1024):
            if dates==end:break
            dates=session_times(dates).next_date
        else:raise DataError('INPUT_BOUND')
        market=load_market(chunks,sectors)
        bundle={'schema_version':'1','identity':runtime_identity(),'market_sha256':market.sha256,
            'snapshots':[json.loads(c.content) for c in sorted(chunks,key=lambda c:c.sha256)],
            'sectors':sectors,'start':start,'end':end,'units':UNITS,'maximum_bytes':maximum_bytes}
        if scoring_as_of is not None:
            bundle.update(schema_version='2',scoring_as_of=scoring_as_of)
            bundle['units']=unit_schedule(bundle)
        raw=canonical(bundle)
        if len(raw)>20*MIB:raise DataError('INPUT_BOUND')
        if len(raw)>maximum_bytes:raise DataError('RUN_BUDGET')
        return self._register(run_id,bundle,raw,maximum_bytes,scoring_as_of)

    @fixed_decimal
    def create_provider(self,run_id,snapshot,scenario,*,maximum_bytes=64*MIB):
        from .provider_replay import load_provider_market
        uuid(run_id)
        if type(maximum_bytes) is not int or not 1<=maximum_bytes<=128*MIB:raise DataError('RUN_BUDGET')
        market=load_provider_market(snapshot,scenario)
        bundle={'schema_version':'provider-diagnostic-v1','input_kind':'provider-diagnostic','identity':runtime_identity(),
            'market_sha256':market.sha256,'snapshot_sha256':snapshot.sha256,
            'provider_evidence_utf8':[c.content.decode('utf-8') for c in sorted(snapshot.evidence,key=lambda c:c.sha256)],
            'scenario':json.loads(scenario.content),'start':snapshot.start,'end':snapshot.end,'units':UNITS,'maximum_bytes':maximum_bytes}
        raw=canonical(bundle)
        if len(raw)>20*MIB:raise DataError('INPUT_BOUND')
        if len(raw)>maximum_bytes:raise DataError('RUN_BUDGET')
        return self._register(run_id,bundle,raw,maximum_bytes,None)

    def _register(self,run_id,bundle,raw,maximum_bytes,scoring_as_of,*,seal_binding=None):
        request_hash=hashlib.sha256(raw).hexdigest()
        with self.store._live():
            from compertum.development_seals import check_campaign_seal
            candidate={'run_id':run_id,'request_sha256':request_hash,'identity':json.loads(canonical(bundle['identity'])),'input_kind':bundle.get('input_kind')}
            if seal_binding is not None:candidate['protocol_seal']=seal_binding
            from compertum.development_seals import expected_environment
            clean=expected_environment(self.store,run_id)
            if clean is not None:candidate['clean_environment']=clean
            check_campaign_seal(self.store,candidate)
            if self.store.conn.execute('SELECT 1 FROM baseline_runs WHERE run_id=?',(run_id,)).fetchone():
                state=self._load(run_id)
                if state['request_sha256']!=request_hash or state.get('protocol_seal')!=seal_binding:raise DataError('RUN_CONFLICT')
                self._verify(state);return self._view(state)
            if self.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0]>=128:raise DataError('RUN_COUNT_BOUND')
            state={'run_id':run_id,'state':'PREPARING','active_owner':self.owner,'request_sha256':request_hash,
                'identity':json.loads(canonical(bundle['identity'])),'maximum_bytes':maximum_bytes,
                'input_artifact':None,'attempts':[],'results':[]}
            if seal_binding is not None:state['protocol_seal']=dict(seal_binding)
            if clean is not None:state['clean_environment']=clean
            if scoring_as_of is not None:state['scoring_as_of']=scoring_as_of
            if bundle.get('input_kind')=='provider-diagnostic':state['input_kind']='provider-diagnostic'
            if bundle.get('input_kind')=='synthetic-campaign':state.update(input_kind='synthetic-campaign',campaign_version=1,outcomes={})
            with self.store.conn:self._save(state,'REGISTERED')
            try:
                state['input_artifact']=self._publish(state,'inputs.json',raw);state['state']='PAUSED'
                with self.store.conn:self._save(state,'INPUTS_PUBLISHED')
            except Exception:
                # Preserve any orphan; never register a partial input as resumable.
                state['input_artifact']=None;state['state']='FAILED'
                with self.store.conn:self._save(state,'PREPARATION_FAILED')
                raise DataError('RUN_PREPARATION_FAILED') from None
            return self._view(state)

    def status(self,run_id):
        with self.store._live():
            state=self._load(run_id)
            if state['state'] not in ('FAILED','STOPPED'):self._verify(state)
            return self._view(state)

    def summary(self,run_id):
        """Verified ledger metadata only; no claim of a fresh artifact audit."""
        with self.store._live():return self._view(self._load(run_id))

    def begin(self,run_id):
        """Register one attempt before handing its immutable input to a worker."""
        with self.store._live():
            state=self._load(run_id)
            if state['state']!='READY':raise DataError('RUN_NOT_READY')
            if state.get('input_kind')=='synthetic-campaign':
                from .campaign_runs import prepare,begin
                return begin(self,run_id,prepare(self,run_id))
            self._verify(state,decode=False);index=len(state['results'])
            attempts=sum(a['unit']==index for a in state['attempts'])
            if attempts>=2:raise DataError('RUN_ATTEMPT_BOUND')
            attempt={'unit':index,'attempt':attempts+1,'status':'RUNNING'}
            state['attempts'].append(attempt);state['state']='RUNNING';state['active_owner']=self.owner
            with self.store.conn:self._save(state,'UNIT_STARTED')
            return {**attempt,'input_artifact':state['input_artifact'],'request_sha256':state['request_sha256']}

    def accept(self,run_id,artifact,*,_verification=None):
        """Accept only the current attempt's immutable, coordinator-published sink."""
        with self.store._live():
            state=self._load(run_id)
            if state['state']!='RUNNING' or state['active_owner']!=self.owner:raise DataError('RUN_NOT_RUNNING')
            if state.get('input_kind')=='synthetic-campaign':
                from .campaign_runs import accept
                return accept(self,run_id,artifact,_verification=_verification)
            attempt=state['attempts'][-1];index=attempt['unit']
            h,cost=unit_schedule(state)[index];suffix='prediction' if cost is None else 'replay'
            expected=f"artifacts/runs/{run_id}/baseline/unit-{index:02}-attempt-{attempt['attempt']}.{suffix}"
            if artifact.get('path')!=expected:raise DataError('RUN_ARTIFACT_CORRUPT')
            row=self.store.conn.execute("SELECT manifest FROM reservations WHERE task=? AND status='PUBLISHED' AND path=?",(run_id,expected)).fetchone()
            if row is None or json.loads(row[0])!=artifact:raise DataError('RUN_ARTIFACT_CORRUPT')
            from .worker_record import verify_result
            verify_result(self._read(run_id,artifact,16*MIB),state['request_sha256'],h,cost,scoring_as_of=state.get('scoring_as_of'),input_kind=state.get('input_kind','synthetic'))
            state['results'].append({'unit':index,'horizon':h,'cost_bps':cost,'artifact':artifact})
            attempt['status']='COMPLETED';state['state']='COMPLETED' if len(state['results'])==len(unit_schedule(state)) else 'READY'
            with self.store.conn:self._save(state,'UNIT_CHECKPOINTED')
            return self._view(state)

    def interrupt(self,run_id,reason,*,terminal=False):
        if reason not in {'OPERATOR_PAUSE','WORKER_FAILED','JOB_TIMEOUT','LAUNCH_FAILED','HEALTH_HALT'}:raise DataError('CONTROL_INVALID')
        with self.store._live():
            state=self._load(run_id)
            if state['state']!='RUNNING' or state['active_owner']!=self.owner:raise DataError('RUN_NOT_RUNNING')
            if state.get('input_kind')=='synthetic-campaign':
                from .campaign_runs import interrupt
                return interrupt(self,run_id,reason,terminal=terminal)
            state['state']='FAILED' if terminal else 'INTERRUPTED'
            state['attempts'][-1].update(status=state['state'],reason=reason)
            with self.store.conn:self._save(state,'UNIT_'+state['state'])
            return self._view(state)

    def control(self,run_id,request_id,action):
        uuid(run_id);uuid(request_id)
        if action not in ('pause','resume','stop'):raise DataError('CONTROL_INVALID')
        with self.store._live():
            old=self.store.conn.execute('SELECT action,receipt FROM baseline_controls WHERE run_id=? AND request_id=?',(run_id,request_id)).fetchone()
            if old:
                if old[0]!=action:raise DataError('CONTROL_CONFLICT')
                return json.loads(old[1])
            state=self._load(run_id)
            if self.store.conn.execute('SELECT count(*) FROM baseline_controls WHERE run_id=?',(run_id,)).fetchone()[0]>=128:raise DataError('CONTROL_BOUND')
            if state['state'] in TERMINAL:raise DataError('RUN_TERMINAL')
            if state['state'] in ('RUNNING','PREPARING'):raise DataError('RUN_BUSY')
            if state.get('input_kind')=='synthetic-campaign':
                from .campaign_runs import control
                return control(self,run_id,request_id,action,state)
            if action=='resume':
                self._verify(state,decode=False);state['state']='READY'
            elif action=='pause':state['state']='PAUSED'
            else:state['state']='STOPPED'
            with self.store.conn:
                self._save(state,action.upper());receipt=self._view(state)
                self.store.conn.execute('INSERT INTO baseline_controls VALUES(?,?,?,?)',(run_id,request_id,action,canonical(receipt).decode()))
            return receipt

    def step(self,run_id):
        with self.store._live():
            state=self._load(run_id)
            if state.get('input_kind')=='synthetic-campaign':
                from .campaign_runs import step
                return step(self,run_id)
            from compertum.data.snapshot import validate_snapshot
            if state['state']=='COMPLETED':self._verify(state);return self._view(state)
            if state['state']!='READY':raise DataError('RUN_NOT_READY')
            bundle=self._verify(state);index=len(state['results'])
            attempts=sum(a['unit']==index for a in state['attempts'])
            if attempts>=2:raise DataError('RUN_ATTEMPT_BOUND')
            attempt={'unit':index,'attempt':attempts+1,'status':'RUNNING'}
            state['attempts'].append(attempt);state['state']='RUNNING';state['active_owner']=self.owner
            with self.store.conn:self._save(state,'UNIT_STARTED')
            try:
                h,cost=unit_schedule(state)[index]
                result=compute_unit(bundle,index)
                artifact=self._publish(state,f'unit-{index:02}-attempt-{attempts+1}.json',result.content)
                state['results'].append({'unit':index,'horizon':h,'cost_bps':cost,'artifact':artifact})
                attempt['status']='COMPLETED';state['state']='COMPLETED' if len(state['results'])==len(unit_schedule(state)) else 'READY'
                with self.store.conn:self._save(state,'UNIT_CHECKPOINTED')
            except Exception as error:
                # Reload committed checkpoint: a failed final commit must not retain
                # a result only present in the in-memory object.
                # Only an I/O interruption is eligible for an explicit retry.
                # Invalid data, exhausted budgets and unknown compute errors stop.
                status='INTERRUPTED' if isinstance(error,OSError) else 'FAILED'
                state=self._load(run_id);state['state']=status
                state['attempts'][-1].update(status=status,reason=error.code if isinstance(error,DataError) else 'UNIT_FAILED')
                with self.store.conn:self._save(state,'UNIT_'+status)
                raise DataError('RUN_'+status) from None
            return self._view(state)


    def create_campaign(self,run_id,folds,*,maximum_bytes=128*MIB):
        from .campaign_runs import create
        return create(self,run_id,folds,maximum_bytes)

    def prepare_campaign(self,run_id,*,_verification=None):
        from .campaign_runs import prepare
        return prepare(self,run_id,_verification=_verification)

    def begin_campaign(self,run_id,prepared,*,reservation_id=None,_verification=None):
        from .campaign_runs import begin
        return begin(self,run_id,prepared,reservation_id=reservation_id,_verification=_verification)

    def campaign_scorecard(self,run_id):
        from .campaign_runs import scorecard
        return scorecard(self,run_id)
