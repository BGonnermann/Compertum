"""Shared native SQLite/attempt history; all requests and credentials invented."""
import json,sqlite3
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.paper_intent_journal import PaperIntentJournal
from compertum.paper_intent_records import paper_client_id
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_order_qualification import prepare_order_exchange
from test_fake_execution_journal import native,checked_records,arguments
from test_paper_read_preparation import KEY,SECRET
from test_paper_responses import ACCOUNT,ORDER

AT='2023-11-24T14:30:00Z';END='2023-11-24T14:31:00Z'

@pytest.fixture
def paper(native,monkeypatch):
    project,lease,store,fake=native
    # Focused tests isolate the shared record state machine. Native acceptance
    # separately uses the real 1GiB reserve and the unchanged durability check.
    monkeypatch.setattr('compertum.paper_intent_journal.execution_durable',lambda *a:None)
    protected=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    from compertum.storage import create_journal_reserve
    return project,lease,store,PaperIntentJournal(store,create_journal_reserve(lease,65536)),protected

def request(paper,*,intent_id=None,operation='SUBMIT_ORDER',**changes):
    project,lease,store,j,protected=paper;intent_id=intent_id or str(uuid4())
    args=dict(account_id=ACCOUNT,request_id=str(uuid4()),intent_id=intent_id,created_at=AT,operation=operation)
    if operation=='SUBMIT_ORDER':args['body']=dict(symbol='AAPL',qty='1',side='buy',type='market',time_in_force='day',extended_hours=False,client_order_id=paper_client_id(project.project_id,'fixture',intent_id))
    else:args['parameters']={'order_id':ORDER}
    args.update(changes)
    return prepare_order_exchange(lease,protected,**args)

def prepared(paper,req=None):
    return paper[3].record_prepared(req or request(paper),expires_at=END,supporting_sha256={'plan':'a'*64})

def args(row):return row['intent']['account_alias'],row['intent']['intent_id']

def test_consumption_once_inert_and_private(paper):
    project,_,store,j,_=paper;req=request(paper);row=prepared(paper,req)
    assert prepared(paper,req)==row
    first=j.consume(*args(row),now=AT);again=j.consume(*args(row),now=AT)
    assert first['first_consumption'] and not again['first_consumption']
    assert first['record']==again['record'] and first['record']['status']=='PAPER_CONSUMED'
    assert first['transport_authorized'] is first['financial_accepted'] is False
    assert all(s not in json.dumps(first) for s in (ACCOUNT,KEY,SECRET))
    evidence=verify_attempt_guard(project);assert evidence['status']=='VERIFIED' and evidence['sequence']==1
    assert store.conn.execute('SELECT count(*) FROM fake_intents').fetchone()[0]==1
    with pytest.raises(RuntimeRefused,match='INTENT_SCOPE_MISMATCH'):FakeIntentJournal(store).read(*args(row))

@pytest.mark.parametrize('phase',['before_schema','before_record','before_consumption'])
def test_older_snapshot_reconstructs_consumed_without_regrant(paper,tmp_path,phase):
    project,_,store,j,_=paper;snap=sqlite3.connect(tmp_path/'older.sqlite')
    try:
        if phase=='before_schema':
            with store.conn:
                for name in ('fake_intents','fake_intent_events'):store.conn.execute('DROP TABLE '+name)
            store.conn.backup(snap);j=PaperIntentJournal(store,paper[3].reserve);paper=(*paper[:3],j,paper[4])
        elif phase=='before_record':store.conn.backup(snap)
        row=prepared(paper)
        if phase=='before_consumption':store.conn.backup(snap)
        assert j.consume(*args(row),now=AT)['first_consumption'];snap.backup(store.conn)
        recovered=PaperIntentJournal(store,paper[3].reserve)
        assert recovered.read(*args(row))['status']=='PAPER_CONSUMED'
        assert not recovered.consume(*args(row),now=AT)['first_consumption']
        from compertum.fake_recovery import snapshot_attempts,matches_snapshot
        assert matches_snapshot(snapshot_attempts(store.conn,project.project_id),verify_attempt_guard(project))
    finally:snap.close()

@pytest.mark.parametrize('operation',['SUBMIT_ORDER','CANCEL_ORDER'])
def test_submit_and_cancel_have_distinct_immutable_consumption(paper,operation):
    row=prepared(paper,request(paper,operation=operation));assert paper[3].consume(*args(row),now=AT)['first_consumption']

@pytest.mark.parametrize('change',['different_body','support','expiry'])
def test_conflicting_preparation_never_replaces_prior(paper,change):
    req=request(paper);row=prepared(paper,req);kwargs=dict(expires_at=END,supporting_sha256={'plan':'a'*64})
    if change=='different_body':
        body=req.to_payload()['body'];body['qty']='2';req=request(paper,intent_id=row['intent']['intent_id'],body=body)
    elif change=='support':kwargs['supporting_sha256']={'plan':'b'*64}
    else:kwargs['expires_at']='2023-11-24T14:30:59Z'
    with pytest.raises(RuntimeRefused,match='INTENT_CONFLICT'):paper[3].record_prepared(req,**kwargs)
    assert paper[3].read(*args(row))==row

