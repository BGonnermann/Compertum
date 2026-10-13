"""Review counterexamples: warning chronology and strict incident evidence."""
import sys,json,hashlib,sqlite3
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path.cwd()/'tests'))
import pytest
from test_execution_health import pair
from test_execution_authority import authority,packet
from test_saved_plan_controls import ready
from test_operation_late_recovery import expired
from test_operation_progression import broker
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.execution_operation_owner import FakeOperationOwner

@pytest.mark.parametrize('change',['erase','backdate'])
def test_review_warning_cannot_be_erased_or_backdated(ready,monkeypatch,change):
    a,saved,first=expired(ready,monkeypatch,accepted=False)
    p=packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256']);warning=a.handle(p)
    assert warning['reason']=='UNRESOLVED_LIMIT'
    value=dict(warning if change=='erase' else first)
    if change=='erase':
        value['reason']=None;value.pop('operator_action_required');value.pop('incident_started_at')
    else:value.update({k:warning[k] for k in ('reason','operator_action_required','incident_started_at')})
    raw=canonical(value).decode();key=value['request_id'];calls=broker(a).snapshot()['calls']
    with a.store.conn:
        a.store.conn.execute('UPDATE fake_plan_results SET sha256=?,body=? WHERE request_id=?',(hashlib.sha256(raw.encode()).hexdigest(),raw,key))
        a.store.conn.execute('UPDATE fake_operator_requests SET result=? WHERE request_id=?',(raw,key))
    with pytest.raises(RuntimeRefused,match='OPERATION_STATE_CORRUPT'):a.handle(packet('operation_status',plan_id=saved['plan_id']))
    assert broker(a).snapshot()['calls']==calls

def holder():
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE fake_incidents(account TEXT,intent_id TEXT,next_index INTEGER,last_elapsed REAL,started_at TEXT,active INTEGER)');db.execute('CREATE TABLE fake_intent_events(seq INTEGER PRIMARY KEY,account TEXT,intent_id TEXT,kind TEXT,body TEXT)')
    i=dict(account_alias='fake-account',intent_id=str(uuid4()));started='2023-10-17T13:35:10Z'
    db.execute('INSERT INTO fake_incidents VALUES(?,?,6,120,?,1)',(i['account_alias'],i['intent_id'],started));db.commit()
    o=object.__new__(FakeOperationOwner);o.db=db
    return o,i,started

@pytest.mark.parametrize('column,value',[('active',2),('last_elapsed',float('inf')),('last_elapsed','bad'),('started_at','x'*100000)],ids=['active','nonfinite','nonnumeric','oversized'])
def test_review_malformed_incident_refuses_before_warning(column,value):
    o,i,started=holder()
    try:
        o.db.execute(f'UPDATE fake_incidents SET {column}=?',(value,));o.db.commit()
        with pytest.raises(RuntimeRefused,match='OPERATION_STATE_CORRUPT'):o._warning(i,'UNKNOWN')
    finally:o.db.close()

def test_review_malformed_resolved_event_cannot_support_history():
    o,i,started=holder()
    try:
        o.db.execute("UPDATE fake_incidents SET started_at='2023-10-17T13:40:10Z',last_elapsed=0")
        o.db.execute('INSERT INTO fake_intent_events VALUES(1,?,?,?,?)',(i['account_alias'],i['intent_id'],'INCIDENT_RESOLVED',json.dumps(dict(started_at=started,last_elapsed=120))))
        o.db.commit()
        with pytest.raises(RuntimeRefused,match='OPERATION_STATE_CORRUPT'):o._limit_evidence(i,started)
    finally:o.db.close()
