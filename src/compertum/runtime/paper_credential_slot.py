"""One reserved execution-owned DPAPI slot; no discovery or account authority."""
from contextlib import contextmanager,ExitStack
import base64
import hashlib
import sqlite3
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import PAPER_ORIGIN,strict_json
from compertum.persistence import checked_path,_active_store_path
from .errors import RuntimeRefused
from .owners import _owner_scope,require_live_owner
from .paper_credentials import ProtectedPaperCredentials,open_paper_credentials,_alias
from .paper_read_secrecy import _reject_reflections

SLOT_PATH='state/paper-credentials.bin'


def _metadata(protected):
    return dict(version=1,record_type='ProtectedPaperCredentialSlot',project_id=protected.project_id,
                account_alias=protected.account_alias,origin=PAPER_ORIGIN)


def _payload(protected):
    return canonical(dict(_metadata(protected),ciphertext=base64.b64encode(protected.ciphertext).decode()))


def _verify(lease,protected):
    if type(protected) is not ProtectedPaperCredentials:raise RuntimeRefused('CREDENTIAL_SLOT_INVALID')
    with open_paper_credentials(lease,protected) as opened:
        try:_reject_reflections(canonical(_metadata(protected)),tuple(opened.headers().values()))
        except RuntimeRefused:raise RuntimeRefused('CREDENTIAL_SLOT_SECRET_REFLECTION') from None


@contextmanager
def _coordinator_records(guard):
    """Pin the exact coordinator ledger through the caller's bounded read."""
    root=guard.project.root_path
    try:
        with ExitStack() as pins:
            current=root/'state';pins.enter_context(guard.api.open_directory(current))
            database=_active_store_path(root,guard.project.project_id,'coordinator')
            for part in database.parent.relative_to(current).parts:
                current=current/part;pins.enter_context(guard.api.open_directory(current))
            pin=pins.enter_context(guard.api.open_file(database,0x80000000,3))
            info=guard.api.file_info(pin)
            if info.attributes&(0x400|0x10) or info.links!=1:raise RuntimeRefused('COORDINATOR_RECORDS_UNVERIFIED')
            conn=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=.2)
            try:
                if dict(conn.execute('SELECT key,value FROM metadata'))!={'schema_version':'1','project_id':guard.project.project_id,'role':'coordinator'}:raise RuntimeRefused('COORDINATOR_RECORDS_UNVERIFIED')
                yield conn
            finally:conn.close()
    except (OSError,sqlite3.Error):raise RuntimeRefused('COORDINATOR_RECORDS_UNVERIFIED') from None


@contextmanager
def _slot(lease):
    with _owner_scope(lease) as guard:
        require_live_owner(lease,'execution')
        root=guard.project.root_path;path=checked_path(root,root/SLOT_PATH)
        with guard.api.open_directory(path.parent):
            with _coordinator_records(guard) as conn:
                rows=conn.execute('SELECT maximum,status,category FROM reservations WHERE path=? LIMIT 2',(SLOT_PATH,)).fetchall()
                if rows!=[(16384,'RUNTIME','records')]:raise RuntimeRefused('CREDENTIAL_SLOT_RESERVATION_UNVERIFIED')
            if next(path.parent.glob(path.name+'.incoming-*'),None) is not None:raise RuntimeRefused('CREDENTIAL_SLOT_STAGING_UNRESOLVED')
            yield guard,path


def _decode(lease,guard,raw,alias):
    try:
        p=strict_json(raw)
        if type(p) is not dict or type(p.get('ciphertext')) is not str:raise ContractError('INVALID_SLOT')
        protected=ProtectedPaperCredentials(p['project_id'],p['account_alias'],base64.b64decode(p['ciphertext'],validate=True))
        if _payload(protected)!=raw or protected.project_id!=guard.project.project_id or protected.account_alias!=alias:raise ContractError('INVALID_SLOT')
        _verify(lease,protected);return protected
    except (ContractError,ValueError,TypeError,KeyError):raise RuntimeRefused('CREDENTIAL_SLOT_INVALID') from None


def _receipt(protected,raw,status):
    return dict(version=1,record_type='PaperCredentialSlotReceipt',status=status,account_alias=protected.account_alias,
                path=SLOT_PATH,size_bytes=len(raw),ciphertext_sha256=hashlib.sha256(protected.ciphertext).hexdigest(),
                slot_sha256=hashlib.sha256(raw).hexdigest(),paper_transport_authorized=False)


def provision_paper_slot(lease,protected):
    with _slot(lease) as (guard,path):
        _verify(lease,protected);raw=_payload(protected)
        if len(raw)>8192:raise RuntimeRefused('CREDENTIAL_SLOT_BOUND_EXCEEDED')
        if path.exists():
            existing=guard.api.read_regular(path)
            if existing!=raw:raise RuntimeRefused('CREDENTIAL_SLOT_CONFLICT')
            _decode(lease,guard,existing,protected.account_alias)
            return _receipt(protected,raw,'ALREADY_PRESENT')
        guard.api.publish_metadata(path,raw,replace=False)
        actual=guard.api.read_regular(path)
        if actual!=raw:raise RuntimeRefused('CREDENTIAL_SLOT_WRITE_UNVERIFIED')
        _decode(lease,guard,actual,protected.account_alias)
        return _receipt(protected,raw,'CREATED')


def load_paper_slot(lease,account_alias):
    with _slot(lease) as (guard,path):
        _alias(account_alias)
        if not path.exists():raise RuntimeRefused('CREDENTIAL_SLOT_MISSING')
        return _decode(lease,guard,guard.api.read_regular(path),account_alias)
