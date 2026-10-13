"""Strict inert paper preparation records for the shared execution journal."""
import hashlib,re
from .data.encoding import canonical
from .paper_contracts import identifier,utc
from .runtime.paper_read_packet import _local_time
from .runtime._winhttp_order import _wire
from .runtime.errors import RuntimeRefused

PAPER_TYPE='PaperIntentPreparation'
UNCONSUMED=frozenset({'PAPER_PREPARED','PAPER_SKIPPED_RESTART','PAPER_SKIPPED_WINDOW_EXPIRED'})
STATES=UNCONSUMED|{'PAPER_CONSUMED'}

def _need(v):
    if not v:raise ValueError()

def _hash(v):_need(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) is not None)
def sha(v):return hashlib.sha256(canonical(v)).hexdigest()

def paper_client_id(project_id,account_alias,intent_id):
    _hash(project_id);identifier(intent_id)
    _need(type(account_alias) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',account_alias) is not None)
    return 'cmp-'+sha(dict(scope='PAPER_PREPARATION',project_id=project_id,account_alias=account_alias,intent_id=intent_id))[:40]

def binding(intent):
    return dict(version=1,record_type='PaperPreparationBinding',scope='PAPER_PREPARATION',intent_sha256=sha(intent),
                transport_authorized=False,financial_accepted=False,approval_status='NOT_GRANTED')

def validate_pair(intent,decision):
    keys={'version','record_type','scope','project_id','account_alias','intent_id','generation','owner_instance','created_at','expires_at',
          'request','request_sha256','credential_sha256','private_context_sha256','client_order_id','supporting_sha256',
          'transport_authorized','financial_accepted','approval_status'}
    _need(type(intent) is dict and set(intent)==keys and type(intent['version']) is int and intent['version']==1
          and intent['record_type']==PAPER_TYPE and intent['scope']=='PAPER_PREPARATION')
    p=intent;_need(type(p['generation']) is int and 0<p['generation']<2**63);identifier(p['owner_instance'])
    for k in ('request_sha256','credential_sha256','private_context_sha256'):_hash(p[k])
    _need(p['client_order_id']==paper_client_id(p['project_id'],p['account_alias'],p['intent_id']))
    _need(p['transport_authorized'] is p['financial_accepted'] is False and p['approval_status']=='NOT_GRANTED')
    age=(_local_time(p['expires_at'])-_local_time(p['created_at'])).total_seconds();_need(0<age<=60)
    _need(utc(p['created_at'])==p['created_at'] and utc(p['expires_at'])==p['expires_at'])
    support=p['supporting_sha256'];_need(type(support) is dict and 1<=len(support)<=4 and set(support)<={'plan','risk','supervision','ownership'})
    for v in support.values():_hash(v)
    r=p['request'];_need(type(r) is dict and set(r)=={'version','record_type','scope','project_id','account_alias','request_id','intent_id','created_at','operation','method','target','parameters','body','transport_authorized','financial_accepted','approval_status'})
    _need(type(r['version']) is int and r['version']==1 and r['record_type']=='PreparedPaperOrderExchange' and r['scope']=='PREPARATION_ONLY')
    identifier(r['request_id']);_need(r['operation'] in {'SUBMIT_ORDER','CANCEL_ORDER'})
    _need(all(r[k]==p[k] for k in ('project_id','account_alias','intent_id','created_at','approval_status'))
          and r['transport_authorized'] is r['financial_accepted'] is False and sha(r)==p['request_sha256'])
    method,target,raw=_wire(r['operation'],r['parameters'],r['body']);_need((method,target)==(r['method'],r['target']))
    if r['operation']=='SUBMIT_ORDER':_need(r['body']['client_order_id']==p['client_order_id'])
    _need(type(decision) is dict and canonical(decision)==canonical(binding(p)) and len(canonical(p))+len(canonical(decision))<=65536)
    return p,decision,p['client_order_id']

def prepare(lease,request,*,expires_at,supporting_sha256):
    from .runtime.paper_order_qualification import _PreparedOrderExchange
    from .domain import ContractError
    try:
        _need(type(request) is _PreparedOrderExchange)
        r=request._verify(lease,request._protected)
        p=dict(version=1,record_type=PAPER_TYPE,scope='PAPER_PREPARATION',project_id=lease.project_id,account_alias=r['account_alias'],
               intent_id=r['intent_id'],generation=lease.generation,owner_instance=lease.identity.process_instance_id,
               created_at=r['created_at'],expires_at=utc(expires_at),request=r,request_sha256=request.sha256,
               credential_sha256=request._credential_sha256,private_context_sha256=request._private_binding,
               client_order_id=paper_client_id(lease.project_id,r['account_alias'],r['intent_id']),supporting_sha256=supporting_sha256,
               transport_authorized=False,financial_accepted=False,approval_status='NOT_GRANTED')
        _local_time(expires_at);d=binding(p);validate_pair(p,d)
        request._validate_retention(canonical(dict(intent=p,decision=d)))
        return p,d
    except (ValueError,TypeError,KeyError,AttributeError,ContractError):raise RuntimeRefused('INVALID_PAPER_PREPARATION') from None
