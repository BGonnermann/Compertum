"""Owned proof lifecycle with explicitly simulated original source readers."""
from datetime import datetime,timezone
from types import SimpleNamespace
import hashlib,json
import pytest
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from test_fixture_order_private_factory import prepared as dispatch_inputs,owner,original_owner,risk_inputs,account,confirmed,inputs,history,completed,pair,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,simulated_source
from test_fixture_order_origin import origin

@pytest.fixture
def observed(dispatch_inputs,monkeypatch):
 from compertum.runtime import paper_fixture_reconciliation as module
 o,intent,component,p=dispatch_inputs;p.close()
 begin=origin();begin.update(project_id=o.a.lease.project_id,created_at='2023-11-24T14:30:00Z')
 raw=canonical(begin)+b'\n';digest=hashlib.sha256(raw).hexdigest()
 monkeypatch.setattr(module,'_reserved_source_file',lambda *args:(raw,[1,'a'*32]))
 monkeypatch.setattr(module,'_account_original',lambda *args:(None,dict(order_source=dict(journal_sha256=digest)),None,None,None))
 monkeypatch.setattr(module,'source_file',lambda *args:({'genesis_sha256':begin['economic_genesis_sha256'],'ledger':{'events':[]}},[1,'b'*32]))
 root=o.a._intents._read(intent['intent_id'])
 return o,intent,component,root,module

def reconcile(fixture,**changes):
 o,intent,component,root,module=fixture
 activity=o.a.db.execute("SELECT value FROM state WHERE substr(key,1,15)='paper_activity:'").fetchall()
 activity_id=next(json.loads(row[0])['activity_id'] for row in activity)
 args=dict(subject='a'*64,packet_id=root['packet_id'],activity_id=activity_id,presence_id=root['presence_id']);args.update(changes)
 return module.reconcile_fixture_orders(o.a,**args)

def test_empty_original_inventory_needs_owned_proofs_and_grants_no_send(observed):
 o,intent,component,root,module=observed;result=reconcile(observed)
 assert result['scope']=='CONTROLLED_LOCAL_RECONCILIATION' and result['fixture_flat'] is True
 assert result['transport_authorized'] is result['financial_accepted'] is False and result['actual_flat'] is None
 assert verify_attempt_guard(resolve_project(o.a.store.root))['sequence']==0

@pytest.mark.parametrize('fault',['presence','descriptor','owner'])
def test_unqualified_current_proof_or_source_refuses(observed,monkeypatch,fault):
 o,intent,component,root,module=observed
 if fault=='presence':o.a._presence.close()
 elif fault=='descriptor':monkeypatch.setattr(module,'_account_original',lambda *args:(None,dict(order_source=dict(journal_sha256='f'*64)),None,None,None))
 else:component.closed=True
 with pytest.raises(RuntimeRefused):reconcile(observed)
 assert verify_attempt_guard(resolve_project(o.a.store.root))['sequence']==0
