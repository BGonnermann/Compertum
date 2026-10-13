"""Immutable alias-only read preparation. These records never grant transport."""
from dataclasses import dataclass,field
import hashlib
import json
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from .data.encoding import canonical
from .domain import ContractError
from .paper_contracts import PAPER_ORIGIN,identifier,timestamp,utc,session_date,strict_json
from .runtime.errors import RuntimeRefused


def _need(value):
    if not value:raise ContractError('INVALID_PAPER_READ_PREPARATION')


def _plan_payload(project_id,account_alias,created_at,start_expires_at,session_date):
    _need(type(project_id) is str and re.fullmatch(r'[0-9a-f]{64}',project_id) is not None)
    _need(type(account_alias) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',account_alias) is not None)
    start,end=timestamp(created_at),timestamp(start_expires_at)
    _need(0<(end-start).total_seconds()<=60)
    _need(type(session_date) is str and start.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session_date)
    return dict(version=1,record_type='PreparedPaperReadPlan',approval_status='NOT_GRANTED',financial_accepted=False,
                project_id=project_id,account_alias=account_alias,origin=PAPER_ORIGIN,created_at=utc(created_at),
                start_expires_at=utc(start_expires_at),session_date=session_date,maximum_gets=13,maximum_order_pages=8,
                orders_per_page=25,packet_timeout_seconds=30,request_timeout_seconds=10,
                sequence=['ACCOUNT','CLOCK','CALENDAR','POSITIONS','ORDERS_UNTIL_SHORT_PAGE','CLOCK'])


@dataclass(frozen=True,slots=True)
class PreparedReadPlan:
    content:bytes
    def __post_init__(self):
        p=strict_json(self.content);_need(type(p) is dict)
        names=('project_id','account_alias','created_at','start_expires_at','session_date')
        _need(all(k in p for k in names))
        _need(canonical(_plan_payload(**{k:p[k] for k in names}))==self.content)
    @property
    def sha256(self):return hashlib.sha256(self.content).hexdigest()
    def to_payload(self):return json.loads(self.content)


def prepare_read_plan(**values):return PreparedReadPlan(canonical(_plan_payload(**values)))


def _request_payload(plan,*,request_id,operation,created_at,packet_started_at,expected_account_id,credential_sha256,after_order_id):
    _need(type(plan) is PreparedReadPlan);p=plan.to_payload();identifier(request_id)
    _need(type(credential_sha256) is str and re.fullmatch(r'[0-9a-f]{64}',credential_sha256) is not None)
    _need(type(operation) is str and operation in ('ACCOUNT','CLOCK','CALENDAR','POSITIONS','ORDERS'))
    if expected_account_id is None:_need(operation=='ACCOUNT')
    else:identifier(expected_account_id)
    dispatched,started=timestamp(created_at),timestamp(packet_started_at)
    _need(timestamp(p['created_at'])<=started<timestamp(p['start_expires_at']))
    elapsed=(dispatched-started).total_seconds();_need(0<=elapsed<30)
    _need(dispatched.astimezone(ZoneInfo('America/New_York')).date().isoformat()==p['session_date'])
    _need(started.astimezone(ZoneInfo('America/New_York')).date().isoformat()==p['session_date'])
    parameters={}
    if operation=='ORDERS':
        parameters=dict(status='all',direction='asc',nested=False,limit=25)
        if after_order_id is not None:identifier(after_order_id);parameters['after_order_id']=after_order_id
    else:
        _need(after_order_id is None)
        if operation=='CALENDAR':parameters=dict(start=p['session_date'],end=p['session_date'])
    query={k:('false' if v is False else v) for k,v in parameters.items()}
    path='/v2/'+operation.lower();target=path+('?' + urlencode(query) if query else '')
    timeout_ms=min(10000,int((30-elapsed)*1000));_need(timeout_ms>0)
    return dict(version=1,record_type='PreparedPaperReadRequest',approval_status='NOT_GRANTED',financial_accepted=False,
                plan_sha256=plan.sha256,request_id=request_id,account_alias=p['account_alias'],origin=PAPER_ORIGIN,
                operation=operation,method='GET',path=path,target=target,parameters=parameters,
                created_at=utc(created_at),packet_started_at=utc(packet_started_at),timeout_ms=timeout_ms)


@dataclass(frozen=True,slots=True,repr=False)
class PreparedReadRequest:
    plan:PreparedReadPlan
    content:bytes
    expected_account_id:str|None=field(repr=False)
    credential_sha256:str=field(repr=False)
    def __post_init__(self):
        p=strict_json(self.content);_need(type(p) is dict)
        names=('request_id','operation','created_at','packet_started_at')
        _need(all(k in p for k in names) and type(p.get('parameters')) is dict)
        expected=_request_payload(self.plan,**{k:p[k] for k in names},expected_account_id=self.expected_account_id,
            credential_sha256=self.credential_sha256,after_order_id=p['parameters'].get('after_order_id'))
        _need(canonical(expected)==self.content)
    @property
    def sha256(self):return hashlib.sha256(self.content).hexdigest()
    def to_payload(self):return json.loads(self.content)
    def __repr__(self):return '<PreparedReadRequest private context redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_READ_PRIVATE_SERIALIZATION_FORBIDDEN')


def prepare_read_request(plan,*,request_id,operation,created_at,packet_started_at,expected_account_id,credential_sha256,after_order_id=None):
    payload=_request_payload(plan,request_id=request_id,operation=operation,created_at=created_at,
        packet_started_at=packet_started_at,expected_account_id=expected_account_id,credential_sha256=credential_sha256,after_order_id=after_order_id)
    return PreparedReadRequest(plan,canonical(payload),expected_account_id,credential_sha256)
