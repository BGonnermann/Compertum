"""Native stores/DPAPI; account origin, reserve capacity and clocks are simulated."""
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.service_budget import queue_for
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication
from test_paper_account_binding import invented_paper_origin,propose,confirm
from test_paper_read_preparation import ACCOUNT,KEY,SECRET


@pytest.fixture
def account(publication,invented_paper_origin):
    o,pub,p,r=propose(publication);confirm(pub,p,r)
    return o,pub,p


def packet(operation,*,request=None,subject='a'*64,**values):
    return dict(request_id=request or str(uuid4()),subject_key=subject,command=dict(operation=operation,**values))


def acknowledge(fixture,request=None):
    o,_,p=fixture;command=packet('acknowledge',request=request,packet_id=p['packet_id'])
    return command,o.a.presence_handle(command)


def inspect(o,receipt):
    return o.a.presence_handle(packet('inspect',presence_id=receipt['presence_id']))


def advance(o,seconds):
    # Service each clock step and keep the independent mutual-health fixture live.
    while seconds>0:
        step=min(1,seconds);seconds-=step
        o.clock.utc+=step;o.clock.mono+=step;o.c.utc+=step;o.c.mono+=step
        connect(o.e,o.w);o.a.tick()


def test_presence_records_authenticated_identity_without_broker_authority(account):
    o,_,p=account;calls=len(o.calls);quota=queue_for(o.e.lease).status()
    request,r=acknowledge(account);v=inspect(o,r)
    assert r['presence_id']==request['request_id'] and r['packet_id']==p['packet_id']
    assert r['status']=='ACKNOWLEDGEMENT_RECORDED' and r['current_presence']=='NOT_ASSERTED'
    assert v['presence_status']=='CURRENT' and v['order_admission']=='BLOCKED'
    assert r['transport_authorized'] is v['transport_authorized'] is False
    assert r['financial_accepted'] is v['financial_accepted'] is False
    assert all(s not in json.dumps((r,v)) for s in (ACCOUNT,KEY,SECRET))
    assert len(o.calls)==calls and queue_for(o.e.lease).status()==quota and o.a._market is None
    assert o.a.db.execute("SELECT 1 FROM sqlite_master WHERE name='fake_intents'").fetchone() is None


def test_duplicate_acknowledgement_keeps_original_times_and_no_new_records(account):
    o,_,_=account;request,r=acknowledge(account);changes=o.a.db.total_changes
    advance(o,5)
    assert o.a.presence_handle(request)==r and o.a.db.total_changes==changes
    assert inspect(o,r)['presence_status']=='CURRENT'


@pytest.mark.parametrize('fault',['subject','packet','extra'])
def test_duplicate_or_untrusted_packet_changes_refuse(account,fault):
    o,_,_=account;request,_=acknowledge(account)
    if fault=='subject':request['subject_key']='b'*64
    elif fault=='packet':request['command']['packet_id']=str(uuid4())
    else:request['command']['present']=True
    with pytest.raises(RuntimeRefused):o.a.presence_handle(request)


def test_presence_lasts_five_minutes_without_renewing_account_freshness(account):
    o,_,p=account;_,r=acknowledge(account);advance(o,31)
    with pytest.raises(RuntimeRefused):o.a.preflight(p['packet_id'])
    assert inspect(o,r)['presence_status']=='CURRENT'
    advance(o,268.999);assert inspect(o,r)['presence_status']=='CURRENT'
    advance(o,.001);v=inspect(o,r)
    assert v['presence_status']=='INVALIDATED' and v['reason']=='PAPER_PRESENCE_EXPIRED'


@pytest.mark.parametrize('fault',['gap','reverse','drift','health','restart'])
def test_invalidated_presence_cannot_revive(account,fault):
    o,_,_=account;request,r=acknowledge(account);utc,mono=o.clock.utc,o.clock.mono
    if fault=='gap':o.clock.utc+=16;o.clock.mono+=16
    elif fault=='reverse':o.clock.utc-=1;o.clock.mono-=1
    elif fault=='drift':o.clock.utc+=6
    elif fault=='health':o.e.halt('INVENTED_HEALTH_LOSS')
    else:o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
    assert inspect(o,r)['presence_status']=='INVALIDATED'
    o.clock.utc,o.clock.mono=utc,mono
    assert inspect(o,r)['presence_status']=='INVALIDATED'
    assert o.a.presence_handle(request)==r


