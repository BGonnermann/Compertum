"""Planned native persistence regressions; simulated origin/clock/reserve fixtures."""
import hashlib,json
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_native_intent_cancel import cancellation,prepare,confirm_intent,inspect,account,publication,owner,pair,invented_paper_origin
from test_paper_presence import packet,advance


@pytest.mark.parametrize('table',['paper_native_intents','paper_native_confirmations'])
@pytest.mark.parametrize('fault',['missing','oversized','rewrite'])
def test_record_corruption_cannot_be_restored_to_live_authority(cancellation,table,fault):
    o=cancellation[0][0];_,r=prepare(cancellation);confirm_intent(o,r)
    row=o.a.db.execute('SELECT * FROM '+table).fetchone()
    columns=[c[1] for c in o.a.db.execute('PRAGMA table_info('+table+')')]
    with o.a.db:
        if fault=='missing':o.a.db.execute('DELETE FROM '+table)
        else:
            body=' '*16385 if fault=='oversized' else canonical(dict(json.loads(row[columns.index('body')]),owner_generation=o.e.lease.generation+1)).decode()
            o.a.db.execute('UPDATE '+table+' SET body=?,sha256=?',(body,hashlib.sha256(body.encode()).hexdigest()))
    try:
        try:v=inspect(o,r)
        except RuntimeRefused:pass
        else:assert v['intent_status']=='INVALIDATED'
    finally:
        (o.a.store.root/('injected-'+table+'-'+fault+'.json')).write_text(json.dumps(dict(columns=columns,observed=o.a.db.execute('SELECT * FROM '+table).fetchall())))
        with o.a.db:o.a.db.execute('INSERT OR REPLACE INTO '+table+' VALUES('+','.join('?' for _ in row)+')',row)
    try:v=inspect(o,r)
    except RuntimeRefused:return
    assert v['intent_status']=='INVALIDATED'


@pytest.mark.parametrize('phase',['prepare','confirm'])
def test_ignored_insert_never_becomes_an_accepted_record(cancellation,phase):
    o=cancellation[0][0];_,r=prepare(cancellation)
    table='paper_native_intents' if phase=='prepare' else 'paper_native_confirmations'
    prior=o.a.db.execute('SELECT count(*) FROM '+table).fetchone()[0]
    with o.a.db:o.a.db.execute('CREATE TRIGGER ignore_native_insert BEFORE INSERT ON '+table+' BEGIN SELECT RAISE(IGNORE); END')
    with pytest.raises(RuntimeRefused):
        if phase=='prepare':prepare(cancellation)
        else:confirm_intent(o,r)
    assert o.a.db.execute('SELECT count(*) FROM '+table).fetchone()==(prior,)


@pytest.mark.parametrize('phase',['prepare','confirm'])
@pytest.mark.parametrize('fault',['health','durable_health','account','presence','elapsed'])
def test_late_callback_cannot_commit_a_refused_record(cancellation,monkeypatch,phase,fault):
    import compertum.runtime.paper_native_intents as module
    from compertum.runtime.execution_health import disarm_execution
    o=cancellation[0][0];r=None
    if phase=='confirm':_,r=prepare(cancellation)
    if fault=='durable_health':o.e.on_halt=lambda reason:disarm_execution(o.a.store,reason)
    if fault=='elapsed':advance(o,29)
    original=module._reject_reflections;fired=[False]
    def changed(*args):
        result=original(*args)
        if not fired[0]:
            fired[0]=True
            if fault in ('health','durable_health'):o.e.halt('INVENTED_INTENT_CALLBACK_HALT')
            elif fault=='account':o.a._account_context.close()
            elif fault=='presence':o.a._presence.close()
            else:o.clock.utc+=2;o.clock.mono+=2
        return result
    monkeypatch.setattr(module,'_reject_reflections',changed)
    with pytest.raises(RuntimeRefused):
        if phase=='prepare':prepare(cancellation)
        else:confirm_intent(o,r)
    assert fired[0]
    table='paper_native_intents' if phase=='prepare' else 'paper_native_confirmations'
    assert o.a.db.execute('SELECT count(*) FROM '+table).fetchone()==(0,)
    assert not o.a.db.in_transaction


