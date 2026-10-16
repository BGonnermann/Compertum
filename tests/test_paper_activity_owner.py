"""Invented account opening; actual WinHTTP loopback and DPAPI, simulated 64 KiB reserve."""
from datetime import datetime,timezone
from uuid import uuid4
import json,pickle,time
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.service_budget import queue_for
from test_execution_health import pair
from test_paper_read_owner import owner
from test_paper_read_publication import publication
from test_paper_account_binding import invented_paper_origin
from test_paper_presence import account
from test_paper_market_collection import pages
from test_winhttp_get import server
from test_paper_read_preparation import ACCOUNT,KEY,SECRET


@pytest.fixture
def activity(account,monkeypatch):
    from compertum.runtime import paper_activity_owner as module
    o,_,p=account;o.clock.utc+=1;o.clock.mono+=1
    o.a.account_context(subject='a'*64,packet_id=p['packet_id'])
    original=module._ActivityProducer
    o.activity_port=None
    def producer(*a,**kw):
        assert o.activity_port is not None
        return original(*a,**kw,_test_port=o.activity_port)
    monkeypatch.setattr(module,'_new_producer',producer)
    return o,p


def send(o,operation,**kw):
    return o.a.activity_handle(dict(subject_key='a'*64,command=dict(operation=operation,**kw)))


def prepare(o,p):
    return send(o,'prepare',activity_id=str(uuid4()),packet_id=p['packet_id'],task_id=o.task,reservation_id=o.grant.grant_id)


def start(o,p):
    send(o,'authorize',activity_id=p['activity_id'],plan_sha256=p['plan_sha256'])
    return send(o,'start',activity_id=p['activity_id'],plan_sha256=p['plan_sha256'])


def finish(o,p):
    until=time.monotonic()+8
    while time.monotonic()<until:
        o.a.tick();v=send(o,'status',activity_id=p['activity_id'])
        if v['state']!='RUNNING':return v
        time.sleep(.002)
    raise AssertionError('Activity did not terminate')


def row(index):return dict(id=f'activity::{index:04}',activity_type='DIV',amount='1.00')


def test_activity_routes_keep_broker_write_capabilities_unavailable():
    from compertum.domain import capability_for
    from compertum.runtime.supervisor import ACTIONS
    from compertum.runtime.owner_channel import _commands
    assert 'paper_activity' in ACTIONS
    assert _commands(['paper_activity','paper_activity_transfer'])==frozenset({'paper_activity','paper_activity_transfer'})
    for action in ('paper.arm','paper.start','paper.cancel','paper.close'):assert capability_for(action).exit_code==3


def test_two_pages_exact_queue_and_encrypted_history(activity):
    from compertum.runtime.paper_activity_evidence import publish_activity_evidence,open_activity_evidence
    o,packet=activity
    with pages([canonical([row(i) for i in range(25)]),b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet);start(o,p);s=finish(o,p)
        assert s['state']=='EVIDENCE_READY' and s['summary']['traversal_complete']
        assert len(seen)==2 and 'page_token=activity%3A%3A0024' in seen[1][0]
        assert all('APCA-API-KEY-ID' not in headers for _,headers in seen)
        assert queue_for(o.e.lease).status()['paper_used']==8
        before=len(seen);start(o,p);assert len(seen)==before
    cipher=o.a._activities._cipher
    assert all(value.encode() not in cipher.ciphertext for value in (KEY,SECRET,ACCOUNT,'activity::0024'))
    child=o.manager.split_grant(o.grant,len(cipher.ciphertext))
    manifest=publish_activity_evidence(o.manager,child,cipher)
    assert publish_activity_evidence(o.manager,child,cipher)==manifest
    with open_activity_evidence(o.e.lease,'fixture',p['activity_id'],manifest) as opened:
        v=opened.snapshot();assert v['freshness']=='NOT_RESTORED'
        assert v['collection']['provenance']=='LOOPBACK_FIXTURE'
        assert v['collection']['pages'][0]['raw_utf8']==canonical([row(i) for i in range(25)]).decode()
        assert v['collection']['summary']['status']=='BLOCKED'
        with pytest.raises(RuntimeRefused):pickle.dumps(opened)
    assert o.a._account_context is o.a._activities._producer._context_input


@pytest.mark.parametrize('status',[401,403,429,500])
def test_http_errors_do_not_retry(activity,status):
    o,packet=activity
    with server(status=status,body=b'{}') as (port,_,seen):
        o.activity_port=port;p=prepare(o,packet);start(o,p);s=finish(o,p)
        assert s['state']=='ABORTED' and len(seen)==1
        assert s['summary']['attempts']==1 and s['summary']['native_closed']


@pytest.mark.parametrize('body',[b'{',b'null',b'{}',b'x'*65537,canonical([dict(id='activity::1',activity_type='DIV',value=SECRET)])],ids=['json','null','object','oversize','reflection'])
def test_invalid_response_never_becomes_page(activity,body):
    o,packet=activity
    with server(body=body) as (port,_,seen):
        o.activity_port=port;p=prepare(o,packet);start(o,p);s=finish(o,p)
        assert s['state']=='ABORTED' and len(seen)==1 and s['summary']['pages']==0
        assert s['summary']['native_closed']


def test_pending_cancel_closes_native_handles_and_prevents_replay(activity):
    o,packet=activity
    with server(stall=True) as (port,arrived,seen):
        o.activity_port=port;p=prepare(o,packet);start(o,p);o.a.tick();assert arrived.wait(1)
        transport=o.a._activities._producer._pending
        with pytest.raises(RuntimeRefused):o.a.require_checkpoint()
        s=send(o,'cancel',activity_id=p['activity_id'])
        assert s['state']=='CANCELED' and transport.native_closed
        with pytest.raises(RuntimeRefused):start(o,p)
        assert len(seen)==1


@pytest.mark.parametrize('fault',['context','history','credential','opening','health','deadline'])
def test_original_binding_change_refuses_before_get(activity,fault):
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet)
        if fault=='context':o.a._account_context.close()
        elif fault=='history':
            with o.a.db:o.a.db.execute("INSERT OR REPLACE INTO state VALUES('fake_attempt_conflict','1')")
        elif fault=='credential':
            from compertum.runtime.paper_credential_slot import SLOT_PATH
            (o.a.store.root/SLOT_PATH).write_bytes(b'changed encrypted slot')
        elif fault=='opening':
            with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key='paper_opening:fixture'")
        elif fault=='health':o.e.reason='TEST_HALT'
        else:o.clock.utc+=21;o.clock.mono+=21
        with pytest.raises(RuntimeRefused):start(o,p)
        assert not seen