def test_same_identity_new_packet_preserves_original_presence(account,publication):
    o,_,_=account;_,r=acknowledge(account)
    _,pub,p,proposal=propose(publication);confirm(pub,p,proposal)
    assert inspect(o,r)['presence_status']=='CURRENT' and r['packet_id']!=p['packet_id']


def test_unconfirmed_packet_is_not_native_presence(publication):
    o,_,p,_=propose(publication)
    with pytest.raises(RuntimeRefused):o.a.presence_handle(packet('acknowledge',packet_id=p['packet_id']))


@pytest.mark.parametrize('kind',['position','foreign_order','negative_cash','closed_market','halted_admission'])
def test_presence_does_not_claim_or_require_action_specific_readiness(publication,invented_paper_origin,monkeypatch,kind):
    import test_paper_read_owner as fixture
    from test_paper_portfolio import order
    original=fixture.body
    def changed(op):
        value=original(op)
        if op=='POSITIONS' and kind=='position':return [None]
        if op=='ORDERS' and kind=='foreign_order':return [order(1,client_order_id='foreign-order')]
        if op=='ACCOUNT' and kind=='negative_cash':return dict(value,cash='-1')
        if op=='CLOCK' and kind=='closed_market':return dict(value,is_open=False,timestamp='2023-11-24T14:29:00Z',next_open='2023-11-24T14:30:00Z')
        return value
    monkeypatch.setattr(fixture,'body',changed)
    if kind=='closed_market':publication[0].clock.utc-=60
    o,pub,p,proposal=propose(publication);confirm(pub,p,proposal)
    if kind=='halted_admission':
        with o.a.db:o.a.db.execute("INSERT INTO state VALUES('admission','\"HALTED\"') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    _,r=acknowledge((o,pub,p))
    assert inspect(o,r)['presence_status']=='CURRENT' and o.a._market is None


def test_ignored_presence_insert_is_not_acknowledged(account):
    o,_,_=account;acknowledge(account)
    o.a.db.execute('CREATE TRIGGER deny_presence BEFORE INSERT ON paper_presence_records BEGIN SELECT RAISE(IGNORE); END')
    with pytest.raises(RuntimeRefused):acknowledge(account)
    assert o.a.db.execute('SELECT count(*) FROM paper_presence_records').fetchone()==(1,)


@pytest.mark.parametrize('fault',['body','digest','missing_version'])
def test_corrupt_presence_evidence_is_not_current(account,fault):
    o,_,_=account;_,r=acknowledge(account)
    with o.a.db:
        if fault=='body':o.a.db.execute("UPDATE paper_presence_records SET body='{}'")
        elif fault=='digest':o.a.db.execute("UPDATE paper_presence_records SET sha256=?",('b'*64,))
        else:o.a.db.execute("DELETE FROM state WHERE key='paper_presence_version'")
    with pytest.raises(RuntimeRefused):inspect(o,r)


@dataclass(frozen=True)
class Decision:
    request_id:str
    subject_key:str


def test_presence_route_forwards_only_authenticated_identity_and_never_enables_writes(owner,monkeypatch):
    from compertum.runtime import supervisor as module
    from compertum.runtime.bootstrap import validate_worker_commands
    from compertum.domain import capability_for
    assert 'paper_presence' in module.ACTIONS and capability_for('paper_presence').exit_code==0
    for action in ('paper.arm','paper.start','paper.cancel','paper.close'):assert capability_for(action).exit_code!=0
    for role in ('execution','watchdog','evaluation'):
        with pytest.raises(RuntimeRefused):validate_worker_commands(role,frozenset({'paper_presence'}))
    s=object.__new__(module.Supervisor);s.partial_fixture=False;s.execution=SimpleNamespace(remote=object());calls=[]
    monkeypatch.setattr(module,'call_owner',lambda remote,action,payload:calls.append((action,payload)))
    decision=Decision(str(uuid4()),'c'*64);command=dict(operation='inspect',presence_id=str(uuid4()))
    s._dispatch(decision,'paper_presence',command)
    assert calls==[('paper_presence',dict(request_id=decision.request_id,subject_key=decision.subject_key,command=command))]


def test_presence_inspection_is_never_cached(owner,monkeypatch):
    from compertum.runtime import supervisor as module
    o=owner;s=object.__new__(module.Supervisor);s.store=o.manager.store;calls=[]
    with s.store.conn:s.store.conn.execute('CREATE TABLE operator_requests(request_id TEXT PRIMARY KEY,binding TEXT NOT NULL,result TEXT,error TEXT)')
    s._dispatch=lambda *args:calls.append(args) or dict(current=len(calls)==1)
    decision=Decision(str(uuid4()),'a'*64);payload=dict(operation='inspect',presence_id=str(uuid4()))
    assert s.handle(decision,'paper_presence',payload)['current']
    assert not s.handle(decision,'paper_presence',payload)['current']
    assert s.store.conn.execute('SELECT count(*) FROM operator_requests').fetchone()==(0,)


@pytest.mark.parametrize('fault',['body','missing_version'])
def test_observed_corruption_cannot_revive_after_original_bytes_are_restored(account,fault):
    o,_,_=account;_,r=acknowledge(account)
    original=o.a.db.execute('SELECT body FROM paper_presence_records').fetchone()[0]
    with o.a.db:
        if fault=='body':o.a.db.execute("UPDATE paper_presence_records SET body='{}'")
        else:o.a.db.execute("DELETE FROM state WHERE key='paper_presence_version'")
    with pytest.raises(RuntimeRefused):inspect(o,r)
    with o.a.db:
        if fault=='body':o.a.db.execute('UPDATE paper_presence_records SET body=?',(original,))
        else:o.a.db.execute("INSERT INTO state VALUES('paper_presence_version','1')")
    assert inspect(o,r)['presence_status']=='INVALIDATED'


def test_replaced_mutual_health_object_does_not_preserve_presence(account):
    from copy import copy
    o,_,_=account;_,r=acknowledge(account);original=o.a.health
    o.a.health=copy(original)
    assert inspect(o,r)['presence_status']=='INVALIDATED'
    o.a.health=original
    assert inspect(o,r)['presence_status']=='INVALIDATED'


@pytest.mark.parametrize('fault',['credentials','ignored_revocation'])
def test_credential_changes_and_failed_revocation_never_revive(account,monkeypatch,fault):
    import compertum.runtime.paper_presence as module
    from compertum.runtime.paper_credentials import seal_paper_credentials
    o,_,_=account;_,r=acknowledge(account);original=module.load_paper_slot
    replacement=seal_paper_credentials(o.a.lease,'fixture',bytearray(b'DIFFERENTKEY'),bytearray(b'DIFFERENTSECRET'))
    monkeypatch.setattr(module,'load_paper_slot',lambda *a:replacement)
    if fault=='ignored_revocation':
        o.a.db.execute('CREATE TRIGGER deny_revoke BEFORE UPDATE ON paper_presence_records BEGIN SELECT RAISE(IGNORE); END')
        with pytest.raises(RuntimeRefused):inspect(o,r)
        o.a.db.execute('DROP TRIGGER deny_revoke')
    else:assert inspect(o,r)['presence_status']=='INVALIDATED'
    monkeypatch.setattr(module,'load_paper_slot',original)
    assert inspect(o,r)['presence_status']=='INVALIDATED'


@pytest.mark.parametrize('fault',['clock','health','closed','replaced'])
def test_invalidation_during_secrecy_scan_never_returns_current(account,monkeypatch,fault):
    import compertum.runtime.paper_presence as module
    o,_,_=account;_,r=acknowledge(account);original=module._reject_reflections
    def interrupted(*args):
        result=original(*args)
        if fault=='clock':o.clock.utc+=16;o.clock.mono+=16
        elif fault=='health':o.e.halt('INVENTED_SCAN_HEALTH_LOSS')
        elif fault=='closed':o.a._presence.close()
        else:o.a._presence=module._PresenceOwner(o.a)
        return result
    monkeypatch.setattr(module,'_reject_reflections',interrupted)
    assert inspect(o,r)['presence_status']=='INVALIDATED'


def test_trusted_native_launch_offer_matches_owner_endpoint_without_spawning_a_child(tmp_path,monkeypatch):
    from compertum.runtime import managed,managed_owner
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    project=resolve_project(tmp_path);supervisor=acquire_owner(project,'supervisor');observed={}
    class StopBeforeLaunch(Exception):pass
    def offered(lease,*,role,allowed_commands):
        assert lease is supervisor and role=='execution';observed['offer']=allowed_commands
        raise StopBeforeLaunch()
    def endpoint(lease,commands):
        observed['endpoint']=commands;raise StopBeforeLaunch()
    monkeypatch.setattr(managed,'prepare_owner_channel',offered)
    monkeypatch.setattr(managed_owner,'start_role_pipe',endpoint)
    monkeypatch.setattr(managed_owner.sys,'argv',['owner','123',json.dumps(dict(root=str(tmp_path),role='execution'))])
    try:
        with pytest.raises(StopBeforeLaunch):managed.launch_owner(supervisor,'execution')
        with pytest.raises(StopBeforeLaunch):managed_owner.main()
    finally:release_owner(supervisor)
    assert observed['offer']==observed['endpoint'] and 'paper_presence' in observed['offer']


def test_failed_schema_version_insert_rolls_back_the_whole_new_schema(account):
    o,_,_=account
    o.a.db.execute("CREATE TRIGGER deny_presence_version BEFORE INSERT ON state WHEN NEW.key='paper_presence_version' BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(RuntimeRefused):acknowledge(account)
    assert o.a.db.execute("SELECT 1 FROM sqlite_master WHERE name='paper_presence_records'").fetchone() is None
    assert o.a.db.execute("SELECT 1 FROM state WHERE key='paper_presence_version'").fetchone() is None


@pytest.mark.parametrize('fault',['reason_rollback','missing_record'])
def test_restoring_original_rows_never_revives_observed_invalidity(account,monkeypatch,fault):
    import compertum.runtime.paper_presence as module
    from compertum.runtime.paper_credentials import seal_paper_credentials
    o,_,_=account;_,r=acknowledge(account)
    row=o.a.db.execute('SELECT * FROM paper_presence_records').fetchone()
    if fault=='reason_rollback':
        original=module.load_paper_slot
        replacement=seal_paper_credentials(o.a.lease,'fixture',bytearray(b'OTHERKEY'),bytearray(b'OTHERSECRET'))
        monkeypatch.setattr(module,'load_paper_slot',lambda *a:replacement)
        assert inspect(o,r)['presence_status']=='INVALIDATED'
        monkeypatch.setattr(module,'load_paper_slot',original)
    else:
        with o.a.db:o.a.db.execute('DELETE FROM paper_presence_records')
        with pytest.raises(RuntimeRefused):inspect(o,r)
    with o.a.db:o.a.db.execute('INSERT OR REPLACE INTO paper_presence_records VALUES(?,?,?,?)',row)
    try:result=inspect(o,r)
    except RuntimeRefused:return
    assert result['presence_status']=='INVALIDATED'


@pytest.mark.parametrize('fault',['clock','health','credentials'])
def test_invalidation_during_acknowledgement_rolls_back_receipt(account,monkeypatch,fault):
    import compertum.runtime.paper_presence as module
    from compertum.runtime.paper_credentials import seal_paper_credentials
    o,_,_=account;original=module._reject_reflections
    def invalidated(*args):
        result=original(*args)
        if fault=='clock':o.clock.utc+=16;o.clock.mono+=16
        elif fault=='health':o.e.halt('INVENTED_ACK_HEALTH_LOSS')
        else:
            replacement=seal_paper_credentials(o.a.lease,'fixture',bytearray(b'ACKOTHERKEY'),bytearray(b'ACKOTHERSECRET'))
            monkeypatch.setattr(module,'load_paper_slot',lambda *a:replacement)
        return result
    monkeypatch.setattr(module,'_reject_reflections',invalidated)
    with pytest.raises(RuntimeRefused):acknowledge(account)
    assert o.a.db.execute('SELECT count(*) FROM paper_presence_records').fetchone()==(0,)
    assert not o.a._presence._issued


def test_presence_is_private_and_history_is_bounded(account):
    import pickle
    o,_,_=account;_,r=acknowledge(account)
    with pytest.raises(RuntimeRefused):pickle.dumps(o.a._presence)
    assert all(s not in repr(o.a._presence) for s in (ACCOUNT,KEY,SECRET))
    row=o.a.db.execute('SELECT sha256,body,reason FROM paper_presence_records').fetchone()
    # Count-bound probe; invented extra rows are never treated as valid receipts.
    with o.a.db:
        o.a.db.executemany('INSERT INTO paper_presence_records VALUES(?,?,?,?)',[(str(uuid4()),*row) for _ in range(127)])
    with pytest.raises(RuntimeRefused,match='PAPER_PRESENCE_HISTORY_BOUND'):acknowledge(account)
    assert o.a.db.execute('SELECT count(*) FROM paper_presence_records').fetchone()==(128,)
    assert inspect(o,r)['presence_status']=='CURRENT'


def test_foreign_subject_cannot_inspect_presence(account):
    o,_,_=account;_,r=acknowledge(account)
    with pytest.raises(RuntimeRefused,match='READ_OPERATOR_CHANGED'):
        o.a.presence_handle(packet('inspect',subject='b'*64,presence_id=r['presence_id']))
    assert inspect(o,r)['presence_status']=='CURRENT'


@pytest.mark.parametrize('fault',['oversized','wrong_type','self_consistent_rewrite'])
def test_invalid_record_bytes_cannot_assert_presence(account,fault):
    import hashlib
    from compertum.data.encoding import canonical
    o,_,_=account;_,r=acknowledge(account)
    raw=o.a.db.execute('SELECT body FROM paper_presence_records').fetchone()[0]
    if fault=='oversized':raw=' '*8193
    else:
        body=json.loads(raw);body['owner_generation']=True if fault=='wrong_type' else body['owner_generation']+1
        raw=canonical(body).decode()
    with o.a.db:o.a.db.execute('UPDATE paper_presence_records SET body=?,sha256=?',(raw,hashlib.sha256(raw.encode()).hexdigest()))
    with pytest.raises(RuntimeRefused):inspect(o,r)


@pytest.mark.parametrize('fault',['inspect_alias','inspect_confirmation','ack_alias','ack_confirmation'])
def test_changed_originals_during_final_evidence_read_never_qualify(account,monkeypatch,fault):
    from contextlib import contextmanager
    import compertum.runtime.paper_presence as module
    o,_,p=account;mode,kind=fault.split('_');r=None
    if mode=='inspect':_,r=acknowledge(account)
    original=module.open_read_evidence;calls=[0]
    @contextmanager
    def changed(*args,**kwargs):
        with original(*args,**kwargs) as value:yield value
        calls[0]+=1
        if calls[0]==(2 if mode=='inspect' else 1):
            key='paper_account_alias:fixture' if kind=='alias' else module.binding._PREFIX+p['packet_id']
            # The enclosing acknowledgement owns its transaction; do not commit it here.
            o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,))
    monkeypatch.setattr(module,'open_read_evidence',changed)
    if mode=='ack':
        with pytest.raises(RuntimeRefused):acknowledge(account)
        assert o.a.db.execute('SELECT count(*) FROM paper_presence_records').fetchone()==(0,)
    else:
        assert inspect(o,r)['presence_status']=='INVALIDATED'
    assert calls[0]==(2 if mode=='inspect' else 1)


