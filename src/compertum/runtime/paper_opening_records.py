"""Bounded opening references and cash comparison; these records confer no authority."""
from decimal import Context,DecimalException,DivisionByZero,InvalidOperation,Overflow,ROUND_HALF_EVEN,localcontext
import hashlib,re
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier,number,timestamp
from .errors import RuntimeRefused

_FIELDS={'version','purpose','project_id','account_alias','first_packet_id','proposal_sha256','confirmed_at','identity_sha256','credential_sha256','opening_observation_sha256','manifest','history','history_sha256','disposition','deficiencies'}

def _need(value):
 if not value:raise RuntimeRefused('PAPER_OPENING_INVALID')

def reference_sha(value):return hashlib.sha256(canonical(value)).hexdigest()

def _hash(value):_need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)

def validate_reference(record,project,alias):
 try:
  _need(type(record) is dict and set(record)=={'reference','sha256'});p=record['reference']
  _need(type(p) is dict and set(p)==_FIELDS and record['sha256']==reference_sha(p))
  _need(len(canonical(record))<=8192 and type(p['version']) is int and p['version']==1 and p['purpose']=='PAPER_CLEAN_OPENING_REFERENCE')
  _need(p['project_id']==project and p['account_alias']==alias)
  _hash(project);_need(type(alias) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',alias) is not None)
  identifier(p['first_packet_id']);_need(timestamp(p['confirmed_at']).isoformat()==p['confirmed_at'])
  for key in ('proposal_sha256','identity_sha256','credential_sha256','opening_observation_sha256','history_sha256'):_hash(p[key])
  m=p['manifest'];_need(type(m) is dict and set(m)=={'artifact_id','path','size_bytes','sha256','task_id'})
  identifier(m['artifact_id']);identifier(m['task_id']);_hash(m['sha256'])
  _need(type(m['size_bytes']) is int and 0<m['size_bytes']<=3*1024**2)
  _need(m['path']==f"artifacts/runs/{m['task_id']}/paper-read-{p['first_packet_id']}.bin")
  h=p['history'];_need(type(h) is dict and set(h)=={'status','sequence','sha256','empty'} and type(h['empty']) is bool)
  _need(p['history_sha256']==reference_sha(h))
  if h['status']=='UNVERIFIED':_need(h['sequence'] is None and h['sha256'] is None and not h['empty'])
  else:
   _need(h['status'] in {'VERIFIED_ZERO_PRE_SCHEMA','VERIFIED_HISTORY'} and type(h['sequence']) is int and 0<=h['sequence']<=256);_hash(h['sha256'])
   if h['sequence']==0:_need(h['sha256']=='0'*64)
   if h['status']=='VERIFIED_ZERO_PRE_SCHEMA':_need(h['sequence']==0 and h['empty'])
   if h['empty']:_need(h['sequence']==0)
  reasons=p['deficiencies'];_need(type(reasons) is list and len(reasons)<=16 and all(type(x) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',x) is not None for x in reasons))
  _need(reasons==sorted(set(reasons)))
  if p['disposition']=='CLEAN_ZERO_HISTORY':_need(not reasons and h['status']!='UNVERIFIED' and h['empty'] and h['sequence']==0)
  else:_need(p['disposition']=='BLOCKED' and bool(reasons))
 except (ContractError,ValueError,TypeError,KeyError,OverflowError,RecursionError):raise RuntimeRefused('PAPER_OPENING_INVALID') from None
 return record

def build_reference(record,manifest,history,reasons,*,restore_clear):
 try:
  _need(type(restore_clear) is bool and type(reasons) is list)
  p=record['proposal'];_need(record['proposal_sha256']==reference_sha(p))
  _need(p['history_sha256']==reference_sha(history) and p['manifest_sha256']==reference_sha(manifest) and p['encrypted_evidence_sha256']==manifest['sha256'])
  reasons=sorted(set(reasons+([] if restore_clear else ['RESTORE_HISTORY_PRESENT'])))
  ref=dict(version=1,purpose='PAPER_CLEAN_OPENING_REFERENCE',project_id=p['project_id'],account_alias=p['account_alias'],first_packet_id=p['packet_id'],proposal_sha256=record['proposal_sha256'],confirmed_at=record['confirmed_at'],identity_sha256=p['identity_sha256'],credential_sha256=p['credential_sha256'],opening_observation_sha256=p['opening_observation_sha256'],manifest=manifest,history=history,history_sha256=p['history_sha256'],disposition='BLOCKED' if reasons else 'CLEAN_ZERO_HISTORY',deficiencies=reasons)
  result=dict(reference=ref,sha256=reference_sha(ref));validate_reference(result,p['project_id'],p['account_alias'])
  # Detach caller-owned mutable containers before persistence.
  from compertum.paper_contracts import strict_json
  return strict_json(canonical(result))
 except (ContractError,ValueError,TypeError,KeyError,OverflowError,RecursionError):raise RuntimeRefused('PAPER_OPENING_INVALID') from None

def cash_matches(opening,current):
 try:
  before,now=number(opening),number(current);_need(before>=0 and now>=0)
  with localcontext(Context(prec=128,rounding=ROUND_HALF_EVEN,Emin=-128,Emax=128,capitals=1,clamp=0,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow])):
   return abs(now-before)<=number('0.01')
 except (ContractError,DecimalException,ValueError,TypeError,OverflowError):raise RuntimeRefused('PAPER_OPENING_INVALID') from None