def test_transaction_guards_preserve_pending_changes(activity):
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet)
        o.a.db.execute("INSERT INTO state VALUES('activity-caller-pending','1')")
        with pytest.raises(RuntimeRefused,match='TRANSACTION_OPEN'):send(o,'cancel',activity_id=p['activity_id'])
        assert o.a.db.in_transaction and o.a.db.execute("SELECT value FROM state WHERE key='activity-caller-pending'").fetchone()==('1',)
        o.a.db.rollback();assert not seen


def test_preparation_derives_absent_context_and_preserves_existing_context(activity):
    o,packet=activity;old=o.a._account_context;old.close();o.a._account_context=None
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet);current=o.a._account_context
        assert current is not old and current is o.a._activities._producer._context_input
        again=send(o,'prepare',activity_id=p['activity_id'],packet_id=packet['packet_id'],task_id=o.task,reservation_id=o.grant.grant_id)
        assert again==p and o.a._account_context is current and not seen


def test_record_shapes_and_false_authority_are_strict(activity):
    from copy import deepcopy
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet);start(o,p);s=finish(o,p)
        original=o.a._activities._read(p['activity_id'])
        for key,value in [('account_alias',[]),('reason',[]),('evidence',{}),('manifest',{}),('summary',{}),('binding',{}),('state','PUBLISHED')]:
            damaged=deepcopy(original);damaged[key]=value
            with pytest.raises((RuntimeRefused,ValueError,TypeError)):o.a._activities._validate(damaged)
        for key in ('transport_authorized','financial_accepted','native_transport_verified'):
            damaged=deepcopy(original);damaged['summary'][key]=True
            with pytest.raises(RuntimeRefused):o.a._activities._validate(damaged)
        assert s['state']=='EVIDENCE_READY'


def test_snapshot_binding_mutation_is_detected_after_expiry(activity):
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet);send(o,'cancel',activity_id=p['activity_id'])
    producer=o.a._activities._producer;o.clock.utc+=60;o.clock.mono+=60
    assert producer.snapshot()['state']=='CANCELED'
    producer._seed['history_sha256']='f'*64
    with pytest.raises(RuntimeRefused):producer.snapshot()