def test_open_caller_transaction_is_never_committed_or_rolled_back(cancellation):
    o=cancellation[0][0]
    with o.a.db:o.a.db.execute('CREATE TABLE caller_pending(value INTEGER)')
    o.a.db.execute('INSERT INTO caller_pending VALUES(7)')
    with pytest.raises(RuntimeRefused):prepare(cancellation)
    assert o.a.db.in_transaction and o.a.db.execute('SELECT value FROM caller_pending').fetchone()==(7,)
    o.a.db.rollback();assert o.a.db.execute('SELECT value FROM caller_pending').fetchone() is None


@pytest.mark.parametrize('phase',['prepare','confirm'])
@pytest.mark.parametrize('fault',['alias','presence','elapsed'])
def test_post_insert_mutation_rolls_back_before_dependency_revocation(cancellation,phase,fault):
    o=cancellation[0][0];_,r=prepare(cancellation)
    table='paper_native_intents' if phase=='prepare' else 'paper_native_confirmations'
    prior=o.a.db.execute('SELECT count(*) FROM '+table).fetchone()[0];fired=[]
    if fault=='elapsed':advance(o,28)
    def observe():
        fired.append(True)
        if fault=='elapsed':o.clock.utc+=3;o.clock.mono+=3
        return 1
    o.a.db.create_function('injected_intent_insert',0,observe)
    mutation="UPDATE state SET value='{}' WHERE key='paper_account_alias:fixture';" if fault=='alias' else "UPDATE paper_presence_records SET reason='INVENTED_TRIGGER_REVOKE';" if fault=='presence' else ''
    with o.a.db:o.a.db.execute('CREATE TRIGGER late_intent_mutation AFTER INSERT ON '+table+' BEGIN SELECT injected_intent_insert(); '+mutation+' END')
    with pytest.raises(RuntimeRefused):
        if phase=='prepare':prepare(cancellation)
        else:confirm_intent(o,r)
    assert fired==[True] and not o.a.db.in_transaction
    assert o.a.db.execute('SELECT count(*) FROM '+table).fetchone()==(prior,)
    # The failed insert's alias mutation rolls back, while revocation may persist
    # independently only after that rollback has completed.
    assert o.a.db.execute("SELECT value FROM state WHERE key='paper_account_alias:fixture'").fetchone()[0]!='{}'
    if fault=='presence':
        reason=o.a.db.execute('SELECT reason FROM paper_presence_records').fetchone()[0]
        assert reason is not None and reason!='INVENTED_TRIGGER_REVOKE'


@pytest.mark.parametrize('fault',['version','confirmations_table'])
def test_partial_schema_refuses_and_cannot_revive_after_restoration(cancellation,fault):
    o=cancellation[0][0];_,r=prepare(cancellation)
    sql=o.a.db.execute("SELECT sql FROM sqlite_master WHERE name='paper_native_confirmations'").fetchone()[0]
    with o.a.db:
        if fault=='version':o.a.db.execute("DELETE FROM state WHERE key='paper_native_intent_version'")
        else:o.a.db.execute('DROP TABLE paper_native_confirmations')
    with pytest.raises(RuntimeRefused):inspect(o,r)
    with o.a.db:
        if fault=='version':o.a.db.execute("INSERT INTO state VALUES('paper_native_intent_version','1')")
        else:o.a.db.execute(sql)
    try:v=inspect(o,r)
    except RuntimeRefused:return
    assert v['intent_status']=='INVALIDATED'


