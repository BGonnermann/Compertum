"""Strict inert market grants and job records. Validation never dispatches work."""
from dataclasses import dataclass
from datetime import timedelta
import hashlib,math,re
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.paper_contracts import strict_json,timestamp
from compertum.paper_market_inputs import OperationalMarketPlan,_day,_ns
from .errors import RuntimeRefused

_PURPOSE='COMPERTUM_OPERATIONAL_MARKET_GRANT_V1'
_GRANT_FIELDS={'version','purpose','job_id','task_id','reservation_id','project_id','account_alias',
               'owner_instance','owner_generation','subject_key','credential_sha256','mode','plan',
               'plan_sha256','history','created_at','start_expires_at','prepared_mono','routes',
               'transport_authorized','financial_accepted'}
_RECORD_FIELDS={'version','purpose','grant','grant_sha256','state','consumed','reason','summary','evidence','manifest'}
_STATES={'PREPARED','GRANTED','RUNNING','EVIDENCE_READY','PUBLISHED','COMPLETE','ABORTED','CANCELED','INTERRUPTED'}
_PRODUCER_STATES={'READY','PENDING','WAITING','PAGINATION_COMPLETE','PAIR_COMPLETE','INCOMPLETE'}
_CIPHER_MAX=3*1024**2
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError)


def _need(value):
 if not value:raise RuntimeRefused('MARKET_GRANT_INVALID')


