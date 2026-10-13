"""Publish synthetic validation evidence using existing coordinator-owned grants."""
import hashlib,json,os
from .snapshot import validate_snapshot,safe_text,canonical,MAX_INPUT
from .errors import DataError
from compertum.events import uuid
from compertum.persistence import checked_path


def publish_snapshot(storage,task_id,raw,*,maximum_bytes):
    """One immutable envelope per exact input, under an aggregate task budget.

    A rejected data envelope is evidence only. It is never a usable snapshot.
    Malformed JSON, invalid encoding and sensitive input retain only a digest.
    """
    uuid(task_id)
    if type(maximum_bytes) is not int or not 0<maximum_bytes<=2*1024*1024:raise DataError('OUTPUT_BUDGET')
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_INPUT:raise DataError('INPUT_BOUND')
    input_hash=hashlib.sha256(raw).hexdigest();snapshot=None;reason=None
    try:snapshot=validate_snapshot(raw)
    except DataError as error:reason=error.code
    original=None
    if reason not in {'SENSITIVE_INPUT','INVALID_JSON','INVALID_ENCODING','DUPLICATE_KEY'}:original=safe_text(raw)
    envelope={'schema_version':'1','status':'OFFLINE_COMPONENT_VERIFIED' if snapshot else 'REJECTED','reason':reason,
              'input_sha256':input_hash,'original_utf8':original,'snapshot':json.loads(snapshot.content) if snapshot else None,
              'snapshot_sha256':snapshot.sha256 if snapshot else None,'diagnostics':list(snapshot.diagnostics) if snapshot else []}
    content=canonical(envelope);store=storage.store
    with store._live(),store.conn:
        store.conn.execute('CREATE TABLE IF NOT EXISTS data_snapshot_budgets(task_id TEXT PRIMARY KEY,maximum INTEGER NOT NULL)')
        store.conn.execute('CREATE TABLE IF NOT EXISTS data_snapshot_receipts(task_id TEXT NOT NULL,input_sha256 TEXT NOT NULL,receipt TEXT NOT NULL,PRIMARY KEY(task_id,input_sha256))')
        old=store.conn.execute('SELECT maximum FROM data_snapshot_budgets WHERE task_id=?',(task_id,)).fetchone()
        if old and old[0]!=maximum_bytes:raise DataError('OUTPUT_BUDGET_CONFLICT')
        store.conn.execute('INSERT OR IGNORE INTO data_snapshot_budgets VALUES(?,?)',(task_id,maximum_bytes))
        prior=store.conn.execute('SELECT receipt FROM data_snapshot_receipts WHERE task_id=? AND input_sha256=?',(task_id,input_hash)).fetchone()
        if prior:
            receipt=json.loads(prior[0]);artifact=receipt['artifact'];path=checked_path(storage.root,storage.root/artifact['path'])
            try:
                with path.open('rb') as stream:
                    size=os.fstat(stream.fileno()).st_size
                    expected=artifact['size_bytes']
                    if type(expected) is not int or not 0<expected<=maximum_bytes or size!=expected:raise DataError('PUBLICATION_CORRUPT')
                    retained=stream.read(expected+1)
                    if len(retained)!=expected:raise DataError('PUBLICATION_CORRUPT')
                    digest=hashlib.sha256(retained).hexdigest()
            except OSError:raise DataError('PUBLICATION_CORRUPT') from None
            if size!=artifact['size_bytes'] or digest!=artifact['sha256'] or digest!=hashlib.sha256(content).hexdigest():raise DataError('PUBLICATION_CORRUPT')
            return receipt
        used=store.conn.execute("SELECT COALESCE(sum(CASE WHEN status IN ('PUBLISHED','ABANDONED') THEN written ELSE maximum END),0) FROM reservations WHERE task=? AND category='records' AND status!='SPLIT'",(task_id,)).fetchone()[0]
        if used+len(content)>maximum_bytes:raise DataError('OUTPUT_BUDGET')
        relative=f'artifacts/runs/{task_id}/data/input-{input_hash}.json'
        # A crash after artifact publication but before its receipt is uncertain.
        # Retain the file and refuse; never truncate or guess it was accepted.
        if checked_path(storage.root,storage.root/relative).exists():raise DataError('PUBLICATION_INCOMPLETE')
        grant=storage.reserve_bytes(task_id,'records',len(content));writer=storage.open_artifact(grant,relative)
        try:writer.write(content);artifact=writer.publish()
        finally:writer.close()
        receipt={'status':envelope['status'],'reason':reason,'input_sha256':input_hash,'snapshot_sha256':envelope['snapshot_sha256'],'artifact':artifact}
        store.conn.execute('INSERT INTO data_snapshot_receipts VALUES(?,?,?)',(task_id,input_hash,canonical(receipt).decode()))
        return receipt
