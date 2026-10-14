"""Pure validation of retained operational read attempts; no scheduling authority."""
from datetime import datetime,timezone
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier
from compertum.paper_market_inputs import (OperationalMarketPlan,OperationalMarketRequest,MarketObservation,
    qualify_market_inputs,_body,_ns,_day,_sha,_token)
from compertum.paper_action_inputs import prepare_action_query,CurrentActionPage,qualify_action_inputs,_request_payload
from .errors import RuntimeRefused
from .http_retry import _RetryAfter,_MAX_NS
from .read_retry import decide_read_retry

_KEYS={'index','page','page_attempt','request','pre_send_at','pre_send_monotonic_ns','dispatch_committed_ns',
       'completed_monotonic_ns','native_closed','observed_status','reply','retry_after','outcome','terminal_reason','retry_not_before_ns'}
_TERMINAL={'HTTP_STATUS_NOT_RETRYABLE','PAGE_ATTEMPT_LIMIT','TASK_DEADLINE','RETRY_EXCEEDS_DEADLINE','TOTAL_ATTEMPT_LIMIT',
           'PAGE_INVALID','REPLY_REFUSED','DISPATCH_FAILED','CANCELLED','TOTAL_DEADLINE','INFORMATION_CUTOFF','NATIVE_CLEANUP_UNVERIFIED'}
# One maximum UTF-8 body can require six JSON bytes per input byte. Requests,
# diagnostics and attempt metadata are reserved separately before dispatch.
_NEXT_MAX=6*65536+65536+8192+16384


def _need(value):
    if not value:raise RuntimeRefused('MARKET_ATTEMPT_EVIDENCE_INVALID')


def _integer(value,minimum=0,maximum=_MAX_NS):
    _need(type(value) is int and minimum<=value<=maximum);return value


def can_retain_attempt(plan,chain):
    _need(type(plan) is OperationalMarketPlan and type(chain) is list and len(chain)<=8)
    plan.__post_init__()
    return len(chain)<8 and len(canonical(dict(plan=plan.to_payload(),attempt_chain=chain)))+_NEXT_MAX<=1048576


def retry_after_payload(value):
    if value is None:return None
    _need(type(value) is _RetryAfter)
    # Reuse the exact validation without interpreting it as a dispatch grant.
    decide_read_retry(status_code=200,completed_attempts=1,failed_at_ns=value.observed_monotonic_ns,
                      now_ns=value.observed_monotonic_ns,deadline_ns=_MAX_NS,retry_after=value)
    return dict(kind=value.kind,delay_ns=value.delay_ns,observed_at=value.observed_at.isoformat().replace('+00:00','Z'),
                observed_monotonic_ns=value.observed_monotonic_ns,not_before_ns=value.not_before_ns)


def _header(value,completed):
    if value is None:return None
    _need(type(value) is dict and set(value)=={'kind','delay_ns','observed_at','observed_monotonic_ns','not_before_ns'})
    _ns(value['observed_at']);at=datetime.fromisoformat(value['observed_at'].replace('Z','+00:00'))
    _need(at.tzinfo is timezone.utc)
    h=_RetryAfter(value['kind'],value['delay_ns'],at,value['observed_monotonic_ns'],value['not_before_ns'])
    decide_read_retry(status_code=200,completed_attempts=1,failed_at_ns=completed,now_ns=completed,deadline_ns=_MAX_NS,retry_after=h)
    return h


def _cursor(raw,mode,symbol):
    body=_body(raw);_need('next_page_token' in body)
    if mode=='HISTORY':
        groups=body.get('bars');_need(type(groups) is dict and set(groups)<={symbol})
        rows=groups.get(symbol,[]);_need(type(rows) is list and len(rows)<=100)
    else:
        groups=body.get('corporate_actions');_need(type(groups) is dict and all(type(rows) is list for rows in groups.values()))
        _need(sum(map(len,groups.values()))<=100)
    return _token(body['next_page_token'])


