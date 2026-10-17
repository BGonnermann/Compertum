"""Private current local risk. Actual broker and financial gates remain closed."""
from dataclasses import dataclass
import json,re,sqlite3
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.fixture_risk import FixtureRiskCalculation,calculate_fixture_risk,_arguments
from compertum.paper_contracts import PAPER_ORIGIN,build_request
from compertum.paper_fixture_plans import build_fixture_inputs
from compertum.paper_portfolio import build_portfolio_bundle
from compertum.paper_responses import parse_response
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_final_proof import _FinalProof,_final_proof,_verify_proofs
from .paper_native_intents import _NativeIntents
from .paper_reconciliation_context import _capture_originals,_sha
from .paper_fixture_economics import fixture_economic_context
from . import paper_fixture_economics as economic_module
from .paper_input_context import _account_manifest
from .paper_read_evidence import open_read_evidence

_FACTORY=object()
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,sqlite3.Error,OSError)
def _need(value,code='PAPER_FIXTURE_RISK_UNVERIFIED'):
 if not value:raise RuntimeRefused(code)

def _join(first,second,value,original,last,final_identity):
 """Join related checks without adding a third final proof."""
 _need(type(first) is type(second) is _FinalProof and first is not second and not first._used and not second._used)
 owner=first._owner;_need(second._owner is owner and first._db is second._db is owner.db)
 _need(first._health is second._health is owner.health and first._peer==second._peer)
 tails=[]
 for proof in (first,second):
  tails.append((proof._check,proof._finish,proof._invalidate,proof._final_identity))
  proof._used=True;proof._check=proof._finish=proof._invalidate=proof._final_identity=None
  proof._owner=proof._db=proof._lease=proof._health=proof._peer=None;proof._content=b''
 def run(index):
  for tail in tails:
   try:tail[index]()
   except RuntimeRefused as error:tail[2](error.code);raise
 def check():run(0);original()
 def finish():run(1);last()
 def identity():
  for tail in tails:
   if tail[3] is not None:tail[3]()
  final_identity()
 result=_final_proof(owner,check,finish,lambda reason:None,value);result._final_identity=identity
 return result

def _portfolio(owner,p):
 manifest=_account_manifest(owner,owner._read(p['packet_id']))
 with open_read_evidence(owner.lease,p['account_alias'],p['packet_id'],manifest) as opened:rows=opened.snapshot()['records']
 grouped={name:[] for name in ('ACCOUNT','POSITIONS','ORDERS','CLOCK','CALENDAR')}
 for row in rows:
  source=row['request'];request=build_request(origin=PAPER_ORIGIN,account_alias=p['account_alias'],account_id=owner._preflight._account_id,
   request_id=source['request_id'],created_at=source['created_at'],operation=source['operation'],parameters=source['parameters'])
  # Reuse original reply bytes in an explicitly unqualified arithmetic adapter.
  response=parse_response(request,origin=PAPER_ORIGIN,account_id=owner._preflight._account_id,status=200,raw=row['raw'],received_at=row['parsed']['received_at'])
  grouped[source['operation']].append(response)
 _need(len(grouped['ACCOUNT'])==len(grouped['POSITIONS'])==len(grouped['CALENDAR'])==1 and grouped['ORDERS'] and grouped['CLOCK'])
 return build_portfolio_bundle(account=grouped['ACCOUNT'][0],positions=grouped['POSITIONS'][0],orders=tuple(grouped['ORDERS']),
  clock=grouped['CLOCK'][-1],calendar=grouped['CALENDAR'][0],as_of=p['created_at'])

