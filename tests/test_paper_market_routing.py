"""Market public routing and uncached reads; native coordinator state, simulated handler."""
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4
import pytest
from compertum.runtime.supervisor import Supervisor,ACTIONS
from compertum.runtime.bootstrap import validate_worker_commands
from compertum.domain import capability_for
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair
from test_paper_read_owner import owner


def test_market_routes_are_read_only_and_transfer_is_never_public():
 assert 'paper_market_read' in ACTIONS and 'paper_market_transfer' not in ACTIONS
 for action in ('paper_market_read','paper_market_transfer'):assert capability_for(action).exit_code==0
 for action in ('paper.arm','paper.start','paper.cancel','paper.close'):assert capability_for(action).exit_code!=0
 for role in ('execution','watchdog','evaluation'):
  for action in ('paper_market_read','paper_market_transfer'):
   with pytest.raises(RuntimeRefused,match='WORKER_COMMAND_DENIED'):validate_worker_commands(role,frozenset({action}))
 s=object.__new__(Supervisor);s.partial_fixture=True
 with pytest.raises(RuntimeRefused,match='EXECUTION_UNAVAILABLE'):s._dispatch(SimpleNamespace(subject_key='a'*64),'paper_market_read',dict(operation='status'))


@dataclass(frozen=True)
class Decision:
 request_id:str
 subject_key:str


@pytest.mark.parametrize('operation',['status','compose'])
def test_repeated_public_request_id_always_rechecks_current_market_view(owner,operation):
 o=owner;s=object.__new__(Supervisor);s.store=o.manager.store;s.partial_fixture=False;calls=[]
 with s.store.conn:s.store.conn.execute('CREATE TABLE operator_requests(request_id TEXT PRIMARY KEY,binding TEXT NOT NULL,result TEXT,error TEXT)')
 def handle(subject,payload):
  calls.append((subject,payload));return dict(observed_at=len(calls),quote_valid=len(calls)==1)
 s.paper_market_reads=SimpleNamespace(handle=handle)
 decision=Decision(str(uuid4()),'a'*64);payload=dict(operation=operation,job_id=str(uuid4()))
 first=s.handle(decision,'paper_market_read',payload);second=s.handle(decision,'paper_market_read',payload)
 assert first['quote_valid'] and not second['quote_valid'] and first['observed_at']!=second['observed_at']
 assert calls==[('a'*64,payload)]*2 and s.store.conn.execute('SELECT count(*) FROM operator_requests').fetchone()==(0,)


def test_market_route_passes_only_authenticated_subject(owner):
 o=owner;s=object.__new__(Supervisor);s.partial_fixture=False;calls=[]
 s.paper_market_reads=SimpleNamespace(handle=lambda subject,payload:calls.append((subject,payload)))
 payload=dict(operation='status',job_id=str(uuid4()))
 s._dispatch(Decision(str(uuid4()),'c'*64),'paper_market_read',payload)
 assert calls==[('c'*64,payload)]