def test_component_is_private_and_history_is_bounded(cancellation):
    import pickle
    from uuid import uuid4
    from test_paper_read_preparation import ACCOUNT,KEY,SECRET
    o=cancellation[0][0];_,r=prepare(cancellation)
    with pytest.raises(RuntimeRefused):pickle.dumps(o.a._intents)
    assert all(s not in repr(o.a._intents) for s in (ACCOUNT,KEY,SECRET))
    columns=[c[1] for c in o.a.db.execute('PRAGMA table_info(paper_native_intents)')]
    original=list(o.a.db.execute('SELECT * FROM paper_native_intents').fetchone());rows=[]
    # Invented count-bound rows are never used as qualified intent evidence.
    for _ in range(127):
        row=list(original);ident=str(uuid4());row[columns.index('intent_id')]=ident
        body=dict(json.loads(row[columns.index('body')]),intent_id=ident)
        raw=canonical(body);row[columns.index('body')]=raw.decode()
        row[columns.index('sha256')]=hashlib.sha256(raw).hexdigest();rows.append(row)
    with o.a.db:o.a.db.executemany('INSERT INTO paper_native_intents VALUES('+','.join('?' for _ in original)+')',rows)
    with pytest.raises(RuntimeRefused,match='PAPER_INTENT_HISTORY_BOUND'):prepare(cancellation)
    assert o.a.db.execute('SELECT count(*) FROM paper_native_intents').fetchone()==(128,)


@pytest.mark.parametrize('table',['paper_native_intents','paper_native_confirmations','paper_native_invalidations'])
def test_replaced_schema_cannot_duplicate_evidence_or_revive(cancellation,table):
    o=cancellation[0][0];_,r=prepare(cancellation);confirm_intent(o,r)
    db=o.a.db;sql=db.execute('SELECT sql FROM sqlite_master WHERE name=?',(table,)).fetchone()[0]
    rows=db.execute('SELECT * FROM '+table).fetchall()
    columns=[c[1] for c in db.execute('PRAGMA table_info('+table+')')]
    insert='INSERT INTO '+table+' VALUES('+','.join('?' for _ in columns)+')'
    with db:
        db.execute('DROP TABLE '+table)
        db.execute('CREATE TABLE '+table+'('+','.join(c+' TEXT' for c in columns)+')')
        db.executemany(insert,rows+rows)
    try:
        with pytest.raises(RuntimeRefused,match='PAPER_INTENT_STATE_CORRUPT'):inspect(o,r)
    finally:
        (o.a.store.root/('replaced-schema-'+table+'.json')).write_text(json.dumps(dict(sql=sql,rows=rows)))
        with db:
            db.execute('DROP TABLE '+table);db.execute(sql);db.executemany(insert,rows)
    try:v=inspect(o,r)
    except RuntimeRefused:return
    assert v['intent_status']=='INVALIDATED'


def test_confirmation_sql_identity_must_match_original_body(cancellation):
    from uuid import uuid4
    o=cancellation[0][0];_,r=prepare(cancellation);_,c=confirm_intent(o,r)
    with o.a.db:o.a.db.execute('UPDATE paper_native_confirmations SET confirmation_id=?',(str(uuid4()),))
    try:
        with pytest.raises(RuntimeRefused,match='PAPER_INTENT_STATE_CORRUPT'):inspect(o,r)
    finally:
        with o.a.db:o.a.db.execute('UPDATE paper_native_confirmations SET confirmation_id=?',(c['confirmation_id'],))
    try:v=inspect(o,r)
    except RuntimeRefused:return
    assert v['intent_status']=='INVALIDATED'


@pytest.mark.parametrize('fault',['symbol','order_id','request_id'])
def test_rejected_caller_input_does_not_poison_original_intent(cancellation,fault):
    import copy
    from uuid import uuid4
    o=cancellation[0][0];p,r=prepare(cancellation);confirm_intent(o,r)
    bad=copy.deepcopy(p);bad['request_id']=str(uuid4())
    if fault=='request_id':bad['request_id']='invalid'
    else:bad['command']['terms'][fault]='aapl' if fault=='symbol' else 'invalid'
    with pytest.raises(RuntimeRefused):o.a.intent_handle(bad)
    assert inspect(o,r)['intent_status']=='CURRENT_CONFIRMED'
    _,next_record=prepare(cancellation)
    assert inspect(o,next_record)['intent_status']=='CURRENT_UNCONFIRMED'