@pytest.mark.parametrize('damage',['missing','extra','head','record'])
def test_damaged_history_blocks_consumption_without_recreation(paper,damage):
    project,_,_,j,_=paper;row=prepared(paper);path=project.root_path/'state/fake-execution-attempts'
    if damage=='missing':path.rename(path.with_name('saved-attempts'))
    elif damage=='extra':(path/'extra.json').write_text('{}')
    elif damage=='head':(path/'head.json').write_text('{}')
    else:(path/'identity.json').write_text('{}')
    with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):j.consume(*args(row),now=AT)
    if damage=='missing':assert not path.exists()
    assert j.read(*args(row))['status']=='PAPER_PREPARED'

def test_expired_preparation_burns_without_attempt_file(paper):
    row=prepared(paper);r=paper[3].consume(*args(row),now=END)
    assert not r['first_consumption'] and r['record']['status']=='PAPER_SKIPPED_WINDOW_EXPIRED'
    assert verify_attempt_guard(paper[0])['sequence']==0

def test_lookup_cannot_be_consumed_as_write(paper):
    with pytest.raises(RuntimeRefused,match='INVALID_PAPER_PREPARATION'):prepared(paper,request(paper,operation='ORDER_BY_ID'))

def test_actual_durability_required_before_consumption(paper,monkeypatch):
    row=prepared(paper)
    def denied(*a):raise RuntimeRefused('JOURNAL_UNRESERVED')
    monkeypatch.setattr('compertum.paper_intent_journal.execution_durable',denied)
    with pytest.raises(RuntimeRefused,match='JOURNAL_UNRESERVED'):paper[3].consume(*args(row),now=AT)
    assert verify_attempt_guard(paper[0])['sequence']==0

def test_legacy_event_bytes_unchanged_in_mixed_guard(paper):
    project,lease,store,j,_=paper;fake=FakeIntentJournal(store);i,d=checked_records(lease);fake.record_checked(i,d)
    from test_execution_risk import NOW
    assert fake.begin_attempt(*arguments(i),now=NOW)['simulate_once']
    path=project.root_path/'state/fake-execution-attempts';raw=(path/'00000001.json').read_bytes()
    row=prepared(paper);assert j.consume(*args(row),now=AT)['first_consumption']
    assert (path/'00000001.json').read_bytes()==raw
    evidence=verify_attempt_guard(project);assert evidence['status']=='VERIFIED' and evidence['sequence']==2
    assert json.loads((path/'identity.json').read_bytes())['schema']=='execution-attempts-v2'
    assert not FakeIntentJournal(store).begin_attempt(*arguments(i),now=NOW)['simulate_once']
    from compertum.fake_recovery import snapshot_attempts,matches_snapshot
    assert matches_snapshot(snapshot_attempts(store.conn,project.project_id),evidence)


def test_forged_reserve_dictionary_does_not_prove_native_durability(paper):
    from types import SimpleNamespace
    reserve=SimpleNamespace(lease=paper[1],receipt=lambda:dict(capacity_bytes=1024**3,unused_bytes=1024**3,allocated_bytes=1024**3,sparse=False))
    with pytest.raises(RuntimeRefused,match='JOURNAL_UNRESERVED'):PaperIntentJournal(paper[2],reserve)

def test_wrong_reserve_lease_is_not_accepted(paper):
    from compertum.runtime.owners import acquire_owner,release_owner
    other=acquire_owner(paper[0],'coordinator');reserve=paper[3].reserve;original=reserve.lease
    try:
        reserve.lease=other
        with pytest.raises(RuntimeRefused,match='JOURNAL_UNRESERVED'):PaperIntentJournal(paper[2],reserve)
    finally:reserve.lease=original;release_owner(other)


@pytest.mark.parametrize('field,value',[
 ('version',True),('scope','DETERMINISTIC_FAKE'),('transport_authorized',True),('financial_accepted',True),
 ('approval_status','GRANTED'),('generation',True),('project_id','a'*63),('owner_instance','x'),
 ('client_order_id','cmp-wrong'),('request_sha256','b'*64),('private_context_sha256','bad'),
 ('expires_at','2023-11-24T14:31:01Z'),('created_at','2023-11-24T14:30:00.0000001Z'),
 ('supporting_sha256',{'unbounded':'a'*64})],ids=['version','scope','transport','financial','approval','generation','project','owner','client','request-hash','private-hash','expiry','clock-precision','support'])
def test_strict_paper_codec_rejects_changed_retained_fields(paper,field,value):
    from compertum.paper_intent_records import validate_pair,binding
    p=prepared(paper)['intent'];p[field]=value
    with pytest.raises((ValueError,RuntimeRefused,__import__('compertum.domain',fromlist=['ContractError']).ContractError)):validate_pair(p,binding(p))

