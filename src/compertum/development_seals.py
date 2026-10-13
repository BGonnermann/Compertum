"""Fresh synthetic campaign tickets; the native evaluation ledger admits them.

Owner-facing validation stays stdlib-only. Numerical campaign imports are lazy.
"""
import hashlib
import json
import sqlite3
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import build_protocol,read_protocol,identifier,digest,MAX_PROTOCOL_BYTES
from .persistence import _active_store_path
from .runtime.errors import RuntimeRefused
from .runtime.identity_pins import runtime_identity
from .runtime.owners import require_live_owner

MAX_TICKETS=128
TICKET_FIELDS={'schema','project_id','run_id','seal_id','protocol_sha256','development_sha256','runtime_sha256'}
BINDING_FIELDS={'seal_id','protocol_sha256','ticket_sha256','admission_event_sha256'}


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def initialize(store):
    with store._live(),store.conn:
        require_live_owner(store.lease,'coordinator')
        store.conn.execute('CREATE TABLE IF NOT EXISTS sealed_campaigns(run_id TEXT PRIMARY KEY,seal_id TEXT UNIQUE NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL,protocol TEXT NOT NULL,receipt TEXT)')


def _ticket(project_id,run_id,seal_id,protocol):
    return {'schema':'synthetic-development-ticket-v1','project_id':project_id,'run_id':run_id,'seal_id':seal_id,
        'protocol_sha256':_sha(canonical(protocol)),'development_sha256':protocol['development_sha256'],
        'runtime_sha256':_sha(canonical(protocol['runtime']))}


def read_ticket(db,project,run_id):
    """Validate exact persisted pins, including the full immutable protocol."""
    try:
        row=db.execute('SELECT seal_id,body,sha256,protocol,receipt FROM sealed_campaigns WHERE run_id=?',(run_id,)).fetchone()
        if row is None:return None
        sid,body,pin,raw,receipt=row
        identifier(run_id);identifier(sid);digest(pin)
        if len(body)>2048 or len(raw)>MAX_PROTOCOL_BYTES or (receipt is not None and len(receipt)>4096):raise ValueError()
        value=json.loads(body)
        if set(value)!=TICKET_FIELDS or canonical(value).decode()!=body or _sha(body.encode())!=pin:raise ValueError()
        protocol=read_protocol(raw.encode(),expected_sha256=value['protocol_sha256'])
        if protocol['development_run_id']!=run_id or value!=_ticket(project.project_id,run_id,sid,protocol):raise ValueError()
        from .clean_registration import require_protocol
        require_protocol(db,project,protocol,sid)
        return {'body':value,'sha256':pin,'protocol':protocol,'receipt':receipt}
    except (sqlite3.Error,ValueError,TypeError,KeyError,AttributeError):
        raise DataError('DEVELOPMENT_TICKET_UNVERIFIED') from None


def owner_ticket(project,seal_id,protocol,ticket_sha256,*,fresh):
    """Evaluation independently reads the committed coordinator transaction."""
    path=_active_store_path(project.root_path,project.project_id,'coordinator')
    try:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:
            db.execute('BEGIN')
            if dict(db.execute('SELECT key,value FROM metadata'))!={'schema_version':'1','project_id':project.project_id,'role':'coordinator'}:raise ValueError()
            ticket=read_ticket(db,project,protocol['development_run_id'])
            if ticket is None or ticket['body']['seal_id']!=seal_id or ticket['sha256']!=ticket_sha256 or ticket['protocol']!=protocol:raise ValueError()
            if fresh and (db.execute('SELECT 1 FROM baseline_runs WHERE run_id=?',(protocol['development_run_id'],)).fetchone()
                    or db.execute('SELECT 1 FROM baseline_history WHERE run_id=? LIMIT 1',(protocol['development_run_id'],)).fetchone()):raise ValueError()
            return ticket
        finally:db.close()
    except (sqlite3.Error,OSError,ValueError,TypeError,KeyError):raise RuntimeRefused('DEVELOPMENT_TICKET_UNVERIFIED') from None


