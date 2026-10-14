"""Private account identity attestation; never an arm, order grant or ledger proof."""
from dataclasses import dataclass
from datetime import timedelta
import hashlib,json,re,sqlite3
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import strict_json,number,timestamp
from compertum.fake_attempt_guard import verify_attempt_guard,require_attempt_guard,ZERO
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_preflight import _PaperPreflight,_measure
from .paper_read_evidence import open_read_evidence
from .paper_read_secrecy import _reject_reflections
from .paper_credential_slot import load_paper_slot
from .paper_credentials import open_paper_credentials

_FACTORY=object()
_TABLES=('fake_intents','fake_intent_events','fake_broker_events','fake_event_applications','fake_incidents','fake_execution_session')
_PREFIX='paper_account_proposal:'
_ALIAS='paper_account_alias:'


def _need(value,code='PAPER_ACCOUNT_BINDING_CHANGED'):
 if not value:raise RuntimeRefused(code)


def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def _state(owner,key):
 row=owner.db.execute('SELECT CASE WHEN length(CAST(value AS BLOB))<=16384 THEN value END FROM state WHERE key=?',(key,)).fetchone()
 if row is None:return None
 _need(type(row[0]) is str,'PAPER_ACCOUNT_STATE_INVALID')
 try:
  value=strict_json(row[0].encode());_need(canonical(value).decode()==row[0],'PAPER_ACCOUNT_STATE_INVALID');return value
 except (ValueError,TypeError):raise RuntimeRefused('PAPER_ACCOUNT_STATE_INVALID') from None


def _put(owner,key,value,*,new=False):
 raw=canonical(value).decode();_need(len(raw.encode())<=16384)
 if new:c=owner.db.execute('INSERT INTO state VALUES(?,?)',(key,raw))
 else:c=owner.db.execute('UPDATE state SET value=? WHERE key=?',(raw,key))
 _need(c.rowcount==1 and _state(owner,key)==value,'PAPER_ACCOUNT_WRITE_UNVERIFIED')


def _history(owner):
 """Never initialize or repair evidence while interpreting an account read."""
 try:
  with owner.store._live() as guard:
   status=_state(owner,'execution_status');conflict=_state(owner,'fake_attempt_conflict')
   _need((status is None or status=='VERIFIED') and (conflict is None or conflict is False))
   present={r[0] for r in owner.db.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] in _TABLES}
   if not present:
    evidence=verify_attempt_guard(guard.project)
    _need(evidence['status']=='VERIFIED' and evidence['sequence']==0 and evidence['sha256']==ZERO)
    mirror=_state(owner,'fake_attempt_guard_head')
    _need(type(mirror) is dict and set(mirror)=={'sequence','sha256'} and type(mirror['sequence']) is int and mirror['sequence']==0 and mirror['sha256']==ZERO)
    return dict(status='VERIFIED_ZERO_PRE_SCHEMA',sequence=0,sha256=ZERO,empty=True)
   _need(present==set(_TABLES))
   counts={t:owner.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in _TABLES}
   _need(counts['fake_intents']<=256 and all(v<=512 for v in counts.values()))
   size=owner.db.execute('SELECT coalesce(max(length(CAST(body AS BLOB))+length(CAST(decision AS BLOB))),0) FROM fake_intents').fetchone()[0]
   _need(size<=65536)
   evidence=require_attempt_guard(owner.store)
   empty=evidence['sequence']==0 and all(counts[t]==0 for t in _TABLES if t!='fake_execution_session')
   return dict(status='VERIFIED_HISTORY',sequence=evidence['sequence'],sha256=evidence['sha256'],empty=empty)
 except (RuntimeRefused,sqlite3.Error):return dict(status='UNVERIFIED',sequence=None,sha256=None,empty=False)


def _time(value):
 parsed=timestamp(value)
 _need(parsed.isoformat()==value,'PAPER_ACCOUNT_STATE_INVALID')
 return parsed