def _reply(plan,mode,request,reply,observed_status,clock_basis):
    _need(type(reply) is dict and set(reply)=={'body_utf8','diagnostic','validated_at'})
    _need(type(reply['body_utf8']) is str and type(reply['diagnostic']) is dict)
    raw=reply['body_utf8'].encode('utf-8');d=reply['diagnostic'];request_raw=canonical(request)
    _need(type(d['status']) is int and d['status']==observed_status)
    received=d['received_at'];at=request.get('created_at',request.get('requested_at'));rid=request['request_id']
    if mode=='HISTORY':o=MarketObservation(OperationalMarketRequest(plan,request_raw),raw,d['status'],received)
    else:o=CurrentActionPage(prepare_action_query(plan),rid,request['parameters'].get('page_token'),at,received,d['status'],raw)
    provenance='LOOPBACK_FIXTURE' if clock_basis=='SYNTHETIC_FIXTURE' else 'DATA_TLS'
    expected=dict(version=1,record_type='PrivateMarketReply',scope='PREPARATION_ONLY',request_sha256=_sha(request_raw),plan_sha256=plan.sha256,
        request_id=rid,operation=mode,status=d['status'],received_at=received,age_ns=_ns(received)-_ns(at),raw_bytes=len(raw),raw_sha256=_sha(raw),
        transport_provenance=provenance,credential_dispatch_binding='NOT_SENT_FIXTURE' if provenance=='LOOPBACK_FIXTURE' else 'PINNED_ENVELOPE',
        outcome='HTTP_RESPONSE_OBSERVED' if d['status']==200 else 'HTTP_REFUSED',semantic_qualification='NOT_PERFORMED',timestamps='DECLARED',
        transport_authorized=False,financial_accepted=False,research_eligible=False,entitlement='UNVERIFIED',coverage='UNVERIFIED')
    _need(canonical(d)==canonical(expected) and len(canonical(d))<=8192)
    return o,raw,received,provenance


def validate_attempt_chain(plan,*,mode,chain,selected_requests,started_at,started_ns,deadline_ns,clock_basis):
    """Authenticate historical structure, never restore tickets or live deadlines.

    The encrypted-evidence owner authenticates the complete snapshot first.
    This function checks its attempt chain and returns the successful projection.
    """
    try:return _validate(plan,mode,chain,selected_requests,started_at,started_ns,deadline_ns,clock_basis)
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,AttributeError,OverflowError):
        raise RuntimeRefused('MARKET_ATTEMPT_EVIDENCE_INVALID') from None


