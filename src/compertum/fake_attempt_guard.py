"""Fake attempt evidence outside replaceable execution SQLite snapshots.

This never grants a real effect. Missing, partial or conflicting evidence blocks
new simulated attempts; restoring an old database cannot erase a saved attempt.
"""
import hashlib,json,os
from .data.encoding import canonical
from .domain import ExecutionIntent,ExecutionDecision,ContractError
from .execution_contracts import instant,record_sha256
from .execution_risk import client_order_id
from .persistence import checked_path,StateStore
from .runtime.errors import RuntimeRefused
from .runtime.owners import require_live_owner

MAX_ATTEMPTS=256
MAX_BYTES=65536
ZERO='0'*64


def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def _directory(project):return checked_path(project.root_path,project.root_path/'state/fake-execution-attempts')


def _read(path,maximum=MAX_BYTES):
    checked_path(path.parent,path)
    with path.open('rb') as f:raw=f.read(maximum+1)
    if len(raw)>maximum:raise ValueError()
    value=json.loads(raw)
    if canonical(value)!=raw:raise ValueError()
    return value


def _flush(path,raw):
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


from .attempt_records import record_key as _records,is_paper,is_native,is_fake
from .paper_intent_records import UNCONSUMED


def _identity(project,mixed=False,native=False):
    if native:return dict(schema='execution-attempts-v3',project_id=project.project_id,
                          scope='DISJOINT_FAKE_PREPARATION_NATIVE')
    return dict(schema='execution-attempts-v2' if mixed else 'fake-execution-attempts-v1',project_id=project.project_id,
                scope='MIXED_PREPARATION_AND_FAKE' if mixed else 'DETERMINISTIC_FAKE')


def _schema(intent):
    if is_native(intent):return 'native-paper-write-attempt-v3'
    return 'paper-preparation-attempt-v2' if is_paper(intent) else 'fake-execution-attempt-v1'


def verify_attempt_guard(project):
    failed=dict(status='EXECUTION_COMPROMISED',records=[],sequence=None,sha256=None)
    try:
        path=_directory(project)
        identity=_read(path/'identity.json',1024)
        if identity not in (_identity(project),_identity(project,True),_identity(project,native=True)):raise ValueError()
        schemas={'fake-execution-attempt-v1'}
        if identity!=_identity(project):schemas.add('paper-preparation-attempt-v2')
        if identity==_identity(project,native=True):schemas.add('native-paper-write-attempt-v3')
        head=_read(path/'head.json',1024)
        if type(head) is not dict or set(head)!={'sequence','sha256'} or type(head['sequence']) is not int or not 0<=head['sequence']<=MAX_ATTEMPTS:raise ValueError()
        expected={'identity.json','head.json'}|{f'{n:08d}.json' for n in range(1,head['sequence']+1)}
        seen_names=set()
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.name not in expected or entry.name in seen_names or len(seen_names)>=MAX_ATTEMPTS+2:raise ValueError()
                seen_names.add(entry.name)
        if seen_names!=expected:raise ValueError()
        records=[];hashes=[];seen=set();prior=ZERO
        for n in range(1,head['sequence']+1):
            item=_read(path/f'{n:08d}.json')
            if type(item) is not dict or set(item)!={'schema','sequence','previous_sha256','record'} or item['schema'] not in schemas or type(item['sequence']) is not int or item['sequence']!=n or item['previous_sha256']!=prior:raise ValueError()
            key=_records(item['record'])
            if _schema(item['record']['intent'])!=item['schema']:raise ValueError()
            if not is_fake(item['record']['intent']) and item['record']['intent']['project_id']!=project.project_id:raise ValueError()
            if key in seen:raise ValueError()
            seen.add(key);records.append(item['record']);prior=_sha(item);hashes.append(prior)
        if prior!=head['sha256'] or _read(path/'head.json',1024)!=head or _read(path/'identity.json',1024)!=identity:raise ValueError()
        return dict(status='VERIFIED',records=records,sequence=len(records),sha256=prior,hashes=hashes)
    except (OSError,ValueError,TypeError,KeyError,ContractError,RuntimeRefused):return failed


