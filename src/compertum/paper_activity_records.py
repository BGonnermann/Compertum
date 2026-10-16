"""Inert private activity records. These records do not qualify native evidence."""
from dataclasses import dataclass,field
import hashlib,json,re
from urllib.parse import urlencode
from .data.encoding import canonical
from .paper_contracts import identifier,number,require,strict_json,symbol,timestamp,utc
from .runtime.errors import RuntimeRefused
from .runtime.paper_read_packet import _local_time,_nanoseconds

_ANCHORS=('project_id','account_alias','opening_sha256','account_context_sha256',
    'history_sha256','credential_sha256','account_identity_sha256','after','until','started_at')
_INPUTS=('project_id','account_alias','opening_sha256','account_context_sha256',
    'history_sha256','credential_sha256','after','until','started_at','created_at','request_id','page_token')
_FILL={'activity_type','id','order_id','symbol','side','qty','cum_qty','leaves_qty','price','transaction_time','type'}


def sha(raw):return hashlib.sha256(raw).hexdigest()


def _token(value):
    require(type(value) is str and 3<=len(value)<=128 and re.fullmatch('[A-Za-z0-9._:-]+',value) is not None)
    left,separator,right=value.partition('::');require(bool(left and separator and right))
    return value


def _payload(expected_account_id,**v):
    identifier(expected_account_id);identifier(v['request_id'])
    for key in ('project_id','opening_sha256','account_context_sha256','history_sha256','credential_sha256'):
        require(type(v[key]) is str and re.fullmatch('[0-9a-f]{64}',v[key]) is not None)
    require(type(v['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v['account_alias']) is not None)
    after,until,started,created=[timestamp(v[k]) for k in ('after','until','started_at','created_at')]
    require(after<until<=started<=created and (created-started).total_seconds()<20)
    for key in ('after','until','started_at','created_at'):require(utc(v[key])==v[key])
    query=dict(after=v['after'],until=v['until'],direction='asc',page_size=25)
    if v['page_token'] is not None:query['page_token']=_token(v['page_token'])
    timeout=min(10000,int((20-(created-started).total_seconds())*1000));require(timeout>0)
    result=dict(version=1,record_type='PreparedPaperActivityRequest',scope='UNQUALIFIED_ACTIVITY_OBSERVATION',
        origin='https://paper-api.alpaca.markets',method='GET',path='/v2/account/activities',
        target='/v2/account/activities?'+urlencode(query),parameters=query,**v,
        account_identity_sha256=sha(expected_account_id.encode()),timeout_ms=timeout,maximum_pages=8,
        packet_timeout_seconds=20,maximum_raw_bytes=512*1024,maximum_retries=0,
        approval_status='NOT_GRANTED',financial_accepted=False,transport_authorized=False)
    require(expected_account_id.encode() not in canonical(result))
    return result


@dataclass(frozen=True,slots=True,repr=False)
class PreparedActivityRequest:
    content:bytes
    expected_account_id:str=field(repr=False)
    def __post_init__(self):
        p=strict_json(self.content);require(type(p) is dict and all(k in p for k in _INPUTS))
        require(canonical(_payload(self.expected_account_id,**{k:p[k] for k in _INPUTS}))==self.content)
    def to_payload(self):return json.loads(self.content)
    @property
    def sha256(self):return sha(self.content)
    def __repr__(self):return '<PreparedActivityRequest private data redacted>'
    def __reduce_ex__(self,p):raise RuntimeRefused('PAPER_ACTIVITY_SERIALIZATION_FORBIDDEN')


def prepare_activity_request(*,expected_account_id,**values):
    require(set(values)==set(_INPUTS))
    return PreparedActivityRequest(canonical(_payload(expected_account_id,**values)),expected_account_id)


def _page(request,raw,received_at):
    require(type(request) is PreparedActivityRequest);request.__post_init__();r=request.to_payload()
    rows=strict_json(raw);require(type(rows) is list and len(rows)<=25)
    received=timestamp(received_at);require(utc(received_at)==received_at)
    require(0<=(received-timestamp(r['created_at'])).total_seconds()<=r['timeout_ms']/1000
        and 0<=(received-timestamp(r['started_at'])).total_seconds()<20)
    ids=set();unsupported=0
    for row in rows:
        require(type(row) is dict);key=_token(row.get('id'));require(key not in ids);ids.add(key)
        kind=row.get('activity_type');require(type(kind) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,31}',kind) is not None)
        if kind!='FILL':unsupported+=1;continue
        require(set(row)==_FILL);identifier(row['order_id']);symbol(row['symbol'])
        require(row['side'] in {'buy','sell'} and row['type'] in {'fill','partial_fill'})
        qty=number(row['qty'],positive=True);cum=number(row['cum_qty'],positive=True);leaves=number(row['leaves_qty'])
        number(row['price'],positive=True);timestamp(row['transaction_time'])
        require(qty<=cum and leaves>=0 and (leaves==0)==(row['type']=='fill'))
    result=dict(version=1,record_type='ParsedPaperActivityPage',scope='UNQUALIFIED_ACTIVITY_OBSERVATION',
        request_sha256=request.sha256,received_at=received_at,rows=rows,unsupported_activities=unsupported,
        raw_sha256=sha(raw),raw_bytes=len(raw),native_transport_verified=False,
        financial_accepted=False,transport_authorized=False)
    content=canonical(result);require(len(content)<=65536)
    return content


@dataclass(frozen=True,slots=True,repr=False)
class ParsedActivityPage:
    request:PreparedActivityRequest
    raw:bytes=field(repr=False)
    content:bytes=field(repr=False)
    received_at:str
    def __post_init__(self):require(_page(self.request,self.raw,self.received_at)==self.content)
    def to_payload(self):return json.loads(self.content)
    def __repr__(self):return '<ParsedActivityPage private data redacted>'
    def __reduce_ex__(self,p):raise RuntimeRefused('PAPER_ACTIVITY_SERIALIZATION_FORBIDDEN')


def parse_activity_page(request,raw,*,received_at):
    _local_time(received_at)
    received_at=utc(received_at)
    return ParsedActivityPage(request,raw,_page(request,raw,received_at),received_at)


def activity_traversal(pages):
    """Describe only the requested traversal. No liability or ownership closure."""
    require(type(pages) is tuple and 0<len(pages)<=8)
    anchor=None;previous=None;last_fill=None;ids=set();requests=set();total=rows=unsupported=0;issues=set()
    for page in pages:
        require(type(page) is ParsedActivityPage);page.__post_init__();p=page.to_payload();r=page.request.to_payload()
        current={k:r[k] for k in _ANCHORS}
        if anchor is None:anchor=current;require(r['page_token'] is None)
        else:
            require(anchor==current and len(previous['rows'])==25 and r['page_token']==previous['rows'][-1]['id'])
            require(timestamp(r['created_at'])>=timestamp(previous['received_at']))
        require(r['request_id'] not in requests);requests.add(r['request_id'])
        total+=p['raw_bytes'];require(total<=512*1024)
        for row in p['rows']:
            require(row['id'] not in ids);ids.add(row['id'])
            if row['activity_type']=='FILL':
                at=_nanoseconds(row['transaction_time']);require(last_fill is None or last_fill<=at);last_fill=at
                if not _nanoseconds(r['after'])<=at<=_nanoseconds(r['until']):issues.add('ACTIVITY_TIME_OUTSIDE_QUERY_INTERVAL')
        rows+=len(p['rows']);unsupported+=p['unsupported_activities'];previous=p
    complete=len(previous['rows'])<25
    if not complete:issues.add('ACTIVITIES_TRUNCATED')
    if unsupported:issues.add('UNSUPPORTED_ACTIVITY')
    issues.update({'NATIVE_PROVENANCE_UNVERIFIED','OWNERSHIP_UNVERIFIED','ECONOMIC_COVERAGE_UNVERIFIED',
        'FEE_LIABILITIES_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED'})
    return dict(version=1,record_type='PaperActivityTraversalObservation',scope='UNQUALIFIED_ACTIVITY_OBSERVATION',
        status='BLOCKED',traversal_complete=complete,pages=len(pages),rows=rows,raw_bytes=total,
        unsupported_activities=unsupported,deficiencies=sorted(issues),actual_flat=None,
        native_transport_verified=False,financial_accepted=False,transport_authorized=False)
