"""Native stores/DPAPI; simulated account origin, clocks and reserve capacity."""
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication,launch
from test_paper_account_binding import invented_paper_origin,propose,confirm,call
from test_paper_presence import account,packet,acknowledge,inspect
from test_paper_account_context import context


def during_second_slot_load(monkeypatch,module,change):
    import compertum.runtime.paper_credential_slot as slot
    load=module.load_paper_slot;scan=slot._reject_reflections;calls=[0];armed=[False];fired=[False]
    def wrapped(*args):
        calls[0]+=1;armed[0]=calls[0]==2
        try:return load(*args)
        finally:armed[0]=False
    def changed(*args):
        scan(*args)
        if armed[0] and not fired[0]:fired[0]=True;change()
    monkeypatch.setattr(module,'load_paper_slot',wrapped)
    monkeypatch.setattr(slot,'_reject_reflections',changed)
    return fired


def replacement_slot(o):
    from compertum.runtime.paper_credential_slot import _payload
    from compertum.runtime.paper_credentials import seal_paper_credentials
    return _payload(seal_paper_credentials(o.e.lease,'fixture',bytearray(b'NEW_FIXTURE_KEY'),bytearray(b'NEW_FIXTURE_SECRET')))


@pytest.mark.parametrize('fault',['current_artifact','first_artifact','alias','history','slot'])
def test_account_final_credential_callback_refuses_changed_originals(account,monkeypatch,fault):
    import compertum.runtime.paper_account_context as module
    from compertum.runtime.paper_credential_slot import SLOT_PATH
    o,pub,first=account;first_manifest=pub._route(first['packet_id'])['publication']['manifest']
    later=launch((o,pub,None))
    for _ in range(10):pub.tick()
    proposal=call(pub,later,'account_propose');confirm(pub,later,proposal)
    ctx=context((o,pub,later));manifest=pub._route(later['packet_id'])['publication']['manifest']
    assert first['packet_id']!=later['packet_id'] and first_manifest['path']!=manifest['path']
    assert ctx.diagnostic()['opening_status']=='CURRENT_CLEAN_OPENING'
    path=o.manager.root/(SLOT_PATH if fault=='slot' else (first_manifest if fault=='first_artifact' else manifest)['path'])
    old_bytes=path.read_bytes();replacement=replacement_slot(o)
    key='paper_account_alias:fixture' if fault=='alias' else 'fake_attempt_guard_head'
    old_row=o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0]
    def change():
        if fault in ('alias','history'):
            with o.a.db:assert o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,)).rowcount==1
        else:path.write_bytes(replacement if fault=='slot' else b'invented final account corruption')
    fired=during_second_slot_load(monkeypatch,module,change)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
    assert fired[0] and ctx._closed
    path.write_bytes(old_bytes)
    with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(old_row,key))
    with pytest.raises(RuntimeRefused):ctx.diagnostic()


@pytest.mark.parametrize('fault',['artifact','slot','alias','revocation'])
def test_presence_inspection_final_slot_callback_never_reports_current(account,monkeypatch,fault):
    import compertum.runtime.paper_presence as module
    from compertum.runtime.paper_credential_slot import SLOT_PATH
    o,pub,p=account;_,receipt=acknowledge(account)
    manifest=pub._route(p['packet_id'])['publication']['manifest']
    path=o.manager.root/(SLOT_PATH if fault=='slot' else manifest['path']);old_bytes=path.read_bytes();replacement=replacement_slot(o)
    key='paper_account_alias:fixture';old_row=o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0]
    def change():
        if fault=='alias':
            with o.a.db:assert o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,)).rowcount==1
        elif fault=='revocation':
            with o.a.db:assert o.a.db.execute("UPDATE paper_presence_records SET reason='INVENTED_REVOCATION' WHERE presence_id=?",(receipt['presence_id'],)).rowcount==1
        else:path.write_bytes(replacement if fault=='slot' else b'invented final presence corruption')
    fired=during_second_slot_load(monkeypatch,module,change)
    value=inspect(o,receipt);assert fired[0] and value['presence_status']=='INVALIDATED'
    path.write_bytes(old_bytes)
    with o.a.db:
        o.a.db.execute('UPDATE state SET value=? WHERE key=?',(old_row,key))
        o.a.db.execute('UPDATE paper_presence_records SET reason=NULL WHERE presence_id=?',(receipt['presence_id'],))
    assert inspect(o,receipt)['presence_status']=='INVALIDATED'


@pytest.mark.parametrize('fault',['artifact','slot'])
def test_presence_acknowledgement_final_slot_callback_cannot_insert(account,monkeypatch,fault):
    import compertum.runtime.paper_presence as module
    from compertum.runtime.paper_credential_slot import SLOT_PATH
    o,pub,p=account;manifest=pub._route(p['packet_id'])['publication']['manifest']
    path=o.manager.root/(SLOT_PATH if fault=='slot' else manifest['path']);replacement=replacement_slot(o)
    fired=during_second_slot_load(monkeypatch,module,lambda:path.write_bytes(replacement if fault=='slot' else b'invented acknowledgement corruption'))
    request=packet('acknowledge',packet_id=p['packet_id'])
    insert_attempts=[0]
    def count_insert(statement):
        text=statement.lstrip().upper()
        if text.startswith('INSERT') and 'PAPER_PRESENCE_RECORDS' in text:insert_attempts[0]+=1
    o.a.db.set_trace_callback(count_insert)
    try:
        with pytest.raises(RuntimeRefused):o.a.presence_handle(request)
    finally:o.a.db.set_trace_callback(None)
    assert fired[0] and o.a.db.execute('SELECT count(*) FROM paper_presence_records').fetchone()==(0,)
    assert insert_attempts[0]==0 and not o.a._presence._issued


def test_presence_inspection_final_live_boundary_cannot_hide_revocation(account,monkeypatch):
    import compertum.runtime.paper_presence as module
    o,_,_=account;_,receipt=acknowledge(account);calls=[0];fired=[False]
    live=module._live
    def changed(*args):
        result=live(*args);calls[0]+=1
        if calls[0]==2 and not fired[0]:
            fired[0]=True
            with o.a.db:assert o.a.db.execute("UPDATE paper_presence_records SET reason='INVENTED_LATE_REVOCATION' WHERE presence_id=?",(receipt['presence_id'],)).rowcount==1
        return result
    monkeypatch.setattr(module,'_live',changed)
    value=inspect(o,receipt);assert fired[0] and value['presence_status']=='INVALIDATED'
    with o.a.db:o.a.db.execute('UPDATE paper_presence_records SET reason=NULL WHERE presence_id=?',(receipt['presence_id'],))
    assert inspect(o,receipt)['presence_status']=='INVALIDATED'