def _stored(owner,packet_id):
 record=_state(owner,_PREFIX+packet_id)
 if record is None:return None
 try:
  _need(type(record) is dict and set(record)=={'proposal','proposal_sha256','confirmed_at'})
  p=record['proposal']
  fields={'version','purpose','project_id','account_alias','packet_id','subject_key','owner_instance','generation','credential_sha256','identity_sha256','preflight_sha256','manifest_sha256','encrypted_evidence_sha256','created_at','expires_at','history_sha256','opening_observation_sha256'}
  _need(type(p) is dict and set(p)==fields)
  _need(type(p['version']) is int and p['version']==1 and p['purpose']=='PAPER_ACCOUNT_IDENTITY_ATTESTATION')
  _need(type(p['generation']) is int and p['generation']>0)
  read=owner._read(packet_id)
  _need(read['state']=='PUBLISHED' and read['evidence'] is not None)
  _need(all(p[k]==read[k] for k in ('project_id','account_alias','packet_id','subject_key','owner_instance','credential_sha256')))
  _need(p['generation']==read['owner_generation'] and p['encrypted_evidence_sha256']==read['evidence']['sha256'])
  for key in fields:
   if key.endswith('_sha256'):_need(type(p[key]) is str and re.fullmatch('[0-9a-f]{64}',p[key]) is not None)
  _need(type(record['proposal_sha256']) is str and record['proposal_sha256']==_sha(p))
  created,expires=_time(p['created_at']),_time(p['expires_at'])
  _need(timestamp(read['plan']['created_at'])<=created<=expires<=created+timedelta(seconds=30))
  _need(created<=timestamp(read['plan']['start_expires_at'])+timedelta(seconds=30))
  if record['confirmed_at'] is not None:_need(created<=_time(record['confirmed_at'])<=expires)
 except (RuntimeRefused,ContractError,ValueError,TypeError,KeyError,OverflowError):raise RuntimeRefused('PAPER_ACCOUNT_STATE_INVALID') from None
 return record


def _alias(owner,alias,identity):
 record=_state(owner,_ALIAS+alias)
 if record is not None:
  try:
   _need(type(record) is dict and set(record)=={'version','project_id','account_alias','identity_sha256','first_packet_id','confirmed_at'})
   _need(type(record['version']) is int and record['version']==1 and record['project_id']==owner.lease.project_id and record['account_alias']==alias)
   _need(type(record['identity_sha256']) is str and re.fullmatch('[0-9a-f]{64}',record['identity_sha256']) is not None)
   _need(type(record['first_packet_id']) is str)
   first=_stored(owner,record['first_packet_id']);_need(first is not None)
   _need(first['proposal']['account_alias']==alias and first['proposal']['identity_sha256']==record['identity_sha256'])
   _need(record['confirmed_at'] is not None and first['confirmed_at']==record['confirmed_at']);_time(record['confirmed_at'])
  except (RuntimeRefused,ContractError,ValueError,TypeError,KeyError):raise RuntimeRefused('PAPER_ACCOUNT_STATE_INVALID') from None
  _need(record['identity_sha256']==identity,'PAPER_ACCOUNT_ALIAS_CONFLICT')
 return record