def _validate(plan,mode,chain,selected_requests,started_at,started_ns,deadline_ns,clock_basis):
    _need(type(plan) is OperationalMarketPlan);plan.__post_init__();p=plan.to_payload()
    _need(type(mode) is str and mode in ('HISTORY','CURRENT_ACTIONS'))
    _need(type(clock_basis) is str and clock_basis in ('LOCAL_CLOCK','SYNTHETIC_FIXTURE'))
    _integer(started_ns);_integer(deadline_ns);cutoff=_ns(p['history_cutoff_at']);start=_ns(started_at)
    _need(_day(started_at)==p['session_date'] and _ns(p['created_at'])<=start<cutoff)
    _need(deadline_ns==started_ns+min(80*10**9,cutoff-start) and deadline_ns<=_MAX_NS)
    _need(type(chain) is list and len(chain)<=8 and type(selected_requests) is list and len(selected_requests)<=8)
    _need(len(canonical(dict(plan=p,attempt_chain=chain)))<=1048576)
    selected=[];records=[];observations=[];tokens=set();ids=set();page=1;ordinal=1;cursor=None
    last_mono=started_ns;last_wall=start;last_valid=started_at;not_before=started_ns;provenances=set();aggregate=None
    for offset,a in enumerate(chain):
        _need(type(a) is dict and set(a)==_KEYS)
        _need(_integer(a['index'],1,8)==offset+1 and _integer(a['page'],1,8)==page and _integer(a['page_attempt'],1,3)==ordinal)
        req=a['request'];_need(type(req) is dict and len(canonical(req))<=65536)
        rid=req['request_id'];identifier(rid);_need(rid not in ids);ids.add(rid)
        at=req.get('created_at',req.get('requested_at'));_need(last_wall<=_ns(at)<cutoff)
        _need(req['parameters'].get('page_token')==cursor)
        if mode=='HISTORY':
            OperationalMarketRequest(plan,canonical(req));_need(req['operation']=='HISTORY')
        else:_need(canonical(req)==canonical(_request_payload(prepare_action_query(plan),rid,at,cursor)))
        completed=_integer(a['completed_monotonic_ns']);_need(completed>=last_mono)
        sent=a['pre_send_at'];pre=a['pre_send_monotonic_ns'];commit=a['dispatch_committed_ns']
        _need((sent is None)==(pre is None))
        if pre is not None:
            _integer(pre);_need(last_mono<=pre<=completed and not_before<=pre<deadline_ns)
            _need(_ns(at)<=_ns(sent)<cutoff and _day(sent)==p['session_date'])
        if commit is not None:_integer(commit);_need(pre is not None and pre<=commit<=completed and commit<deadline_ns)
        _need(type(a['native_closed']) is bool)
        status=a['observed_status'];_need(status is None or type(status) is int and 100<=status<=599)
        if status is not None:_need(commit is not None)
        header=_header(a['retry_after'],completed)
        if header is not None:_need(status is not None and commit<=header.observed_monotonic_ns<=completed)
        outcome=a['outcome'];_need(type(outcome) is str and outcome in ('SELECTED','RETRY','TERMINAL'))
        reason=a['terminal_reason'];target=a['retry_not_before_ns'];reply=a['reply'];observation=None;raw=None
        if reply is not None:
            _need(commit is not None and status is not None and a['native_closed'])
            observation,raw,received,provenance=_reply(plan,mode,req,reply,status,clock_basis);provenances.add(provenance)
            _need(_ns(sent)<=_ns(received));last_wall=_ns(received)
            validated=reply['validated_at']
            if validated is not None:
                _need(_day(validated)==p['session_date'] and last_wall<=_ns(validated));last_wall=_ns(validated);last_valid=validated
            else:_need(outcome=='TERMINAL' and reason=='REPLY_REFUSED')
        else:_need(outcome=='TERMINAL')
        if outcome=='SELECTED':
            _need(completed<deadline_ns)
            _need(reason is None and target is None and reply is not None and status==200 and reply['validated_at'] is not None and last_wall<=cutoff)
            token=_cursor(raw,mode,p['symbol']);_need(token is None or token not in tokens)
            observations.append(observation)
            result=qualify_market_inputs(plan,tuple(observations),as_of=received) if mode=='HISTORY' else qualify_action_inputs(prepare_action_query(plan),tuple(observations),as_of=received)
            aggregate=result.content
            selected.append(rid);records.append(dict(request=req,body_utf8=reply['body_utf8'],diagnostic=reply['diagnostic'],validated_at=reply['validated_at'],dispatched_at=sent))
            if offset<len(chain)-1:_need(token is not None)
            if token is not None:tokens.add(token)
            cursor=token;page+=1;ordinal=1;not_before=completed
        elif outcome=='RETRY':
            _need(reason is None and reply is not None and status!=200 and reply['validated_at'] is not None and last_wall<cutoff and a['native_closed'])
            decision=decide_read_retry(status_code=status,completed_attempts=ordinal,failed_at_ns=completed,now_ns=completed,deadline_ns=deadline_ns,retry_after=header)
            _need(decision.state=='WAITING' and type(target) is int and target==decision.not_before_ns and offset+1<8)
            not_before=target;ordinal+=1
        else:
            _need(type(reason) is str and reason in _TERMINAL and target is None and offset==len(chain)-1)
            if not a['native_closed']:_need(reason=='NATIVE_CLEANUP_UNVERIFIED')
            if reason in ('HTTP_STATUS_NOT_RETRYABLE','PAGE_ATTEMPT_LIMIT','TASK_DEADLINE','RETRY_EXCEEDS_DEADLINE'):
                _need(reply is not None and status!=200 and reply['validated_at'] is not None)
                decision=decide_read_retry(status_code=status,completed_attempts=ordinal,failed_at_ns=completed,now_ns=completed,deadline_ns=deadline_ns,retry_after=header)
                _need(decision.state=='TERMINAL' and decision.reason==reason)
            if reason=='TOTAL_ATTEMPT_LIMIT':_need(offset==7)
        last_mono=completed
    _need(selected_requests==selected and all(type(rid) is str for rid in selected_requests))
    return dict(records=records,aggregate=aggregate,validated_at=last_valid,next_cursor=cursor,
                native_provenance=next(iter(provenances)) if len(provenances)==1 else 'UNVERIFIED',
                last_outcome=None if not chain else chain[-1]['outcome'])