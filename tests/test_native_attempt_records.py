"""Invented native record data; no grant producer or broker transport."""
from copy import deepcopy
import json
import sqlite3
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_fake_execution_journal import native, checked_records
from test_paper_intent_journal import paper,prepared
from test_execution_authority import authority
from test_execution_health import pair
from test_fake_economic_opening import opened,declare

AT='2023-11-24T14:35:00Z'
END='2023-11-24T14:36:00Z'


def records(lease=None,operation='SUBMIT_ORDER'):
    from compertum.native_attempt_records import native_client_id, sha
    project=lease.project_id if lease else 'a'*64
    intent_id=str(uuid4())
    p=dict(version=1,record_type='NativePaperWrite',scope='NATIVE_PAPER_WRITE',
        project_id=project,account_alias='fixture',intent_id=intent_id,
        generation=lease.generation if lease else 1,
        owner_instance=lease.identity.process_instance_id if lease else str(uuid4()),
        created_at=AT,expires_at=END,purpose='FIXTURE_BUY' if operation=='SUBMIT_ORDER' else 'CANCEL',
        client_order_id=native_client_id(project,'fixture',intent_id),
        evidence_sha256={key:'b'*64 for key in ('intent','confirmation','presence','opening','ownership','economics','risk','inputs')})
    from compertum.runtime._winhttp_order import _wire
    body=dict(symbol='AAPL',qty='1',side='buy',type='market',time_in_force='day',
        extended_hours=False,client_order_id=p['client_order_id']) if operation=='SUBMIT_ORDER' else None
    parameters={} if body else {'order_id':str(uuid4())}
    method,target,_=_wire(operation,parameters,body)
    p['request']=dict(version=1,record_type='PreparedPaperOrderExchange',scope='PREPARATION_ONLY',
        project_id=project,account_alias='fixture',request_id=str(uuid4()),intent_id=intent_id,
        created_at=AT,operation=operation,method=method,target=target,parameters=parameters,body=body,
        transport_authorized=False,financial_accepted=False,approval_status='NOT_GRANTED')
    p['request_sha256']=sha(p['request'])
    d=dict(version=1,record_type='NativePaperWriteBinding',scope='RETAINED_EVIDENCE_ONLY',
        intent_sha256=sha(p),transport_authorized=False,financial_accepted=False)
    return p,d


def attempt(p,d):
    return dict(intent=p,decision=d,attempted_at=AT,client_order_id=p['client_order_id'])


@pytest.mark.parametrize('operation',['SUBMIT_ORDER','CANCEL_ORDER'])
def test_native_kind_is_disjoint_and_has_no_dispatch_capability(operation):
    from compertum.attempt_records import validate_pair,is_native,is_paper,record_key
    from compertum.native_attempt_records import native_client_id
    from compertum.paper_intent_records import paper_client_id
    p,d=records(operation=operation)
    assert validate_pair(p,d)==(p,d,p['client_order_id'])
    assert is_native(p) and not is_paper(p)
    assert native_client_id(p['project_id'],p['account_alias'],p['intent_id'])!=paper_client_id(p['project_id'],p['account_alias'],p['intent_id'])
    assert record_key(attempt(p,d))==('fixture',p['intent_id'])
    assert d['transport_authorized'] is d['financial_accepted'] is False


@pytest.mark.parametrize('fault',[
    'unknown_field','bool_version','bool_generation','wrong_scope','bad_alias','bad_project',
    'bad_instance','bad_id','missing_evidence','extra_evidence','bad_evidence',
    'wrong_request_hash','wrong_request_account','wrong_request_intent','wrong_request_time',
    'wrong_request_target','wrong_request_method','wrong_request_scope','wrong_request_version',
    'wrong_client','preparation_client','wrong_body_client','unsupported_operation',
    'expired_interval','long_interval','noncanonical_time','purpose_mismatch','fixture_sell',
    'fixture_quantity','fixture_limit','decision_authority','decision_extra','decision_hash'])