def _capture(owner,subject,intent_id,economic):
 component=owner._intents;_need(type(component) is _NativeIntents and component.parent is owner and component.db is owner.db)
 resources=(owner.store,owner.reserve,owner.health,owner.lease,owner.db)
 instance=component.instance
 p=component._read(intent_id);_need(p['subject_key']==subject,'READ_OPERATOR_CHANGED')
 _need(p['purpose'] in {'FIXTURE_BUY','FIXTURE_RESTING_BUY','CANCEL','CLOSE_LONG'},'PAPER_FIXTURE_STRATEGY_DENIED')
 c=component._confirmation(p);_need(c is not None,'PAPER_FIXTURE_CONFIRMATION_REQUIRED');component._records_current(p,c)
 issued=component._issued.get(intent_id);_need(issued is not None and issued[0]==_sha(p))
 issued_context,issued_presence=issued[1:3];context_binding=issued_context._binding
 input_identities=issued_context._identities;presence_instance=issued_presence.instance
 _need(economic._owner is owner and economic._context is owner._account_context and economic._context._packet==p['packet_id'])
 input_proof,presence=component._proofs(p);economic_proof=economic._prepare_proof()
 _,base,originals,metadata,original,_,_= _capture_originals(owner,economic._context,economic._portfolio,economic._activity_id,allow_unsupported=True)
 source,source_binding,source_check=economic_module._source_snapshot(owner,economic._context,base,originals)
 calculation=json.loads(economic._calculation)
 _need(economic._binding==_sha(dict(base,source=source_binding,calculation_sha256=_sha(calculation))))
 _need(metadata['provenance']=='LOOPBACK_FIXTURE' and calculation['cash_matches'])
 current_presence=json.loads(presence._content);portfolio=_portfolio(owner,p);inputs=None
 if p['purpose']!='CANCEL':
  market=owner._market._combined.to_payload()['diagnostic'];ledger=source['ledger']
  _need(market['asset']['valid'] and market['quote']['valid'])
  if p['purpose'].startswith('FIXTURE_'):_need(market['observed_conditions_met'])
  _need(market['symbol']==ledger['symbol']==p['terms']['symbol'] and market['asset']['asset_id']==ledger['asset_id'])
  _need(ledger['action_events']==[])
  history=market['history'];quote=market['quote'];asset=market['asset']
  inputs=build_fixture_inputs(quotes=[dict(symbol=market['symbol'],bid=quote['bid'],ask=quote['ask'],observed_at=quote['observed_at'],feed=market['feed'])],
   securities=[dict(symbol=market['symbol'],feature_sessions=history['observed_sessions'],raw_close=history['prior_raw_close'],liquidity_sessions=20,
    mean_dollar_volume=history['mean_dollar_volume'],feature_session=history['prior_session'],tradable=asset['tradable'],
    actions_verified=ledger['action_events']==[],mapping_verified=asset['asset_id']==ledger['asset_id'])],
   feed=market['feed'],feature_session=history['prior_session'],created_at=p['created_at'],supervision_at=current_presence['acknowledged_at'])
 values=dict(portfolio=portfolio,inputs=inputs,purpose=p['purpose'],terms=p['terms'],intent_id=p['intent_id'],now=p['created_at'],outstanding_fees=calculation['outstanding_fees'])
 expected=canonical(_arguments(**values));risk=calculate_fixture_risk(**values);_need(type(risk) is FixtureRiskCalculation)
 risk.__post_init__();private=risk.content;result=risk.to_payload()
 _need(risk.arguments==expected==canonical(_arguments(**values)) and risk.content==private)
 evidence=dict(intent=_sha(p),confirmation=_sha(c),presence=_sha(current_presence),opening=base['opening']['sha256'],ownership=_sha(originals),
  economics=_sha(calculation),risk=_sha(result),inputs=p['context_sha256'])
 pin=_sha(dict(evidence=evidence,economic=economic._binding,component=component.instance,activity=economic._activity_id))
 diagnostic=dict(version=1,record_type='FixtureRiskContextDiagnostic',scope='ENGINEERING_FIXTURE_RISK',risk_status='CURRENT_LOCAL_RISK_CHECKED',
  source_qualified=True,purpose=p['purpose'],intent_id=p['intent_id'],expires_at=p['expires_at'],planned_notional=result['planned_notional'],
  projected_exposure=result['projected_exposure'],financial_accepted=False,transport_authorized=False,actual_flat=None,
  unverified_requirements=['DURABLE_DISPATCH_UNVERIFIED','ACTUAL_FINANCIAL_INPUTS_UNVERIFIED'])
 _need(owner._preflight._account_id.encode() not in canonical(diagnostic))
 expected_diagnostic=canonical(diagnostic);expected_presence=presence._content
 expected_intent=canonical(p);expected_confirmation=canonical(c)
 def final_identity():
  _need(not owner._closed and owner._intents is component and component.parent is owner and not component._closed)
  _need(component.instance==instance and component.db is owner.db and component._reason is None)
  _need(all(a is b for a,b in zip(resources,(owner.store,owner.reserve,owner.health,owner.lease,owner.db))))
  _need(component._issued.get(intent_id) is issued and issued[0]==_sha(p))
  current=owner._account_context if p['purpose']=='CANCEL' else owner._input_context
  _need(current is issued_context and not issued_context._closed and issued_context._binding==context_binding==p['context_sha256'])
  _need(issued_context._owner is owner and issued_context._generation==owner.lease.generation
   and issued_context._instance==owner.lease.identity.process_instance_id)
  _need(len(issued_context._identities)==len(input_identities) and all(a is b for a,b in zip(issued_context._identities,input_identities)))
  if p['purpose']=='CANCEL':
   preflight,proposal=input_identities[-2:]
   _need(owner._preflight is preflight and not preflight._closed and owner._account_proposal is proposal)
  else:
   preflight,proposal,market,producer,view,held,combined=input_identities
   _need(owner._preflight is preflight and not preflight._closed and owner._account_proposal is proposal and owner._market is market)
   _need(market.parent is owner and market.lease is owner.lease and market._producer is producer and market._fresh_view is view
    and market._opened is held and market._combined is combined)
   _need(not producer._closed and not combined._closed and not held._closed and producer in producer._owner_state.resources
    and combined in combined._state.resources and held in held._state.resources)
   _need(view._pair is producer and producer._view is view and combined._fresh is view and combined._history is held)
  if proposal is not None:_need(not proposal._closed and proposal._context is preflight)
  _need(owner._presence is issued_presence and not issued_presence._closed and issued_presence.parent is owner)
  _need(issued_presence.instance==presence_instance==current_presence['component_id'] and issued_presence.db is owner.db)
  _need(p['presence_id'] not in issued_presence._revoked)
  _need(issued_presence._reason is None and issued_presence._issued.get(p['presence_id'])==p['presence_sha256'])
  _need(canonical(p)==expected_intent and canonical(c)==expected_confirmation)
  _need(joined._content==expected_diagnostic and presence._content==expected_presence)
 def checked():
  _need(owner._intents is component and not component._closed and not economic._closed)
  component._records_current(p,c);original();source_check()
 def finished():
  _need(owner._intents is component and not component._closed and not economic._closed)
  component._age(p)
 joined=_join(input_proof,economic_proof,diagnostic,checked,finished,final_identity)
 return (joined,presence),pin,private,diagnostic,evidence

