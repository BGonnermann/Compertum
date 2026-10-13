"""Invented paper records for native crash/restore tests; never a transport."""
import json,sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_paper_intent_journal import request,AT,END,args
from test_paper_read_preparation import KEY,SECRET
from compertum.paper_intent_journal import PaperIntentJournal
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.persistence import open_store
from compertum.storage import open_journal_reserve
from compertum.runtime.identity import resolve_project
from compertum.fake_attempt_guard import verify_attempt_guard


def records(root,lease,store,reserve):
    protected=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    journal=PaperIntentJournal(store,reserve);p=(resolve_project(root),lease,store,journal,protected)
    rows=[journal.record_prepared(request(p),expires_at=END,supporting_sha256={'plan':'a'*64}) for _ in range(2)]
    (root/'paper-fixture.json').write_text(json.dumps(dict(consumed=args(rows[0]),waiting=args(rows[1]),reserve=reserve.receipt())))
    return journal,rows


def prepare(root,leases,stores,reserve,collect):
    journal,rows=records(root,leases['execution'],stores['execution'],reserve);before=collect()
    assert journal.consume(*args(rows[0]),now=AT)['first_consumption']
    return dict(status='CONSUMED_PREPARATION',transport_authorized=False),before


def inspect(root,project):
    lease=acquire_owner(project,'execution')
    try:
        store=open_store(lease,'execution');reserve=open_journal_reserve(lease);journal=PaperIntentJournal(store,reserve)
        fixture=json.loads((root/'paper-fixture.json').read_text());result=journal.consume(*fixture['consumed'],now=AT)
        waiting=journal.read(*fixture['waiting'])
        return dict(result=result,waiting=waiting['status'],guard=verify_attempt_guard(project)['status'],reserve=reserve.receipt(),generation=lease.generation)
    finally:release_owner(lease)