def _evidence(project,*,required=False):
    from .evaluation_seals import verify_seal_journal
    exists=(project.root_path/'state/evaluation-seals').exists()
    consumption=(project.root_path/'state/evaluation-consumption').exists()
    if not exists and not consumption and not required and not _active_store_path(project.root_path,project.project_id,'evaluation').exists():return None
    evidence=verify_seal_journal(project)
    if evidence['status']!='VERIFIED':raise DataError('SEAL_JOURNAL_COMPROMISED')
    from .consumption import verify_consumption_guard
    if verify_consumption_guard(project)['status']!='VERIFIED':raise DataError('EVALUATION_COMPROMISED')
    return evidence


def _mirror(project,evidence):
    path=_active_store_path(project.root_path,project.project_id,'evaluation')
    try:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:
            db.execute('BEGIN')
            if dict(db.execute('SELECT key,value FROM metadata'))!={'schema_version':'1','project_id':project.project_id,'role':'evaluation'}:raise ValueError()
            status=db.execute("SELECT value FROM state WHERE key='evaluation_status'").fetchone()
            if status and json.loads(status[0])=='EVALUATION_COMPROMISED':raise ValueError()
            rows=db.execute('SELECT sequence,sha256,body FROM evaluation_seal_events ORDER BY sequence LIMIT 257').fetchall()
            expected=[(e['sequence'],_sha(canonical(e)),canonical(e).decode()) for e in evidence['events']]
            if rows!=expected:raise ValueError()
        finally:db.close()
    except (sqlite3.Error,OSError,ValueError):raise DataError('SEAL_MIRROR_UNVERIFIED') from None


def validate_binding(binding):
    if type(binding) is not dict or set(binding)!=BINDING_FIELDS:raise DataError('SEAL_ADMISSION_REQUIRED')
    identifier(binding['seal_id'])
    for field in BINDING_FIELDS-{'seal_id'}:digest(binding[field])


def check_campaign_seal(store,state):
    """A missing field cannot downgrade a ticketed or owner-admitted run."""
    from .evaluation_seals import seal_receipt
    with store._live() as guard:
        require_live_owner(store.lease,'coordinator')
        ticket=read_ticket(store.conn,guard.project,state['run_id'])
        supplied=state.get('protocol_seal')
        evidence=_evidence(guard.project,required=ticket is not None or supplied is not None)
        member=any(r['creation']['protocol']['development_run_id']==state['run_id'] for r in evidence['seals'].values()) if evidence else False
        from .clean_registration import member_registration
        clean_member=member_registration(store.conn,guard.project,state['run_id'])
        if ticket is None and supplied is None and not member and clean_member is None:
            if state.get('clean_environment') is not None:raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED')
            return None
        if ticket is None or supplied is None:raise DataError('SEAL_ADMISSION_REQUIRED')
        validate_binding(supplied)
        if state.get('clean_environment')!=_protocol_expected(ticket['protocol']):raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED')
        sid=ticket['body']['seal_id'];row=evidence['seals'].get(sid)
        if row is None or row['creation']['protocol']!=ticket['protocol']:raise DataError('SEAL_ADMISSION_REQUIRED')
        if row['status']!='SEALED':raise DataError('SEAL_INVALIDATED')
        if not row['admission'] or row['admission']['ticket_sha256']!=ticket['sha256']:raise DataError('SEAL_ADMISSION_REQUIRED')
        receipt=seal_receipt(guard.project.project_id,evidence,sid)
        if ticket['receipt']!=canonical(receipt).decode():raise DataError('SEAL_RECEIPT_UNVERIFIED')
        binding={'seal_id':sid,'protocol_sha256':receipt['protocol_sha256'],'ticket_sha256':ticket['sha256'],
            'admission_event_sha256':receipt['admission_event_sha256']}
        if supplied!=binding or state.get('input_kind')!='synthetic-campaign' or state['request_sha256']!=receipt['development_sha256']:raise DataError('SEAL_ADMISSION_REQUIRED')
        current=json.loads(canonical(runtime_identity()))
        if state['identity']!=ticket['protocol']['runtime'] or current!=state['identity']:raise DataError('SEAL_RUNTIME_CHANGED')
        _mirror(guard.project,evidence)
        return binding