@dataclass(frozen=True,slots=True,repr=False,init=False)
class _FixtureRiskContext:
 _owner:object
 _db:object
 _subject:str
 _intent_id:str
 _economic:object
 _binding:str
 _calculation:bytes
 _evidence:bytes
 _closed:bool
 def __init__(self,*,_factory=None,**fields):
  _need(_factory is _FACTORY,'PAPER_FIXTURE_RISK_CONTEXT_UNQUALIFIED')
  for name,value in fields.items():object.__setattr__(self,name,value)
 def __repr__(self):return '<PrivateFixtureRiskContext redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_FIXTURE_RISK_SERIALIZATION_FORBIDDEN')
 def close(self):
  with _MUTEX:object.__setattr__(self,'_closed',True);self._economic.close()
 def _prepare_proofs(self):
  with _MUTEX:
   _need(not self._closed,'PAPER_FIXTURE_RISK_CONTEXT_UNAVAILABLE')
   try:pending=self._db.in_transaction
   except sqlite3.Error:self.close();raise RuntimeRefused('PAPER_FIXTURE_RISK_DATABASE_CLOSED') from None
   _need(not pending,'PAPER_FIXTURE_RISK_TRANSACTION_OPEN')
   try:
    owner=self._owner
    with _owner_scope(owner.lease),owner.store._live():
     _need(owner.db is self._db and not owner._closed)
     proofs,pin,calculation,_,evidence=_capture(owner,self._subject,self._intent_id,self._economic)
     _need(pin==self._binding and calculation==self._calculation and canonical(evidence)==self._evidence)
     joined=proofs[0];check,finish,invalidate,identity=joined._check,joined._finish,joined._invalidate,joined._final_identity
     def same():
      _need(not self._closed and not self._economic._closed and self._owner is owner and owner.db is self._db and not owner._closed)
      _need(self._binding==pin and self._calculation==calculation and self._evidence==canonical(evidence))
     def checked():same();check();same()
     def finished():same();finish();same()
     def final_identity():identity();same()
     def invalidated(reason):invalidate(reason);self.close()
     joined._check=checked;joined._finish=finished;joined._invalidate=invalidated;joined._final_identity=final_identity
     return proofs
   except RuntimeRefused:self.close();raise
   except _INVALID:self.close();raise RuntimeRefused('PAPER_FIXTURE_RISK_CONTEXT_INVALID') from None
 def diagnostic(self):
  proofs=self._prepare_proofs()
  try:return _verify_proofs(*proofs)[0]
  except RuntimeRefused:self.close();raise

def fixture_risk_context(owner,*,subject,intent_id,activity_id):
 with _MUTEX:
  economic=None
  try:
   _need(not owner.db.in_transaction,'PAPER_FIXTURE_RISK_TRANSACTION_OPEN')
   _need(type(subject) is str and re.fullmatch('[0-9a-f]{64}',subject) is not None);uuid(intent_id);uuid(activity_id)
   component=owner._intents;_need(type(component) is _NativeIntents and component.parent is owner)
   p=component._read(intent_id);_need(p['subject_key']==subject,'READ_OPERATOR_CHANGED')
   _need(p['purpose']!='STRATEGY','PAPER_FIXTURE_STRATEGY_DENIED')
   economic=fixture_economic_context(owner,subject=subject,packet_id=p['packet_id'],activity_id=activity_id)
   with _owner_scope(owner.lease),owner.store._live():
    proofs,pin,calculation,_,evidence=_capture(owner,subject,intent_id,economic);_verify_proofs(*proofs)
    return _FixtureRiskContext(_factory=_FACTORY,_owner=owner,_db=owner.db,_subject=subject,_intent_id=intent_id,
     _economic=economic,_binding=pin,_calculation=calculation,_evidence=canonical(evidence),_closed=False)
  except (RuntimeRefused,*_INVALID):
   if economic is not None:economic.close()
   raise RuntimeRefused('PAPER_FIXTURE_RISK_CONTEXT_INVALID') from None
