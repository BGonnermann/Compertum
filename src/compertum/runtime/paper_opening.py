"""Execution-owned immutable first opening; never a trading or reconciliation grant."""
import hashlib,json,os
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import number
from compertum.persistence import checked_path,_active_store_path
from .errors import RuntimeRefused
from .owners import _owner_scope,require_live_owner
from .paper_opening_records import build_reference,validate_reference,cash_matches,reference_sha
from . import paper_account_binding as binding
from .paper_read_evidence import open_read_evidence
from .paper_credential_slot import load_paper_slot
from .paper_credentials import open_paper_credentials,_alias as valid_alias
from .paper_read_secrecy import _reject_reflections

_PREFIX='paper_opening:'

def _need(value,code='PAPER_OPENING_INVALID'):
 if not value:raise RuntimeRefused(code)

def _restore_clear(owner):
 """A restored pre-confirmation database must never establish another baseline."""
 root=owner.store.root
 try:
  with _owner_scope(owner.lease) as guard,guard.api.open_directory(checked_path(root,root/'state')):
   with os.scandir(root/'state') as entries:
    for count,entry in enumerate(entries,1):
     _need(count<=512,'PAPER_OPENING_RESTORE_UNVERIFIED')
     name=entry.name.casefold()
     if name in {'active-generation.json','generations','restore-operation.json'} or (name.startswith('restore-') and name.endswith('.jsonl')) or (name.startswith('aborted-pointer-') and name.endswith('.json')):return False
     info=entry.stat(follow_symlinks=False)
     _need(not entry.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400,'PAPER_OPENING_RESTORE_UNVERIFIED')
   expected=checked_path(root,root/'state/execution.sqlite')
   return owner.store.path==expected and _active_store_path(root,owner.lease.project_id,'execution')==expected
 except (OSError,ValueError,TypeError):raise RuntimeRefused('PAPER_OPENING_RESTORE_UNVERIFIED') from None

def _reference_secrecy(owner,record):
 r=record['reference'];protected=load_paper_slot(owner.lease,r['account_alias'])
 _need(hashlib.sha256(protected.ciphertext).hexdigest()==r['credential_sha256'],'PAPER_OPENING_CREDENTIAL_CHANGED')
 with open_paper_credentials(owner.lease,protected) as opened:
  _reject_reflections(canonical(record),tuple(opened.headers().values()))

def _original(owner,alias):
 """Return private original cash only after every immutable reference is checked."""
 valid_alias(alias);record=binding._state(owner,_PREFIX+alias)
 if record is None:raise RuntimeRefused('PAPER_OPENING_UNRECORDED')
 validate_reference(record,owner.lease.project_id,alias);_reference_secrecy(owner,record);r=record['reference'];mapping=binding._alias(owner,alias,r['identity_sha256'])
 _need(mapping is not None and mapping['first_packet_id']==r['first_packet_id'] and mapping['confirmed_at']==r['confirmed_at'])
 first=binding._stored(owner,r['first_packet_id']);_need(first is not None and first['proposal_sha256']==r['proposal_sha256'] and first['confirmed_at']==r['confirmed_at'])
 p=first['proposal'];_need(all(p[k]==r[k] for k in ('identity_sha256','credential_sha256','opening_observation_sha256','history_sha256')))
 _need(p['manifest_sha256']==reference_sha(r['manifest']) and p['encrypted_evidence_sha256']==r['manifest']['sha256'])
 value=owner._read(r['first_packet_id']);_need(value['task_id']==r['manifest']['task_id'])
 with open_read_evidence(owner.lease,alias,r['first_packet_id'],r['manifest']) as opened:
  snapshot=opened.snapshot();meta=snapshot['metadata'];rows=snapshot['records']
  _need(meta['credential_sha256']==r['credential_sha256'] and meta['execution_generation']==value['owner_generation'])
  identity=meta['contexts'][0]['private_account_id'];account=next(row['parsed']['observation'] for row in rows if row['request']['operation']=='ACCOUNT')
  _need(reference_sha(dict(purpose='COMPERTUM_PAPER_ALIAS_IDENTITY_V1',project_id=owner.lease.project_id,account_alias=alias,private_account_id=identity))==r['identity_sha256'])
  refs=[dict(request_sha256=reference_sha(row['request']),parsed_sha256=reference_sha(row['parsed']),raw_sha256=row['parsed']['raw_sha256'],received_at=row['parsed']['received_at']) for row in rows]
  _need(reference_sha(dict(private_account_id=identity,account=account,references=refs))==r['opening_observation_sha256'])
  cash=account['cash'];number(cash)
  if r['disposition']=='CLEAN_ZERO_HISTORY':
   status=meta['status'];_need(status['state']=='PREPARATION_COMPLETE' and status['positions']==status['orders']==0 and status['orders_coverage']=='OBSERVED_SHORT_TERMINAL_PAGE')
   _need(account['status']=='ACTIVE' and not any(account[k] for k in ('trading_blocked','account_blocked','trade_suspended_by_user')) and number(cash)>=0)
 return record,cash

