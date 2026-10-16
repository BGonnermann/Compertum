"""Strict retained native-write evidence. Parsing never grants dispatch authority.

There is no producer or transport in this module. The execution owner must
qualify original proofs before recording these records in a later increment.
"""
import hashlib
import re
from .data.encoding import canonical
from .domain import ContractError
from .paper_contracts import identifier, utc
from .runtime.paper_read_packet import _local_time
from .runtime._winhttp_order import _wire

NATIVE_TYPE='NativePaperWrite'
STATES=frozenset({'NATIVE_CONSUMED','NATIVE_UNKNOWN','NATIVE_ACKNOWLEDGED',
    'NATIVE_PARTIALLY_FILLED','NATIVE_FILLED','NATIVE_CANCELED','NATIVE_EXPIRED','NATIVE_REJECTED'})
EVIDENCE=frozenset({'intent','confirmation','presence','opening','ownership','economics','risk','inputs'})


def _need(value):
    if not value:raise ValueError('INVALID_NATIVE_WRITE_RECORD')


def sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def _hash(value):_need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)


def native_client_id(project_id,account_alias,intent_id):
    _hash(project_id);identifier(intent_id)
    _need(type(account_alias) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',account_alias) is not None)
    return 'cmp-'+sha(dict(scope='NATIVE_PAPER_WRITE',project_id=project_id,
        account_alias=account_alias,intent_id=intent_id))[:40]


def validate_pair(intent,decision):
    try:return _validate(intent,decision)
    except (ContractError,KeyError,TypeError,AttributeError,OverflowError):
        raise ValueError('INVALID_NATIVE_WRITE_RECORD') from None


def _validate(p,d):
    fields={'version','record_type','scope','project_id','account_alias','intent_id','generation',
        'owner_instance','created_at','expires_at','purpose','client_order_id','evidence_sha256',
        'request','request_sha256'}
    _need(type(p) is dict and set(p)==fields and type(p['version']) is int and p['version']==1)
    _need(p['record_type']==NATIVE_TYPE and p['scope']=='NATIVE_PAPER_WRITE')
    _need(type(p['generation']) is int and 0<p['generation']<2**63);identifier(p['owner_instance'])
    _need(p['client_order_id']==native_client_id(p['project_id'],p['account_alias'],p['intent_id']))
    _need(utc(p['created_at'])==p['created_at'] and utc(p['expires_at'])==p['expires_at'])
    _need(0<(_local_time(p['expires_at'])-_local_time(p['created_at'])).total_seconds()<=60)
    evidence=p['evidence_sha256'];_need(type(evidence) is dict and set(evidence)==EVIDENCE)
    for value in evidence.values():_hash(value)
    _hash(p['request_sha256']);r=p['request']
    _need(type(r) is dict and set(r)=={'version','record_type','scope','project_id','account_alias',
        'request_id','intent_id','created_at','operation','method','target','parameters','body',
        'transport_authorized','financial_accepted','approval_status'})
    _need(type(r['version']) is int and r['version']==1 and r['record_type']=='PreparedPaperOrderExchange'
        and r['scope']=='PREPARATION_ONLY' and r['approval_status']=='NOT_GRANTED'
        and r['transport_authorized'] is r['financial_accepted'] is False)
    identifier(r['request_id'])
    _need(all(r[key]==p[key] for key in ('project_id','account_alias','intent_id','created_at')))
    _need(r['operation'] in {'SUBMIT_ORDER','CANCEL_ORDER'} and sha(r)==p['request_sha256'])
    method,target,_=_wire(r['operation'],r['parameters'],r['body'])
    _need((method,target)==(r['method'],r['target']))
    purpose=p['purpose'];_need(type(purpose) is str and purpose in
        {'CANCEL','CLOSE_LONG','FIXTURE_BUY','FIXTURE_RESTING_BUY','STRATEGY'})
    _need((purpose=='CANCEL')==(r['operation']=='CANCEL_ORDER'))
    if r['operation']=='SUBMIT_ORDER':
        body=r['body'];_need(body['client_order_id']==p['client_order_id'])
        if purpose.startswith('FIXTURE_'):
            _need(body['qty']=='1' and body['side']=='buy')
        if purpose=='CLOSE_LONG':_need(body['side']=='sell')
        _need(body['type']==('limit' if purpose=='FIXTURE_RESTING_BUY' else 'market'))
    expected=dict(version=1,record_type='NativePaperWriteBinding',scope='RETAINED_EVIDENCE_ONLY',
        intent_sha256=sha(p),transport_authorized=False,financial_accepted=False)
    _need(type(d) is dict and canonical(d)==canonical(expected))
    _need(len(canonical(p))+len(canonical(d))<=65536)
    return p,d,p['client_order_id']