@pytest.mark.parametrize('fault',['health','health_persisted','stale','preflight_closed','preflight_replaced','proposal_closed','proposal_replaced','alias','confirmation','presence_record'])
def test_final_preflight_callback_cannot_commit_invalid_acknowledgement(account,monkeypatch,fault):
    import compertum.runtime.paper_presence as presence
    import compertum.runtime.paper_preflight as preflight
    o,_,_=account
    if fault=='health_persisted':
        from compertum.runtime.execution_health import disarm_execution
        o.e.on_halt=lambda reason:disarm_execution(o.a.store,reason)
    if fault=='stale':advance(o,29)
    final=[False];fired=[False];original=presence._PresenceOwner._originals;scan=preflight._reject_reflections
    def originals(self,p):
        result=original(self,p);final[0]=True;return result
    def interrupted(*args):
        result=scan(*args)
        if final[0] and not fired[0]:
            fired[0]=True
            if fault in ('health','health_persisted'):o.e.halt('INVENTED_FINAL_PREFLIGHT_HEALTH_LOSS')
            elif fault=='stale':o.clock.utc+=2;o.clock.mono+=2
            elif fault=='preflight_closed':o.a._preflight.close()
            elif fault=='preflight_replaced':o.a._preflight=SimpleNamespace(close=lambda:None)
            elif fault=='proposal_closed':o.a._account_proposal.close()
            elif fault=='proposal_replaced':o.a._account_proposal=SimpleNamespace(close=lambda:None)
            elif fault=='presence_record':
                o.a.db.execute("UPDATE paper_presence_records SET body='{}'")
                o.a.db.execute("CREATE TRIGGER corrupt_presence AFTER INSERT ON paper_presence_records BEGIN UPDATE paper_presence_records SET body='{}'; END")
            else:
                key='paper_account_alias:fixture' if fault=='alias' else presence.binding._PREFIX+account[2]['packet_id']
                o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,))
        return result
    monkeypatch.setattr(presence._PresenceOwner,'_originals',originals)
    monkeypatch.setattr(preflight,'_reject_reflections',interrupted)
    with pytest.raises(RuntimeRefused):acknowledge(account)
    assert fired[0] and not o.a._presence._issued
    assert o.a.db.execute('SELECT count(*) FROM paper_presence_records').fetchone()==(0,)