def record_confirmation_opening(owner,record,manifest,history,reasons,*,new_alias):
 """Only account_confirm calls this inside its existing atomic transaction."""
 _need(owner.db.in_transaction,'PAPER_OPENING_TRANSACTION_REQUIRED')
 alias=record['proposal']['account_alias'];existing=binding._state(owner,_PREFIX+alias)
 if new_alias:
  _need(existing is None,'PAPER_OPENING_CONFLICT')
  reference=build_reference(record,manifest,history,reasons,restore_clear=_restore_clear(owner))
  _reference_secrecy(owner,reference)
  binding._put(owner,_PREFIX+alias,reference,new=True)
  _original(owner,alias)
 elif existing is not None:_original(owner,alias)
 # An existing legacy alias with no reference remains unrecorded, never repaired.

def validate_confirmation_opening(owner,alias):
 if binding._state(owner,_PREFIX+alias) is not None:_original(owner,alias)

def _public(owner,record,status,reasons,packet=None):
 r=record['reference'];result=dict(version=1,record_type='PaperOpeningDiagnostic',scope='INITIAL_BASELINE_ONLY',account_alias=r['account_alias'],opening_reference_sha256=record['sha256'],first_packet_id=r['first_packet_id'],current_packet_id=packet,opening_status=status,deficiencies=sorted(set(reasons)),trading_status='BLOCKED',transport_authorized=False,financial_accepted=False,actual_flat=None)
 raw=canonical(result);_need(len(raw)<=8192)
 protected=load_paper_slot(owner.lease,r['account_alias'])
 with open_paper_credentials(owner.lease,protected) as opened:_reject_reflections(raw,tuple(opened.headers().values()))
 return result

def opening_history(owner,alias):
 with _owner_scope(owner.lease),owner.store._live():
  require_live_owner(owner.lease,'execution');_need(not owner._closed,'READ_OWNER_CLOSED')
  try:
   record,_=_original(owner,alias)
   return _public(owner,record,'HISTORICAL_ONLY',record['reference']['deficiencies'])
  except (ContractError,ValueError,TypeError,KeyError,OverflowError,RecursionError):raise RuntimeRefused('PAPER_OPENING_INVALID') from None

def current_opening(owner,packet,manifest):
 with _owner_scope(owner.lease),owner.store._live():
  require_live_owner(owner.lease,'execution');_need(not owner._closed,'READ_OWNER_CLOSED')
  try:
   value=owner._read(packet);proposal,confirmed,p,history,reasons=binding._live(owner,value,manifest)
   _need(confirmed['confirmed_at'] is not None and p['transport_provenance']=='PAPER_TLS','PAPER_OPENING_CURRENT_CONFIRMATION_REQUIRED')
   record,original_cash=_original(owner,p['account_alias']);r=record['reference']
   # Decryption and provenance checking consume lifetime. Refresh all live facts.
   again,confirmed,p,history,reasons=binding._live(owner,value,manifest);_need(again is proposal)
   _need(confirmed['confirmed_at'] is not None and p['transport_provenance']=='PAPER_TLS','PAPER_OPENING_CURRENT_CONFIRMATION_REQUIRED')
   _need(confirmed['proposal']['identity_sha256']==r['identity_sha256'] and confirmed['proposal']['credential_sha256']==r['credential_sha256'],'PAPER_OPENING_IDENTITY_CHANGED')
   reasons=list(reasons)+r['deficiencies']
   if history['status']=='UNVERIFIED' or any(history[k]!=r['history'][k] for k in ('sequence','sha256','empty')):reasons.append('OPENING_HISTORY_CHANGED')
   account=next(json.loads(raw)['observation'] for _,raw in proposal._context._records if json.loads(raw)['operation']=='ACCOUNT')
   if number(original_cash)<0 or number(account['cash'])<0:reasons.append('NEGATIVE_ACCOUNT_CASH')
   elif not cash_matches(original_cash,account['cash']):reasons.append('UNEXPLAINED_CASH_CHANGE')
   result=_public(owner,record,'BLOCKED' if reasons or r['disposition']!='CLEAN_ZERO_HISTORY' else 'CURRENT_CLEAN_OPENING',reasons,packet)
   proposal._context.diagnostic()
   return result
  except (ContractError,ValueError,TypeError,KeyError,OverflowError,RecursionError):raise RuntimeRefused('PAPER_OPENING_INVALID') from None