@pytest.fixture
def activity_publication(activity,monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from compertum.runtime import paper_activity_publication as module
    o,p=activity
    @contextmanager
    def scope(remote):yield
    monkeypatch.setattr(module,'_remote_scope',scope)
    def rpc(remote,action,payload):
        if action=='paper_activity':return o.a.activity_handle(payload)
        assert action=='paper_activity_transfer';return o.a.activity_transfer(payload)
    monkeypatch.setattr(module,'call_owner',rpc)
    remote=SimpleNamespace(descriptor=SimpleNamespace(registration=SimpleNamespace(project_id=o.e.lease.project_id,identity=SimpleNamespace(role='execution'))))
    return o,p,module.PaperActivityPublication(o.manager,remote),module,remote


def pub_start(fixture):
    o,packet,pub,_,_=fixture;aid=str(uuid4())
    p=pub.handle('a'*64,dict(operation='prepare',activity_id=aid,packet_id=packet['packet_id']))
    pub.handle('a'*64,dict(operation='authorize',activity_id=aid,plan_sha256=p['plan_sha256']))
    pub.handle('a'*64,dict(operation='start',activity_id=aid,plan_sha256=p['plan_sha256']))
    return p


def test_publication_lost_ack_and_restart_never_reissue_get(activity_publication,monkeypatch):
    from compertum.runtime.paper_activity_evidence import open_activity_evidence
    o,_,pub,module,remote=activity_publication
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=pub_start(activity_publication);finish(o,p)
        original=module.call_owner;acks=[]
        def lost_ack(remote,action,payload):
            value=original(remote,action,payload)
            if action=='paper_activity_transfer' and payload['operation']=='ack':acks.append(value);raise RuntimeRefused('SIMULATED_LOST_ACK')
            return value
        monkeypatch.setattr(module,'call_owner',lost_ack)
        for _ in range(12):pub.tick()
        r=pub._read(p['activity_id']);assert r['state']=='ACK_UNCONFIRMED' and len(acks)==1 and len(seen)==1
        for _ in range(8):pub.tick()
        assert len(acks)==1
        monkeypatch.setattr(module,'call_owner',original)
        restarted=module.PaperActivityPublication(o.manager,remote);restarted.tick()
        r=restarted._read(p['activity_id']);assert r['state']=='PUBLISHED' and r['ack_attempts']==2 and len(seen)==1
        assert o.a.activity_transfer(dict(operation='ack',activity_id=p['activity_id'],manifest=r['manifest']))['state']=='PUBLISHED'
        o.a._activities.close();o.a._activities=None
        assert send(o,'status',activity_id=p['activity_id'])['state']=='PUBLISHED'
        with open_activity_evidence(o.e.lease,'fixture',p['activity_id'],r['manifest']) as opened:assert opened.snapshot()['freshness']=='NOT_RESTORED'


def test_ack_exhaustion_is_durable_and_bounded(activity_publication,monkeypatch):
    o,_,pub,module,remote=activity_publication
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=pub_start(activity_publication);finish(o,p);original=module.call_owner;count=[]
        def lost(remote,action,payload):
            if action=='paper_activity_transfer' and payload['operation']=='ack':count.append(1);raise RuntimeRefused('LOST_ACK')
            return original(remote,action,payload)
        monkeypatch.setattr(module,'call_owner',lost)
        for _ in range(10):pub.tick()
        for _ in range(3):
            pub=module.PaperActivityPublication(o.manager,remote)
            for _ in range(6):pub.tick()
        assert len(count)==2 and pub._read(p['activity_id'])['state']=='ACK_UNCONFIRMED' and len(seen)==1


def test_restart_interrupts_unfinished_collection_and_never_regrants(activity):
    from compertum.runtime.paper_activity_owner import _ActivityOwner
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet);start(o,p);o.a._activities.close()
        o.a._activities=_ActivityOwner(o.a)
        assert send(o,'status',activity_id=p['activity_id'])['state']=='INTERRUPTED'
        with pytest.raises(RuntimeRefused):start(o,p)
        assert not seen


def test_duplicate_chunks_and_tampered_publication_remain_blocking(activity):
    from compertum.runtime.paper_activity_evidence import publish_activity_evidence,open_activity_evidence
    from copy import deepcopy
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet);start(o,p);s=finish(o,p)
    c=dict(operation='chunk',activity_id=p['activity_id'],offset=0,sha256=s['evidence']['sha256'])
    assert o.a.activity_transfer(c)==o.a.activity_transfer(c)
    cipher=o.a._activities._cipher;child=o.manager.split_grant(o.grant,len(cipher.ciphertext));m=publish_activity_evidence(o.manager,child,cipher)
    for key,value in [('sha256','f'*64),('size_bytes',1),('task_id',str(uuid4())),('path','artifacts/foreign.bin')]:
        bad=deepcopy(m);bad[key]=value
        with pytest.raises((RuntimeRefused,ValueError)):
            with open_activity_evidence(o.e.lease,'fixture',p['activity_id'],bad):pass
    with pytest.raises(RuntimeRefused):
        with open_activity_evidence(o.e.lease,'other',p['activity_id'],m):pass


def test_same_alias_held_credential_substitution_never_dispatches(activity):
    from compertum.runtime.paper_credentials import seal_paper_credentials
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet);producer=o.a._activities._producer
        producer._protected=seal_paper_credentials(o.e.lease,'fixture',bytearray(b'DIFFERENT_KEY_12345'),bytearray(b'DIFFERENT_SECRET_12345'))
        with pytest.raises(RuntimeRefused,match='CREDENTIAL_CHANGED'):start(o,p)
        assert not seen