def _facts(owner,context,value,manifest):
 _need(type(context) is _PaperPreflight and context is owner._preflight)
 p=context.diagnostic()
 _need(value['state']=='PUBLISHED' and value['packet_id']==p['packet_id'],'PAPER_ACCOUNT_PUBLISHED_EVIDENCE_REQUIRED')
 _need(type(manifest) is dict and manifest.get('sha256')==p['encrypted_evidence_sha256'] and manifest.get('size_bytes')==value['evidence']['size_bytes'])
 with open_read_evidence(owner.lease,p['account_alias'],p['packet_id'],manifest):pass
 # Artifact verification can consume observation lifetime; check again afterward.
 p=context.diagnostic()
 records=[json.loads(b) for a,b in context._records]
 account=next(r['observation'] for r in records if r['operation']=='ACCOUNT')
 history=_history(owner)
 reasons=[]
 if account['status']!='ACTIVE' or any(account[k] for k in ('trading_blocked','account_blocked','trade_suspended_by_user')):reasons.append('ACCOUNT_BLOCKED')
 if number(account['cash'])<0:reasons.append('NEGATIVE_ACCOUNT_CASH')
 if p['positions']:reasons.append('UNEXPLAINED_POSITIONS')
 if p['orders']:reasons.append('UNEXPLAINED_ORDER_HISTORY')
 if p['order_coverage']!='OBSERVED_SHORT_TERMINAL_PAGE':reasons.append('ORDER_COVERAGE_UNVERIFIED')
 if history['status']=='UNVERIFIED':reasons.append('LOCAL_HISTORY_UNVERIFIED')
 elif not history['empty']:reasons.append('NONEMPTY_LOCAL_HISTORY_REQUIRES_RECONCILIATION')
 identity=_sha(dict(purpose='COMPERTUM_PAPER_ALIAS_IDENTITY_V1',project_id=owner.lease.project_id,account_alias=p['account_alias'],private_account_id=context._account_id))
 _alias(owner,p['account_alias'],identity)
 first=min(timestamp(json.loads(a)['created_at']) for a,b in context._records)
 body=dict(version=1,purpose='PAPER_ACCOUNT_IDENTITY_ATTESTATION',project_id=owner.lease.project_id,account_alias=p['account_alias'],packet_id=p['packet_id'],
  subject_key=value['subject_key'],owner_instance=owner.lease.identity.process_instance_id,generation=owner.lease.generation,
  credential_sha256=p['credential_sha256'],identity_sha256=identity,preflight_sha256=context._content_sha,manifest_sha256=_sha(manifest),
  encrypted_evidence_sha256=p['encrypted_evidence_sha256'],created_at=p['created_at'],expires_at=(first+timedelta(seconds=30)).isoformat(),
  history_sha256=_sha(history),opening_observation_sha256=_sha(dict(private_account_id=context._account_id,account=account,references=p['references'])))
 context.diagnostic()
 return body,p,history,sorted(set(reasons))


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _AccountProposal:
 content:bytes
 _context:object
 _confirmed_at:object
 _closed:bool
 def __init__(self,*,_factory=None,**fields):
  _need(_factory is _FACTORY,'PAPER_ACCOUNT_PROPOSAL_UNQUALIFIED')
  for key,value in fields.items():object.__setattr__(self,key,value)
 def __repr__(self):return '<PrivateAccountProposal redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_ACCOUNT_PRIVATE_SERIALIZATION_FORBIDDEN')
 def close(self):
  with _MUTEX:object.__setattr__(self,'_closed',True);object.__setattr__(self,'_context',None)


def _public(owner,record,*,identity='UNCONFIRMED',live='NOT_ASSERTED',opening='UNVERIFIED',reasons=(),history=None):
 p=record['proposal'];digest=record['proposal_sha256']
 result=dict(version=1,record_type='PaperAccountBindingReceipt',scope='ACCOUNT_IDENTITY_ONLY',account_alias=p['account_alias'],packet_id=p['packet_id'],
  proposal_sha256=digest,created_at=p['created_at'],expires_at=p['expires_at'],required_acknowledgement='CONFIRM PAPER ACCOUNT '+p['account_alias']+' '+digest,
  confirmation_recorded=record['confirmed_at'] is not None,confirmation_recorded_at=record['confirmed_at'],identity_status=identity,live_context=live,
  opening_status=opening,local_history=history,deficiencies=list(reasons),trading_status='BLOCKED',transport_authorized=False,financial_accepted=False,actual_flat=None)
 raw=canonical(result);_need(len(raw)<=8192)
 protected=load_paper_slot(owner.lease,p['account_alias'])
 with open_paper_credentials(owner.lease,protected) as opened:_reject_reflections(raw,tuple(opened.headers().values()))
 return result


def _live(owner,value,manifest):
 proposal=owner._account_proposal
 _need(type(proposal) is _AccountProposal and not proposal._closed,'PAPER_ACCOUNT_PROPOSAL_UNAVAILABLE')
 body,p,history,reasons=_facts(owner,proposal._context,value,manifest)
 _need(canonical(body)==proposal.content)
 record=_stored(owner,value['packet_id']);_need(record is not None and record['proposal']==body and record['confirmed_at']==proposal._confirmed_at)
 return proposal,record,p,history,reasons