def test_malformed_native_records_refuse(fault):
    from compertum.native_attempt_records import sha,validate_pair
    from compertum.paper_intent_records import paper_client_id
    p,d=records()
    if fault=='unknown_field':p['unexpected']=True
    elif fault=='bool_version':p['version']=True
    elif fault=='bool_generation':p['generation']=True
    elif fault=='wrong_scope':p['scope']='PAPER_PREPARATION'
    elif fault=='bad_alias':p['account_alias']='invalid alias'
    elif fault=='bad_project':p['project_id']='x'*64
    elif fault=='bad_instance':p['owner_instance']='invalid'
    elif fault=='bad_id':p['intent_id']='invalid'
    elif fault=='missing_evidence':p['evidence_sha256'].pop('economics')
    elif fault=='extra_evidence':p['evidence_sha256']['caller_flag']='b'*64
    elif fault=='bad_evidence':p['evidence_sha256']['risk']='x'*64
    elif fault=='wrong_request_hash':p['request_sha256']='c'*64
    elif fault=='wrong_request_account':p['request']['account_alias']='other'
    elif fault=='wrong_request_intent':p['request']['intent_id']=str(uuid4())
    elif fault=='wrong_request_time':p['request']['created_at']=END
    elif fault=='wrong_request_target':p['request']['target']='/v2/account'
    elif fault=='wrong_request_method':p['request']['method']='GET'
    elif fault=='wrong_request_scope':p['request']['scope']='NATIVE_PAPER_WRITE'
    elif fault=='wrong_request_version':p['request']['version']=True
    elif fault=='wrong_client':p['client_order_id']='cmp-invented'
    elif fault=='preparation_client':p['client_order_id']=paper_client_id(p['project_id'],p['account_alias'],p['intent_id'])
    elif fault=='wrong_body_client':p['request']['body']['client_order_id']='cmp-invented'
    elif fault=='unsupported_operation':p['request']['operation']='ORDER_BY_CLIENT_ID'
    elif fault=='expired_interval':p['expires_at']=AT
    elif fault=='long_interval':p['expires_at']='2023-11-24T14:36:01Z'
    elif fault=='noncanonical_time':p['expires_at']='2023-11-24T14:36:00+00:00'
    elif fault=='purpose_mismatch':p['purpose']='CANCEL'
    elif fault=='fixture_sell':p['request']['body']['side']='sell'
    elif fault=='fixture_quantity':p['request']['body']['qty']='2'
    elif fault=='fixture_limit':p['request']['body'].update(type='limit',limit_price='1')
    if fault!='wrong_request_hash':p['request_sha256']=sha(p['request'])
    d['intent_sha256']=sha(p)
    if fault=='decision_authority':d['transport_authorized']=True
    elif fault=='decision_extra':d['allowed']=True
    elif fault=='decision_hash':d['intent_sha256']='c'*64
    with pytest.raises((ValueError,RuntimeRefused)):validate_pair(p,d)


def test_native_attempt_uses_original_interval():
    from compertum.attempt_records import record_key
    p,d=records();r=attempt(p,d);r['attempted_at']=END
    with pytest.raises(ValueError):record_key(r)


def test_native_guard_survives_older_database_and_fake_journal_ignores_it(native,tmp_path):
    from compertum.fake_attempt_guard import append_record,verify_attempt_guard,require_attempt_guard
    from compertum.fake_execution_journal import FakeIntentJournal
    from compertum.fake_recovery import snapshot_attempts,matches_snapshot
    project,lease,store,journal=native;p,d=records(lease)
    snap=sqlite3.connect(tmp_path/'older.sqlite')
    try:
        store.conn.backup(snap)
        with store.conn:
            assert append_record(store,attempt(p,d))['first']
        evidence=verify_attempt_guard(project)
        assert evidence['status']=='VERIFIED' and evidence['records']==[attempt(p,d)]
        assert not append_record(store,attempt(p,d))['first']
        snap.backup(store.conn)
        FakeIntentJournal(store)
        assert store.conn.execute('SELECT count(*) FROM fake_intents').fetchone()==(0,)
        assert require_attempt_guard(store)['records']==evidence['records']
        assert matches_snapshot(snapshot_attempts(store.conn,project.project_id),evidence)
        assert not append_record(store,attempt(p,d))['first']
    finally:snap.close()


def test_fake_and_preparation_readers_refuse_native_rows(native):
    from compertum.fake_recovery import snapshot_attempts
    from compertum.fake_execution_journal import FakeIntentJournal
    project,lease,store,journal=native;p,d=records(lease)
    with store.conn:
        store.conn.execute("INSERT INTO fake_intents VALUES(?,?,?,?,?,'NATIVE_CONSUMED',NULL,0,'0',0)",
            (p['account_alias'],p['intent_id'],p['client_order_id'],canonical(p).decode(),canonical(d).decode()))
    assert snapshot_attempts(store.conn,project.project_id)['rows'][0]['attempted']
    with pytest.raises(RuntimeRefused,match='INTENT_SCOPE_MISMATCH'):journal.read(p['account_alias'],p['intent_id'])


@pytest.mark.parametrize('fault',['schema','project','kind'])
def test_native_guard_rejects_substitution(native,fault):
    from compertum.fake_attempt_guard import append_record,verify_attempt_guard
    import hashlib
    project,lease,store,_=native;p,d=records(lease)
    with store.conn:append_record(store,attempt(p,d))
    folder=project.root_path/'state/fake-execution-attempts'
    path=folder/'00000001.json';value=json.loads(path.read_bytes())
    if fault=='schema':value['schema']='paper-preparation-attempt-v2'
    elif fault=='kind':value['record']['intent']['record_type']='PaperIntentPreparation'
    else:value['record']['intent']['project_id']='f'*64
    raw=canonical(value);path.write_bytes(raw)
    (folder/'head.json').write_bytes(canonical(dict(sequence=1,sha256=hashlib.sha256(raw).hexdigest())))
    assert verify_attempt_guard(project)['status']=='EXECUTION_COMPROMISED'