@pytest.mark.parametrize('state',['CHECKED','UNKNOWN','FILLED','PAPER_INVALID'])
def test_recovery_rejects_cross_scope_state_substitution(paper,state):
    from compertum.fake_recovery import snapshot_attempts
    row=prepared(paper)
    with paper[2].conn:paper[2].conn.execute('UPDATE fake_intents SET state=?',(state,))
    with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):snapshot_attempts(paper[2].conn,paper[0].project_id)

def test_supporting_hash_cannot_reflect_credential(paper):
    lease=paper[1];protected=seal_paper_credentials(lease,'fixture',bytearray(b'a'*64),bytearray(SECRET.encode()))
    owner=(*paper[:4],protected);req=request(owner)
    with pytest.raises(RuntimeRefused):paper[3].record_prepared(req,expires_at=END,supporting_sha256={'plan':'a'*64})
    assert paper[2].conn.execute('SELECT count(*) FROM fake_intents').fetchone()[0]==0

def test_history_event_written_before_head_prevents_any_second_consumption(paper,monkeypatch):
    row=prepared(paper);j=paper[3]
    with j.store._live() as guard:api=guard.api
    original=api.publish_metadata
    def fail(path,raw):
        if path.name=='head.json' and path.parent.name=='fake-execution-attempts':raise OSError('injected fixture boundary')
        return original(path,raw)
    monkeypatch.setattr(api,'publish_metadata',fail)
    with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):j.consume(*args(row),now=AT)
    assert verify_attempt_guard(paper[0])['status']=='EXECUTION_COMPROMISED'
    with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):j.consume(*args(row),now=AT)

def test_history_head_published_before_sqlite_commit_burns_consumption(paper,monkeypatch):
    row=prepared(paper);j=paper[3];original=j.base._event
    def fail(*a,**kw):raise RuntimeRefused('FIXTURE_DB_BOUNDARY')
    monkeypatch.setattr(j.base,'_event',fail)
    with pytest.raises(RuntimeRefused,match='FIXTURE_DB_BOUNDARY'):j.consume(*args(row),now=AT)
    monkeypatch.setattr(j.base,'_event',original)
    assert verify_attempt_guard(paper[0])['sequence']==1
    r=j.consume(*args(row),now=AT);assert not r['first_consumption'] and r['record']['status']=='PAPER_CONSUMED'

@pytest.mark.parametrize('kind',['intent','event','attempt'])
def test_shared_limits_cannot_be_bypassed_by_paper_scope(paper,monkeypatch,kind):
    row=prepared(paper);j=paper[3]
    if kind=='intent':
        monkeypatch.setattr('compertum.paper_intent_journal.MAX_INTENTS',1)
        with pytest.raises(RuntimeRefused,match='FAKE_JOURNAL_BOUND'):prepared(paper)
    else:
        monkeypatch.setattr('compertum.fake_execution_journal.MAX_EVENTS' if kind=='event' else 'compertum.fake_attempt_guard.MAX_ATTEMPTS',1 if kind=='event' else 0)
        with pytest.raises(RuntimeRefused,match='FAKE_JOURNAL_BOUND|FAKE_ATTEMPT_BOUND'):j.consume(*args(row),now=AT)
        if kind=='event':assert verify_attempt_guard(paper[0])['sequence']==1


from test_execution_health import pair
from test_execution_authority import authority
from test_saved_plan_controls import ready

def add_to_existing_owner(a,monkeypatch,count=1):
    from compertum.runtime.identity import resolve_project
    monkeypatch.setattr('compertum.paper_intent_journal.execution_durable',lambda *args:None)
    lease=a.store.lease;protected=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    p=(resolve_project(a.store.root),lease,a.store,PaperIntentJournal(a.store,a.reserve),protected)
    for _ in range(count):
        row=prepared(p);assert p[3].consume(*args(row),now=AT)['first_consumption']

def test_paper_history_does_not_change_fake_observations(authority,monkeypatch):
    from test_execution_observations import observed_owner
    owner=observed_owner(authority);before,_=owner.read();add_to_existing_owner(authority[0],monkeypatch)
    after,_=owner.read()
    assert after.to_payload()['account']==before.to_payload()['account']
    assert after.to_payload()['positions']==before.to_payload()['positions']

def test_paper_history_uses_capacity_without_becoming_pending_fake_work(ready,monkeypatch):
    from test_operation_progression import started
    from compertum.execution_operation_owner import FakeOperationOwner
    a=ready[0];started(a);op=FakeOperationOwner(a.plan_owner);op._schema();assert op._headroom([])
    add_to_existing_owner(a,monkeypatch,6)
    assert op._headroom([])
    assert a.store.conn.execute('SELECT count(*) FROM fake_intents').fetchone()[0]==6


def test_reserve_replacement_after_preparation_cannot_consume(paper):
    from types import SimpleNamespace
    row=prepared(paper);j=paper[3]
    j.reserve=SimpleNamespace(lease=paper[1],receipt=lambda:dict(capacity_bytes=1024**3,unused_bytes=1024**3,allocated_bytes=1024**3,sparse=False))
    with pytest.raises(RuntimeRefused,match='JOURNAL_UNRESERVED'):j.consume(*args(row),now=AT)
    assert verify_attempt_guard(paper[0])['sequence']==0