def _hash(value):_need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)
def _reason(value):_need(value is None or type(value) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',value) is not None)


def _manifest(value,task,job):
 _need(type(value) is dict and set(value)=={'artifact_id','task_id','path','size_bytes','sha256'})
 uuid(value['artifact_id']);_need(value['task_id']==task)
 _need(value['path']==f'artifacts/runs/{task}/market-collection-{job}.bin')
 _need(type(value['size_bytes']) is int and 0<value['size_bytes']<=_CIPHER_MAX);_hash(value['sha256'])


def _routes(mode,symbol):
 if mode=='FRESH':
  pairs=[('ASSET','https://paper-api.alpaca.markets','/v2/assets/'+symbol),
         ('QUOTE','https://data.alpaca.markets','/v2/stocks/quotes/latest')]
 else:
  _need(mode in {'HISTORY','CURRENT_ACTIONS'})
  pairs=[(mode,'https://data.alpaca.markets','/v2/stocks/bars' if mode=='HISTORY' else '/v1/corporate-actions')]
 return [dict(operation=op,origin=origin,method='GET',path=path) for op,origin,path in pairs]


def _validate_grant(p):
 _need(type(p) is dict and set(p)==_GRANT_FIELDS)
 _need(type(p['version']) is int and p['version']==1 and p['purpose']==_PURPOSE)
 for key in ('job_id','task_id','owner_instance'):uuid(p[key])
 for key in ('project_id','subject_key','credential_sha256','plan_sha256'):_hash(p[key])
 _need(type(p['owner_generation']) is int and 0<p['owner_generation']<2**63)
 _need(type(p['prepared_mono']) in (int,float) and math.isfinite(p['prepared_mono']) and 0<=p['prepared_mono']<1e15)
 _need(type(p['mode']) is str and p['mode'] in {'HISTORY','CURRENT_ACTIONS','FRESH'})
 plan=OperationalMarketPlan(canonical(p['plan']));v=plan.to_payload()
 _need(p['plan_sha256']==plan.sha256 and p['project_id']==v['project_id'] and p['account_alias']==v['account_alias'])
 at=timestamp(p['created_at']);_need(at.isoformat()==p['created_at'])
 _need(p['start_expires_at']==(at+timedelta(seconds=60)).isoformat())
 _need(_day(p['created_at'])==v['session_date'] and _ns(p['created_at'])>=_ns(v['created_at']))
 _need(p['routes']==_routes(p['mode'],v['symbol']))
 _need(p['transport_authorized'] is False and p['financial_accepted'] is False)
 if p['mode']=='FRESH':
  _need(p['reservation_id'] is None);h=p['history']
  _need(type(h) is dict and set(h)=={'job_id','task_id','grant_sha256','manifest'})
  uuid(h['job_id']);uuid(h['task_id']);_hash(h['grant_sha256'])
  _need(h['job_id']!=p['job_id'] and h['task_id']!=p['task_id']);_manifest(h['manifest'],h['task_id'],h['job_id'])
 else:
  uuid(p['reservation_id']);_need(p['history'] is None and _ns(p['created_at'])<_ns(v['history_cutoff_at']))


@dataclass(frozen=True,slots=True,repr=False)
class MarketGrant:
 content:bytes
 def __post_init__(self):
  try:
   _need(type(self.content) is bytes and 0<len(self.content)<=24576)
   p=strict_json(self.content);_validate_grant(p);_need(canonical(p)==self.content)
  except _INVALID:raise RuntimeRefused('MARKET_GRANT_INVALID') from None
 def to_payload(self):return strict_json(self.content)
 @property
 def sha256(self):return hashlib.sha256(self.content).hexdigest()
 def __repr__(self):return '<InertMarketGrant>'


def build_grant(*,job_id,task_id,reservation_id,project_id,owner_instance,owner_generation,
                subject_key,credential_sha256,mode,plan,history,created_at,prepared_mono):
 try:
  _need(type(plan) is OperationalMarketPlan);plan.__post_init__();v=plan.to_payload()
  p=dict(version=1,purpose=_PURPOSE,job_id=job_id,task_id=task_id,reservation_id=reservation_id,
         project_id=project_id,account_alias=v['account_alias'],owner_instance=owner_instance,
         owner_generation=owner_generation,subject_key=subject_key,credential_sha256=credential_sha256,
         mode=mode,plan=v,plan_sha256=plan.sha256,history=history,created_at=created_at,
         start_expires_at=(timestamp(created_at)+timedelta(seconds=60)).isoformat(),prepared_mono=prepared_mono,
         routes=_routes(mode,v['symbol']),transport_authorized=False,financial_accepted=False)
  return MarketGrant(canonical(p))
 except _INVALID:raise RuntimeRefused('MARKET_GRANT_INVALID') from None


def initial_record(grant):
 _need(type(grant) is MarketGrant);grant.__post_init__()
 return dict(version=1,purpose='COMPERTUM_MARKET_JOB_V1',grant=grant.to_payload(),grant_sha256=grant.sha256,
             state='PREPARED',consumed=False,reason=None,summary=None,evidence=None,manifest=None)


def validate_record(value):
 try:
  _need(type(value) is dict and set(value)==_RECORD_FIELDS and len(canonical(value))<=32768)
  _need(type(value['version']) is int and value['version']==1 and value['purpose']=='COMPERTUM_MARKET_JOB_V1')
  grant=MarketGrant(canonical(value['grant']));g=grant.to_payload();_need(grant.sha256==value['grant_sha256'])
  _need(type(value['state']) is str and value['state'] in _STATES and type(value['consumed']) is bool)
  _need(value['state'] not in {'PREPARED','GRANTED'} or not value['consumed'])
  _need(value['state'] not in {'RUNNING','EVIDENCE_READY','PUBLISHED','COMPLETE'} or value['consumed'])
  _reason(value['reason']);summary=value['summary'];evidence=value['evidence'];manifest=value['manifest']
  if summary is not None:
   _need(type(summary) is dict and set(summary)=={'state','reason','attempts','responses'} and value['consumed'])
   _need(type(summary['state']) is str and summary['state'] in _PRODUCER_STATES);_reason(summary['reason'])
   _need(type(summary['attempts']) is int and 0<=summary['attempts']<=(2 if g['mode']=='FRESH' else 8))
   _need(type(summary['responses']) is int and 0<=summary['responses']<=summary['attempts'])
   _need(summary['state']!=('PAGINATION_COMPLETE' if g['mode']=='FRESH' else 'PAIR_COMPLETE'))
   if summary['state']=='PAIR_COMPLETE':
    _need(summary['attempts']==summary['responses']==2 and summary['reason'] is None)
   if summary['state']=='PAGINATION_COMPLETE':_need(summary['responses']>=1 and summary['reason'] is None)
   if summary['state']=='INCOMPLETE':_need(summary['reason'] is not None)
  if evidence is not None:
   _need(g['mode']!='FRESH' and value['consumed'] and type(evidence) is dict and set(evidence)=={'size_bytes','sha256'})
   _need(type(evidence['size_bytes']) is int and 0<evidence['size_bytes']<=_CIPHER_MAX);_hash(evidence['sha256'])
  if manifest is not None:
   _need(evidence is not None and value['state']=='PUBLISHED');_manifest(manifest,g['task_id'],g['job_id'])
   _need(all(manifest[k]==evidence[k] for k in ('size_bytes','sha256')))
  if value['state'] in {'PUBLISHED','EVIDENCE_READY'}:
   _need(summary is not None and summary['state'] in {'PAGINATION_COMPLETE','INCOMPLETE'})
  if value['state']=='PUBLISHED':_need(manifest is not None)
  if value['state']=='EVIDENCE_READY':_need(evidence is not None)
  if value['state']=='COMPLETE':_need(g['mode']=='FRESH' and summary is not None and summary['state']=='PAIR_COMPLETE')
  return value
 except _INVALID:raise RuntimeRefused('MARKET_GRANT_INVALID') from None