def handle_binding(owner,subject,value,command):
 """Invoked only under the existing authenticated execution-owner scope."""
 with _owner_scope(owner.lease),owner.store._live():
  _need(value['subject_key']==subject,'READ_OPERATOR_CHANGED')
  op=command['operation'];packet=value['packet_id'];manifest=command['manifest']
  if op=='account_propose':
   context=owner.preflight(packet);body,p,history,reasons=_facts(owner,context,value,manifest)
   record=_stored(owner,packet)
   if record is None:
    _need(owner.db.execute("SELECT count(*) FROM state WHERE key LIKE 'paper_account_proposal:%'").fetchone()[0]<32,'PAPER_ACCOUNT_HISTORY_BOUND')
    record=dict(proposal=body,proposal_sha256=_sha(body),confirmed_at=None)
    with owner.db:_put(owner,_PREFIX+packet,record,new=True)
   else:_need(record['proposal']==body)
   proposal=owner._account_proposal
   if proposal is None:
    _need(record['confirmed_at'] is None,'PAPER_ACCOUNT_PROPOSAL_UNAVAILABLE')
    owner._account_proposal=_AccountProposal(_factory=_FACTORY,content=canonical(body),_context=context,_confirmed_at=None,_closed=False)
   else:_need(not proposal._closed and proposal._context is context and proposal.content==canonical(body))
   return _public(owner,record,reasons=reasons,history=history)
  record=_stored(owner,packet);_need(record is not None,'PAPER_ACCOUNT_PROPOSAL_UNKNOWN')
  mapping=_alias(owner,record['proposal']['account_alias'],record['proposal']['identity_sha256'])
  _need(record['confirmed_at'] is None or mapping is not None,'PAPER_ACCOUNT_STATE_INVALID')
  if op=='account_status':
   try:
    proposal,record,p,history,reasons=_live(owner,value,manifest)
    confirmed=record['confirmed_at'] is not None and p['transport_provenance']=='PAPER_TLS'
    opening=('EMPTY_PORTFOLIO_OBSERVED' if not reasons else 'BLOCKED') if confirmed else 'UNVERIFIED'
    result=_public(owner,record,identity='CONFIRMED_CURRENT_CONTEXT' if confirmed else 'UNCONFIRMED',live='FRESH',opening=opening,reasons=reasons,history=history)
    proposal._context.diagnostic()
    return result
   except RuntimeRefused as error:
    return _public(owner,record,identity='HISTORICAL_ONLY' if record['confirmed_at'] else 'UNCONFIRMED',live='UNAVAILABLE',reasons=[error.code])
  _need(op=='account_confirm','CONTROL_PAYLOAD_DENIED')
  proposal,record,p,history,reasons=_live(owner,value,manifest)
  expected=_public(owner,record)
  _need(command['proposal_sha256']==record['proposal_sha256'] and command['acknowledgement']==expected['required_acknowledgement'],'PAPER_ACCOUNT_CONFIRMATION_MISMATCH')
  _need(p['transport_provenance']=='PAPER_TLS','PAPER_ACCOUNT_NATIVE_ORIGIN_REQUIRED')
  if record['confirmed_at'] is None:
   alias=p['account_alias'];identity=record['proposal']['identity_sha256'];now,_=_measure()
   try:
    with owner.db:
     # All checks remain under the same owner mutex and transaction.
     proposal._context.diagnostic();mapping=_alias(owner,alias,identity)
     if mapping is None:
      _need(owner.db.execute("SELECT count(*) FROM state WHERE key LIKE 'paper_account_alias:%'").fetchone()[0]<32,'PAPER_ACCOUNT_HISTORY_BOUND')
      _put(owner,_ALIAS+alias,dict(version=1,project_id=owner.lease.project_id,account_alias=alias,identity_sha256=identity,first_packet_id=packet,confirmed_at=now.isoformat()),new=True)
     record=dict(record,confirmed_at=now.isoformat());_put(owner,_PREFIX+packet,record)
     from .paper_opening import record_confirmation_opening
     record_confirmation_opening(owner,record,manifest,history,reasons,new_alias=mapping is None)
     proposal._context.diagnostic()
   except sqlite3.Error:raise RuntimeRefused('PAPER_ACCOUNT_WRITE_UNVERIFIED') from None
   object.__setattr__(proposal,'_confirmed_at',record['confirmed_at'])
  else:
   from .paper_opening import validate_confirmation_opening
   validate_confirmation_opening(owner,p['account_alias'])
   proposal._context.diagnostic()
  # A cached confirmation response records history, not current freshness.
  return _public(owner,record,identity='ATTESTATION_RECORDED')