def _require(store,evidence):
    if evidence['status']!='VERIFIED':raise RuntimeRefused('EXECUTION_COMPROMISED')
    mirror=store.get_state('fake_attempt_guard_head')
    if type(mirror) is not dict or set(mirror)!={'sequence','sha256'} or type(mirror['sequence']) is not int or not 0<=mirror['sequence']<=evidence['sequence']:raise RuntimeRefused('EXECUTION_COMPROMISED')
    expected=ZERO if mirror['sequence']==0 else evidence['hashes'][mirror['sequence']-1]
    if mirror['sha256']!=expected:raise RuntimeRefused('EXECUTION_COMPROMISED')
    preserved={_records(v):v for v in evidence['records']}
    for account,key,body,decision in store.conn.execute("SELECT account,intent_id,body,decision FROM fake_intents WHERE state NOT IN ('CHECKED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED','PAPER_PREPARED','PAPER_SKIPPED_RESTART','PAPER_SKIPPED_WINDOW_EXPIRED')"):
        prior=preserved.get((account,key))
        if prior is None or canonical(prior['intent']).decode()!=body or canonical(prior['decision']).decode()!=decision:raise RuntimeRefused('EXECUTION_COMPROMISED')



def _save_head(store,evidence):
    value=canonical(dict(sequence=evidence['sequence'],sha256=evidence['sha256'])).decode()
    store.conn.execute("INSERT INTO state VALUES('fake_attempt_guard_head',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(value,))


def initialize_attempt_guard(lease,project,*,fresh_store):
    """Only original native store creation may create empty evidence."""
    require_live_owner(lease,'execution');path=_directory(project)
    if not path.exists():
        if not fresh_store or lease.generation!=1:return dict(status='EXECUTION_COMPROMISED')
        path.mkdir()
        _flush(path/'identity.json',canonical(dict(schema='fake-execution-attempts-v1',project_id=project.project_id,scope='DETERMINISTIC_FAKE')))
        _flush(path/'head.json',canonical(dict(sequence=0,sha256=ZERO)))
    return verify_attempt_guard(project)


def provision_attempt_guard(store):
    if type(store) is not StateStore:raise RuntimeRefused('WRONG_OWNER_ROLE')
    with store._live() as guard:
        require_live_owner(store.lease,'execution');path=_directory(guard.project)
        if not path.exists():return dict(status='EXECUTION_COMPROMISED',records=[])
        evidence=verify_attempt_guard(guard.project)
        if store.get_state('fake_attempt_guard_head') is None:
            # Existing preserved attempts may precede an older snapshot's schema.
            if evidence['status']=='VERIFIED':_save_head(store,dict(sequence=0,sha256=ZERO))
        try:_require(store,evidence)
        except RuntimeRefused:return dict(status='EXECUTION_COMPROMISED',records=[])
        return evidence


def record_attempt(store,intent,decision,*,now):
    record=dict(intent=intent.to_payload(),decision=decision.to_payload(),attempted_at=now,client_order_id=client_order_id(intent))
    return append_record(store,record)


def append_record(store,record):
    if type(store) is not StateStore:raise RuntimeRefused('WRONG_OWNER_ROLE')
    key=_records(record)
    with store._live() as guard:
        require_live_owner(store.lease,'execution');evidence=verify_attempt_guard(guard.project);_require(store,evidence)
        for prior in evidence['records']:
            if _records(prior)==key:
                if prior['intent']!=record['intent'] or prior['decision']!=record['decision']:raise RuntimeRefused('EXECUTION_COMPROMISED')
                return dict(first=False,record=prior)
        n=evidence['sequence']+1
        if n>MAX_ATTEMPTS:raise RuntimeRefused('FAKE_ATTEMPT_BOUND')
        paper=is_paper(record['intent']);native=is_native(record['intent'])
        if (paper or native) and record['intent']['project_id']!=guard.project.project_id:raise RuntimeRefused('EXECUTION_COMPROMISED')
        item=dict(schema=_schema(record['intent']),sequence=n,previous_sha256=evidence['sha256'],record=record);raw=canonical(item)
        if len(raw)>MAX_BYTES:raise RuntimeRefused('FAKE_ATTEMPT_BOUND')
        path=_directory(guard.project)
        try:
            with guard.api.open_directory(path):
                if native and _read(path/'identity.json',1024)!=_identity(guard.project,native=True):
                    guard.api.publish_metadata(path/'identity.json',canonical(_identity(guard.project,native=True)))
                if paper and _read(path/'identity.json',1024)==_identity(guard.project):
                    guard.api.publish_metadata(path/'identity.json',canonical(_identity(guard.project,True)))
                _flush(path/f'{n:08d}.json',raw)
                head=dict(sequence=n,sha256=hashlib.sha256(raw).hexdigest());guard.api.publish_metadata(path/'head.json',canonical(head))
            _save_head(store,head)
        except (OSError,RuntimeRefused):raise RuntimeRefused('EXECUTION_COMPROMISED') from None
        return dict(first=True,record=record)


def require_attempt_guard(store):
    with store._live() as guard:
        require_live_owner(store.lease,'execution');evidence=verify_attempt_guard(guard.project);_require(store,evidence)
        return evidence