def _caller(evaluation,project):
    from .evaluation_seals import EvaluationSeals
    from .runtime.owner_channel import RemoteRoleEndpoint,_remote_scope
    from .runtime.owner_rpc import call_owner
    try:
        if type(evaluation) is EvaluationSeals:
            with evaluation.store._live() as guard:
                require_live_owner(evaluation.store.lease,'evaluation')
                if guard.project!=project:raise RuntimeRefused('SEAL_OWNER_UNVERIFIED')
            return evaluation.handle
        if type(evaluation) is RemoteRoleEndpoint:
            with _remote_scope(evaluation):
                registration=evaluation.descriptor.registration
                if registration.project_id!=project.project_id or registration.identity.role!='evaluation' or 'synthetic_protocol' not in evaluation.allowed_commands:raise RuntimeRefused('SEAL_OWNER_UNVERIFIED')
            return lambda payload:call_owner(evaluation,'synthetic_protocol',payload)
    except RuntimeRefused:raise DataError('SEAL_OWNER_UNVERIFIED') from None
    raise DataError('SEAL_OWNER_UNVERIFIED')


def create_campaign(runs,run_id,folds,*,seal_id,evaluation,data_manifest_sha256,holdout_manifest_sha256,maximum_bytes=128*1024**2):
    from .modeling.campaign import build_campaign
    from .evaluation_seals import reserve_seal_append,seal_receipt
    identifier(run_id);identifier(seal_id)
    with runs.store._live() as guard:
        require_live_owner(runs.store.lease,'coordinator');call=_caller(evaluation,guard.project)
        campaign=build_campaign(folds,identity=runtime_identity(),maximum_bytes=maximum_bytes)
        protocol=build_protocol(development_run_id=run_id,development_sha256=campaign.sha256,
            data_manifest_sha256=data_manifest_sha256,holdout_manifest_sha256=holdout_manifest_sha256,runtime=runtime_identity())
        return _admit_prepared(runs,run_id,campaign.content,protocol,seal_id=seal_id,evaluation=evaluation,maximum_bytes=maximum_bytes)


def create_prepared_campaign(runs,run_id,raw,*,expected_sha256,seal_id,evaluation):
    from .prepared_campaign import read_prepared
    from .clean_registration import read_registration,require_protocol
    identifier(run_id);identifier(seal_id)
    with runs.store._live() as guard:
        require_live_owner(runs.store.lease,'coordinator')
        bundle,pair,lane=read_prepared(raw,expected_sha256=expected_sha256,identity=runtime_identity())
        value=json.loads(pair.content)
        if read_registration(runs.store.conn,guard.project,value['pair_id'])!=pair or value[lane]['run_id']!=run_id or value[lane]['seal_id']!=seal_id:raise DataError('CLEAN_REGISTRATION_UNVERIFIED')
        protocol=build_protocol(development_run_id=run_id,development_sha256=expected_sha256,data_manifest_sha256=value['data_manifest_sha256'],holdout_manifest_sha256=value['holdout_manifest_sha256'],runtime=value['runtime'],clean_pair={'record':value,'sha256':pair.sha256,'lane':lane})
        require_protocol(runs.store.conn,guard.project,json.loads(protocol.content),seal_id)
        return _admit_prepared(runs,run_id,raw,protocol,seal_id=seal_id,evaluation=evaluation,maximum_bytes=bundle['maximum_bytes'])