def insert_native(store,p,d):
    with store.conn:
        store.conn.execute("INSERT INTO fake_intents VALUES(?,?,?,?,?,'NATIVE_CONSUMED',NULL,0,'0',0)",
            (p['account_alias'],p['intent_id'],p['client_order_id'],canonical(p).decode(),canonical(d).decode()))
        store.conn.execute("INSERT INTO fake_intent_events(account,intent_id,kind,body) VALUES(?,?,'NATIVE_CONSUMED','{}')",
            (p['account_alias'],p['intent_id']))


def test_native_rows_and_events_are_excluded_from_fake_status(native):
    _,lease,store,journal=native;before=journal.status();p,d=records(lease)
    insert_native(store,p,d)
    assert journal.status()==before


@pytest.mark.parametrize('sequence',['NFP','PNF','FNP'])
def test_mixed_guard_preserves_each_record_kind_and_fake_counts(paper,sequence):
    from compertum.fake_attempt_guard import append_record,verify_attempt_guard
    from compertum.fake_execution_journal import FakeIntentJournal
    from test_execution_risk import NOW
    project,lease,store,journal,_=paper
    expected=[];fake=FakeIntentJournal(store)
    for kind in sequence:
        if kind=='N':
            p,d=records(lease)
            with store.conn:append_record(store,attempt(p,d))
            insert_native(store,p,d);expected.append('NativePaperWrite')
        elif kind=='F':
            i,d=checked_records(lease);fake.record_checked(i,d)
            fake.begin_attempt(i.to_payload()['account_alias'],i.to_payload()['intent_id'],now=NOW)
            expected.append(i.to_payload()['record_type'])
        else:
            row=prepared(paper);journal.consume(row['intent']['account_alias'],row['intent']['intent_id'],now=row['intent']['created_at'])
            expected.append('PaperIntentPreparation')
    evidence=verify_attempt_guard(project)
    assert evidence['status']=='VERIFIED' and [r['intent']['record_type'] for r in evidence['records']]==expected
    assert fake.status()['intents']==1
    assert fake.status()['events']==store.conn.execute("SELECT count(*) FROM fake_intent_events WHERE account LIKE 'fake-%'").fetchone()[0]


@pytest.mark.parametrize('state',['PAPER_CONSUMED','UNKNOWN','CHECKED'])
def test_native_record_cannot_use_other_record_states(native,state):
    from compertum.fake_recovery import snapshot_attempts
    project,lease,store,_=native;p,d=records(lease);insert_native(store,p,d)
    with store.conn:store.conn.execute('UPDATE fake_intents SET state=?',(state,))
    with pytest.raises(RuntimeRefused):snapshot_attempts(store.conn,project.project_id)


@pytest.mark.parametrize('change',['decision','request'])
def test_native_attempt_key_cannot_replace_retained_evidence(native,change):
    from compertum.fake_attempt_guard import append_record
    from compertum.native_attempt_records import sha
    _,lease,store,_=native;p,d=records(lease)
    with store.conn:append_record(store,attempt(p,d))
    if change=='decision':p['evidence_sha256']['risk']='c'*64
    else:p['request']['request_id']=str(uuid4());p['request_sha256']=sha(p['request'])
    d['intent_sha256']=sha(p)
    with pytest.raises(RuntimeRefused,match='COMPROMISED'):append_record(store,attempt(p,d))


def test_preparation_reader_refuses_native_row(paper):
    _,lease,store,journal,_=paper;p,d=records(lease);insert_native(store,p,d)
    with pytest.raises(RuntimeRefused):journal.read(p['account_alias'],p['intent_id'])


def test_native_history_is_classified_separately(native):
    from types import SimpleNamespace
    from compertum.fake_attempt_guard import append_record
    from compertum.runtime.paper_preflight import _history
    from compertum.runtime.paper_portfolio_context import _journal_snapshot
    _,lease,store,_=native;p,d=records(lease)
    with store.conn:append_record(store,attempt(p,d))
    insert_native(store,p,d)
    assert _history(store)==dict(status='PRESERVED_DISJOINT_EXECUTION_HISTORY',
        native_attempts=1,fake_attempts=0,paper_preparations=0)
    assert _journal_snapshot(SimpleNamespace(db=store.conn,store=store))['classes']==dict(fake=0,preparation=0,unknown=0,native=1)


def test_native_records_do_not_enter_fake_driver_economics(opened):
    from compertum.fake_attempt_guard import append_record
    from compertum.fake_execution_journal import FakeIntentJournal
    from compertum.fake_execution_driver import FakeExecutionDriver
    store,broker=opened;declare(store,broker)
    driver=FakeExecutionDriver(FakeIntentJournal(store),broker)
    before=driver._economics(broker.snapshot());p,d=records(store.lease)
    with store.conn:append_record(store,attempt(p,d))
    assert driver._economics(broker.snapshot())==before