def test_ack_compares_original_plan_binding_and_summary(activity):
    from copy import deepcopy
    from compertum.runtime.paper_activity_evidence import publish_activity_evidence
    from compertum.paper_activity_records import sha
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet);start(o,p);finish(o,p)
    helper=o.a._activities;original=helper._read(p['activity_id']);cipher=helper._cipher
    child=o.manager.split_grant(o.grant,len(cipher.ciphertext));m=publish_activity_evidence(o.manager,child,cipher)
    for fault in ('plan','summary'):
        damaged=deepcopy(original)
        if fault=='plan':
            damaged['binding']['seed']['history_sha256']='e'*64;damaged['plan_sha256']=sha(canonical(damaged['binding']))
        else:damaged['summary']['unsupported_activities']=1
        helper._validate(damaged)
        with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(canonical(damaged).decode(),'paper_activity:'+p['activity_id']))
        with pytest.raises(RuntimeRefused,match='PUBLICATION_CHANGED'):o.a.activity_transfer(dict(operation='ack',activity_id=p['activity_id'],manifest=m))
        with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(canonical(original).decode(),'paper_activity:'+p['activity_id']))
    assert o.a.activity_transfer(dict(operation='ack',activity_id=p['activity_id'],manifest=m))['state']=='PUBLISHED'


@pytest.mark.parametrize('mode',['http_error','cancel'])
def test_restart_preserves_terminal_failed_evidence(activity,mode):
    from compertum.runtime.paper_activity_owner import _ActivityOwner
    o,packet=activity
    with server(status=403) as (port,_,seen):
        o.activity_port=port;p=prepare(o,packet)
        if mode=='cancel':send(o,'cancel',activity_id=p['activity_id'])
        else:start(o,p);finish(o,p)
        original=o.a._activities._read(p['activity_id']);o.a._activities.close()
        o.a._activities=_ActivityOwner(o.a)
        assert o.a._activities._read(p['activity_id'])==original
        assert original['reason']==('CANCELED' if mode=='cancel' else 'HTTP_STATUS_UNACCEPTABLE')
        if mode=='http_error':assert original['summary']['attempts']==1


def test_restart_after_consuming_second_ack_makes_no_rpc(activity_publication,monkeypatch):
    o,_,pub,module,remote=activity_publication
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=pub_start(activity_publication);finish(o,p)
        for _ in range(12):pub.tick()
        r=pub._read(p['activity_id']);assert r['state']=='PUBLISHED'
        r.update(state='ACK_PENDING',ack_attempts=2);pub._save(r)
        def forbidden(*args):raise AssertionError('Consumed ACK repeated')
        monkeypatch.setattr(module,'call_owner',forbidden)
        restarted=module.PaperActivityPublication(o.manager,remote)
        for _ in range(5):restarted.tick()
        assert restarted._read(p['activity_id'])['state']=='ACK_UNCONFIRMED' and len(seen)==1


def test_rejected_local_start_keeps_execution_channel_healthy(activity_publication,monkeypatch):
    from contextlib import contextmanager
    o,packet,pub,module,remote=activity_publication
    o.activity_port=1  # No request starts: this case cancels the prepared plan.
    healthy=[True]
    @contextmanager
    def scope(endpoint):
        assert healthy[0]
        try:yield
        except BaseException:
            healthy[0]=False;raise
    monkeypatch.setattr(module,'_remote_scope',scope)
    aid=str(uuid4())
    p=pub.handle('a'*64,dict(operation='prepare',activity_id=aid,packet_id=packet['packet_id']))
    pub.handle('a'*64,dict(operation='cancel',activity_id=aid))
    pub.tick()
    assert pub.entries[aid]['phase']=='COLLECT'
    with pytest.raises(RuntimeRefused):pub.handle('a'*64,dict(operation='start',activity_id=aid,plan_sha256=p['plan_sha256']))
    assert healthy[0]
    assert pub.handle('a'*64,dict(operation='status',activity_id=aid))['state']=='CANCELED'


@pytest.mark.parametrize('fault',['subject','hash','packet','extra'])
def test_forged_start_or_prepare_refuses(activity,fault):
    o,packet=activity
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=prepare(o,packet)
        command=dict(operation='authorize',activity_id=p['activity_id'],plan_sha256=p['plan_sha256'])
        subject='b'*64 if fault=='subject' else 'a'*64
        if fault=='hash':command['plan_sha256']='0'*64
        if fault=='packet':command['activity_id']=str(uuid4())
        if fault=='extra':command['native_transport_verified']=True
        with pytest.raises(RuntimeRefused):o.a.activity_handle(dict(subject_key=subject,command=command))
        assert not seen