def expected_environment(store,run_id):
    """Return launch expectations only from the currently committed protocol."""
    from .clean_registration import member_registration
    with store._live() as guard:
        ticket=read_ticket(store.conn,guard.project,run_id)
        member=member_registration(store.conn,guard.project,run_id)
        if ticket is None:
            if member is not None:raise DataError('CLEAN_REGISTRATION_UNVERIFIED')
            return None
        return _protocol_expected(ticket['protocol'])


def _protocol_expected(protocol):
    binding=protocol.get('clean_pair')
    if binding is None:return None
    value=binding['record'];lane=binding['lane']
    return {'schema':'expected-clean-campaign-v1','pair_sha256':binding['sha256'],'manifest_sha256':value[lane]['manifest_sha256'],'lane':lane,'run_id':protocol['development_run_id']}


def _admit_prepared(runs,run_id,raw,protocol,*,seal_id,evaluation,maximum_bytes):
    from .evaluation_seals import reserve_seal_append,seal_receipt
    from .clean_registration import require_protocol
    with runs.store._live() as guard:
        require_live_owner(runs.store.lease,'coordinator');call=_caller(evaluation,guard.project)
        require_protocol(runs.store.conn,guard.project,json.loads(protocol.content),seal_id)
        p=json.loads(protocol.content);body=canonical(_ticket(guard.project.project_id,run_id,seal_id,p));pin=_sha(body)
        old=read_ticket(runs.store.conn,guard.project,run_id)
        registered=runs.store.conn.execute('SELECT 1 FROM baseline_runs WHERE run_id=?',(run_id,)).fetchone()
        history=runs.store.conn.execute('SELECT 1 FROM baseline_history WHERE run_id=? LIMIT 1',(run_id,)).fetchone()
        if old is None:
            if registered or history:raise DataError('RUN_ALREADY_UNSEALED')
            evidence=_evidence(guard.project)
            if evidence and any(r['creation']['protocol']['development_run_id']==run_id for r in evidence['seals'].values()):raise DataError('SEAL_ADMISSION_REQUIRED')
            if runs.store.conn.execute('SELECT count(*) FROM sealed_campaigns').fetchone()[0]>=MAX_TICKETS:raise DataError('SEAL_COUNT_BOUND')
            try:
                with runs.store.conn:runs.store.conn.execute('INSERT INTO sealed_campaigns VALUES(?,?,?,?,?,NULL)',(run_id,seal_id,body.decode(),pin,protocol.content.decode()))
            except sqlite3.IntegrityError:raise DataError('SEAL_CONFLICT') from None
        elif old['body']!=json.loads(body) or old['protocol']!=p:raise DataError('SEAL_CONFLICT')
        if registered:
            state=runs._load(run_id);binding=check_campaign_seal(runs.store,state)
        else:
            try:
                reserve_seal_append(runs.storage)
                call({'operation':'create','seal_id':seal_id,'protocol_utf8':protocol.content.decode(),'protocol_sha256':protocol.sha256})
                reserve_seal_append(runs.storage)
                result=call({'operation':'admit','seal_id':seal_id,'ticket_sha256':pin})
                evidence=_evidence(guard.project,required=True)
                genuine=seal_receipt(guard.project.project_id,evidence,seal_id)
                if result!=genuine or not result['development_admitted'] or result['status']!='SEALED' or result['ticket_sha256']!=pin:raise DataError('SEAL_RECEIPT_UNVERIFIED')
                _mirror(guard.project,evidence)
                with runs.store.conn:runs.store.conn.execute('UPDATE sealed_campaigns SET receipt=? WHERE run_id=?',(canonical(result).decode(),run_id))
                binding={'seal_id':seal_id,'protocol_sha256':protocol.sha256,'ticket_sha256':pin,'admission_event_sha256':result['admission_event_sha256']}
            except (RuntimeRefused,DataError,OSError,sqlite3.Error):raise DataError('SEAL_ADMISSION_UNVERIFIED') from None
        return runs._register(run_id,json.loads(raw),raw,maximum_bytes,None,seal_binding=binding)
