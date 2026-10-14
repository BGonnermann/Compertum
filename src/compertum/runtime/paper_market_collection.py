"""Execution-private sequential history/action producer. No grants or publication."""
from dataclasses import dataclass
from datetime import datetime,timezone
import json,math,time
from uuid import uuid4
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier
from compertum.paper_market_inputs import (OperationalMarketPlan,OperationalMarketRequest,MarketObservation,prepare_market_request,
                                         qualify_market_inputs,_body,_day,_ns,_sha,_token)
from compertum.paper_action_inputs import prepare_action_query,CurrentActionPage,qualify_action_inputs
from .errors import RuntimeRefused
from .read_retry import decide_read_retry
from .paper_market_attempts import can_retain_attempt,retry_after_payload
from .service_budget import producer_permit,cancel_producer,bind_producer_permit
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import ProtectedPaperCredentials,open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from .paper_market_qualification import prepare_market_exchange,start_market_exchange,qualify_market_reply

_FACTORY=object()
_INVALID=(ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,AttributeError)


def _need(value,code='PAPER_COLLECTION_INVALID'):
    if not value:raise RuntimeRefused(code)


def _utc():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def _scan_generated(value,values):
    """Scan bounded generated JSON without widening the single-response parser.

    Each source body was already scanned before retention. Walk decoded output
    strings too; 512-character overlap exceeds every permitted encoded key token.
    """
    _need(len(canonical(value))<=2*1048576,'PAPER_COLLECTION_RETENTION_LIMIT')
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1;_need(depth<=40 and count<=100000)
        if type(item) is str:
            for offset in range(0,max(1,len(item)),2048):
                _reject_reflections(canonical(dict(value=item[offset:offset+2560])),values)
        elif type(item) is dict:
            pending.extend((x,depth+1) for x in item.keys());pending.extend((x,depth+1) for x in item.values())
        elif type(item) is list:pending.extend((x,depth+1) for x in item)


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PrivateCollectionSnapshot:
    _collection:object
    _content:bytes
    _sha256:str
    def __init__(self,collection=None,content=None,*,_factory=None):
        _need(_factory is _FACTORY)
        object.__setattr__(self,'_collection',collection);object.__setattr__(self,'_content',content);object.__setattr__(self,'_sha256',_sha(content))
    def __repr__(self):return '<PrivateOperationalCollection original data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_COLLECTION_SERIALIZATION_FORBIDDEN')
    @property
    def content(self):
        with _owner_scope(self._collection._lease):
            self._collection._context();_need(self._collection._snapshot is self and _sha(self._content)==self._sha256)
            return self._content
    def to_payload(self):return json.loads(self.content)


class _MarketCollection:
    def __init__(self,lease,plan,protected,*,collection_id,mode,_test_port=None,_test_clock=None,_test_monotonic=None):
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution')
            try:
                _need(not any(type(r) is _MarketCollection and not r._closed for r in state.resources),'PAPER_COLLECTION_CAPACITY')
                _need(type(plan) is OperationalMarketPlan and type(protected) is ProtectedPaperCredentials)
                plan=OperationalMarketPlan(plan.content);protected.__post_init__();p=plan.to_payload();identifier(collection_id)
                _need(type(mode) is str and mode in ('HISTORY','CURRENT_ACTIONS'))
                _need(p['project_id']==lease.project_id==protected.project_id and p['account_alias']==protected.account_alias)
                _need(_test_port is None or type(_test_port) is int and 1<=_test_port<=65535)
                _need(_test_port is not None or _test_clock is _test_monotonic is None)
                _need(_test_clock is None or callable(_test_clock));_need(_test_monotonic is None or callable(_test_monotonic))
                self._lease=lease;self._owner_state=state;self._plan=plan;self._protected=protected;self._collection_id=collection_id;self._mode=mode
                self._port=_test_port;self._clock=_test_clock or _utc;self._monotonic=_test_monotonic or time.monotonic
                self._credential_sha=_sha(protected.ciphertext);self._generation=lease.generation;self._instance=lease.identity.process_instance_id
                self._closed=False;self._state='READY';self._reason=None;self._pending=None;self._cleanup_pending=None
                self._records=[];self._aggregate=None;self._aggregate_error=None;self._snapshot=None;self._tokens=set();self._cursor=None;self._ids=set();self._attempts=0
                self._dispatch_times={};self._started_ns=time.monotonic_ns();self._real_started=self._started_ns/10**9
                self._last_retry_ns=self._started_ns;self._chain=[];self._selected=[];self._page=1;self._page_attempt=0;self._retry_target_ns=None;self._force_v2=False
                self._last_clock=p['created_at'];self._last_mono=None;self._start_mono=self._mono();self._started_at=self._stamp()
                _need(_ns(self._started_at)<_ns(p['history_cutoff_at']))
                self._deadline_ns=self._started_ns+min(80*10**9,_ns(p['history_cutoff_at'])-_ns(self._started_at))
                self._validated_at=self._started_at;self._complete_by_cutoff=False;self._context_sha=self._binding()
                with open_paper_credentials(lease,protected) as opened:
                    values=tuple(opened.headers().values());_reject_reflections(plan.content,values)
                    _reject_reflections(canonical(dict(collection_id=collection_id,mode=mode,purpose='OPERATIONAL_ONLY')),values)
                self._seal_state();state.resources.append(self)
            except _INVALID:raise RuntimeRefused('PAPER_COLLECTION_INVALID') from None

    def __repr__(self):return '<OwnedOperationalCollection private data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_COLLECTION_SERIALIZATION_FORBIDDEN')

    def _binding(self):
        return _sha(canonical(dict(plan=self._plan.sha256,credential=self._credential_sha,collection=self._collection_id,mode=self._mode,
                                  port=self._port,generation=self._generation,instance=self._instance,purpose='OPERATIONAL_ONLY',
                                  started_at=self._started_at,start_mono=self._start_mono,real_started=self._real_started,started_ns=self._started_ns,deadline_ns=self._deadline_ns)))

    def _context(self):
        try:
            require_live_owner(self._lease,'execution');_need(not self._closed and self in self._owner_state.resources)
            self._plan.__post_init__();self._protected.__post_init__();p=self._plan.to_payload()
            _need(self._binding()==self._context_sha and _sha(self._protected.ciphertext)==self._credential_sha)
            _need(p['project_id']==self._lease.project_id==self._protected.project_id and p['account_alias']==self._protected.account_alias)
            _need(self._generation==self._lease.generation and self._instance==self._lease.identity.process_instance_id)
            _need(self._state_hash()==self._state_sha,'PAPER_COLLECTION_EVIDENCE_CHANGED')
        except _INVALID:raise RuntimeRefused('PAPER_COLLECTION_CONTEXT_CHANGED') from None

    def _state_hash(self):
        records=[dict(request=_sha(req),body=_sha(raw),diagnostic=_sha(diag),validated_at=at) for req,raw,diag,at in self._records]
        return _sha(canonical(dict(records=records,aggregate=None if self._aggregate is None else _sha(self._aggregate),aggregate_error=self._aggregate_error,
            state=self._state,reason=self._reason,attempts=self._attempts,cursor=self._cursor,tokens=sorted(self._tokens),ids=sorted(self._ids),
            pending=None if self._pending is None else _sha(self._pending._content),cleanup_pending=None if self._cleanup_pending is None else id(self._cleanup_pending),validated_at=self._validated_at,
            complete_by_cutoff=self._complete_by_cutoff,dispatch_times=self._dispatch_times,chain=self._chain,selected=self._selected,
            page=self._page,page_attempt=self._page_attempt,retry_target_ns=self._retry_target_ns,force_v2=self._force_v2)))

    def _seal_state(self):self._state_sha=self._state_hash()

    def _retry_now(self):
        value=time.monotonic_ns()
        _need(type(value) is int and self._last_retry_ns<=value<=2**63-1,'PAPER_COLLECTION_CLOCK_INVALID')
        self._last_retry_ns=value;return value

    def _remaining(self):
        now=self._stamp();remaining=80-(self._mono()-self._start_mono)
        _need(remaining>0,'PAPER_COLLECTION_DEADLINE')
        until=(_ns(self._plan.to_payload()['history_cutoff_at'])-_ns(now))/10**9
        _need(until>0,'PAPER_COLLECTION_CUTOFF')
        real_remaining=(self._deadline_ns-self._retry_now())/10**9
        _need(real_remaining>0,'PAPER_COLLECTION_DEADLINE')
        return now,min(10,remaining,until,real_remaining)

    def _before_send(self,request_id,deadline):
        self._context();now,_=self._remaining()
        _need(time.monotonic()<deadline,'PAPER_COLLECTION_DEADLINE')
        self._dispatch_times[request_id]=now
        self._chain[-1]['pre_send_at']=now;self._chain[-1]['pre_send_monotonic_ns']=self._retry_now();self._seal_state()

    def _stamp(self):
        value=self._clock();p=self._plan.to_payload()
        _need(_day(value)==p['session_date'] and _ns(value)>=_ns(self._last_clock),'PAPER_COLLECTION_CLOCK_INVALID')
        self._last_clock=value;return value

    def _mono(self):
        value=self._monotonic()
        _need(type(value) in (int,float) and math.isfinite(value) and (self._last_mono is None or value>=self._last_mono),'PAPER_COLLECTION_CLOCK_INVALID')
        self._last_mono=value;return value

    def _close_pending(self):
        if self._pending is None:return True
        exchange=self._pending;error=None
        try:exchange.close()
        except RuntimeRefused as caught:error=caught
        facts=exchange._native_evidence();self._chain[-1].update(facts)
        self._chain[-1]['completed_monotonic_ns']=self._retry_now();self._pending=None
        if not facts['native_closed']:
            self._cleanup_pending=exchange;return False
        if error is not None:raise error
        return True

    def _finish(self,reason,state='INCOMPLETE'):
        cleanup=True
        try:cancel_producer(self)
        finally:
            try:cleanup=self._close_pending()
            finally:
                if not cleanup:reason='NATIVE_CLEANUP_UNVERIFIED';state='INCOMPLETE'
                self._state=state;self._reason=reason;self._complete_by_cutoff=False
                if self._chain and self._chain[-1]['outcome'] is None:
                    self._chain[-1].update(outcome='TERMINAL',terminal_reason=reason)
                    self._force_v2=True
                if not cleanup:
                    self._chain[-1].update(outcome='TERMINAL',terminal_reason=reason,retry_not_before_ns=None)
                    self._force_v2=True
                self._seal_state()

    def dispatch(self):
        with _owner_scope(self._lease):
            self._context();_need(self._state=='READY' and self._pending is None,'PAPER_COLLECTION_NOT_READY')
            try:
                now,budget=self._remaining();_need(self._attempts<8)
                if self._retry_target_ns is not None and self._retry_now()<self._retry_target_ns:return 'WAITING'
                _need(can_retain_attempt(self._plan,self._chain),'PAPER_COLLECTION_RETENTION_LIMIT')
                permit=producer_permit(self)
                if permit is None:return 'WAITING'
                native_deadline=min(self._deadline_ns/10**9,time.monotonic()+budget)
                request_id=str(uuid4());identifier(request_id);_need(request_id not in self._ids)
                if self._mode=='HISTORY':
                    req=prepare_market_request(self._plan,operation='HISTORY',request_id=request_id,created_at=now,page_token=self._cursor)
                    exchange=prepare_market_exchange(self._lease,self._protected,req)
                else:
                    exchange=prepare_market_exchange(self._lease,self._protected,prepare_action_query(self._plan),action_request_id=request_id,
                                                      action_requested_at=now,action_page_token=self._cursor)
                self._pending=exchange;self._attempts+=1;self._page_attempt+=1;self._ids.add(request_id);self._state='PENDING';self._retry_target_ns=None
                self._chain.append(dict(index=self._attempts,page=self._page,page_attempt=self._page_attempt,request=json.loads(exchange.content),
                    pre_send_at=None,pre_send_monotonic_ns=None,dispatch_committed_ns=None,completed_monotonic_ns=None,native_closed=False,
                    observed_status=None,reply=None,retry_after=None,outcome=None,terminal_reason=None,retry_not_before_ns=None))
                self._seal_state();bind_producer_permit(self,permit)
                _,budget=self._remaining();native_deadline=min(native_deadline,time.monotonic()+budget)
                start_market_exchange(exchange,timeout=budget,_test_port=self._port,_deadline_at=native_deadline,
                                      _pre_send=lambda:self._before_send(request_id,native_deadline),_permit=permit,_commit_deadline_ns=self._deadline_ns)
            except BaseException as error:
                reason={'PAPER_COLLECTION_CUTOFF':'INFORMATION_CUTOFF','PAPER_COLLECTION_DEADLINE':'TOTAL_DEADLINE',
                        'PAPER_COLLECTION_RETENTION_LIMIT':'RETENTION_LIMIT'}.get(getattr(error,'code',None),'DISPATCH_FAILED')
                self._force_v2=True;self._finish(reason)
                if isinstance(error,_INVALID):raise RuntimeRefused('PAPER_COLLECTION_DISPATCH_INVALID') from None
                raise

    def _observations(self):
        observations=[]
        for request,raw,diagnostic,_ in self._records:
            p=json.loads(request);d=json.loads(diagnostic)
            if self._mode=='HISTORY':observations.append(MarketObservation(OperationalMarketRequest(self._plan,request),raw,d['status'],d['received_at']))
            else:observations.append(CurrentActionPage(prepare_action_query(self._plan),p['request_id'],p['parameters'].get('page_token'),p['requested_at'],d['received_at'],d['status'],raw))
        return tuple(observations)

    def _page_cursor(self,raw):
        b=_body(raw);_need('next_page_token' in b)
        if self._mode=='HISTORY':
            groups=b.get('bars');_need(type(groups) is dict and set(groups)<=set([self._plan.to_payload()['symbol']]))
            rows=groups.get(self._plan.to_payload()['symbol'],[]);_need(type(rows) is list and len(rows)<=100)
        else:
            groups=b.get('corporate_actions');_need(type(groups) is dict and all(type(rows) is list for rows in groups.values()))
            _need(sum(map(len,groups.values()))<=100)
        token=_token(b['next_page_token']);_need(token is None or token not in self._tokens)
        return token

    def _wire_records(self,records=None):
        return [dict(request=json.loads(req),body_utf8=raw.decode('utf-8'),diagnostic=json.loads(diag),validated_at=at,dispatched_at=self._dispatch_times.get(json.loads(req)['request_id']))
                for req,raw,diag,at in (self._records if records is None else records)]

    def poll(self):
        with _owner_scope(self._lease):
            self._context();_need(self._state=='PENDING' and self._pending is not None,'PAPER_COLLECTION_NO_PENDING')
            try:
                if self._mono()-self._start_mono>=80 or self._retry_now()>=self._deadline_ns:self._finish('TOTAL_DEADLINE');return True
                result=self._pending._transport.poll()
                if result is None:return False
                received=self._stamp()
                reply=qualify_market_reply(self._lease,self._protected,self._pending,result.body,status=result.status_code,received_at=received,result=result)
                request=self._pending.content;raw=reply.raw;diagnostic=reply.content
                attempt=self._chain[-1]
                attempt['reply']=dict(body_utf8=raw.decode('utf-8'),diagnostic=json.loads(diagnostic),validated_at=None)
                candidate_header=retry_after_payload(result.retry_after)
                if not self._close_pending():
                    attempt.update(outcome='TERMINAL',terminal_reason='NATIVE_CLEANUP_UNVERIFIED');self._force_v2=True
                    self._finish('NATIVE_CLEANUP_UNVERIFIED');return True
                _need(len(canonical(dict(plan=self._plan.to_payload(),attempt_chain=self._chain)))<=1048576,'PAPER_COLLECTION_RETENTION_LIMIT')
                candidate=(request,raw,diagnostic,None);aggregate_candidate=None;token=None;page_ok=False
                if result.status_code==200:
                    try:
                        observations=list(self._observations());p=json.loads(request);d=json.loads(diagnostic)
                        if self._mode=='HISTORY':observations.append(MarketObservation(OperationalMarketRequest(self._plan,request),raw,d['status'],received))
                        else:observations.append(CurrentActionPage(prepare_action_query(self._plan),p['request_id'],p['parameters'].get('page_token'),p['requested_at'],received,d['status'],raw))
                        aggregate=qualify_market_inputs(self._plan,tuple(observations),as_of=received) if self._mode=='HISTORY' else qualify_action_inputs(prepare_action_query(self._plan),tuple(observations),as_of=received)
                        aggregate_candidate=aggregate.content;token=self._page_cursor(raw);page_ok=True
                    except (RuntimeRefused,*_INVALID):pass
                with open_paper_credentials(self._lease,self._protected) as opened:
                    values=tuple(opened.headers().values())
                    if aggregate_candidate is not None:_scan_generated(json.loads(aggregate_candidate),values)
                    _scan_generated(self._chain[:-1]+[dict(attempt,retry_after=candidate_header)],values)
                attempt['retry_after']=candidate_header
                validated=self._stamp();self._validated_at=validated;attempt['reply']['validated_at']=validated
                completed=self._retry_now();attempt['completed_monotonic_ns']=completed
                if self._mono()-self._start_mono>=80 or completed>=self._deadline_ns:reason='TOTAL_DEADLINE'
                elif _ns(validated)>_ns(self._plan.to_payload()['history_cutoff_at']):reason='INFORMATION_CUTOFF'
                elif result.status_code!=200:
                    self._force_v2=True
                    decision=decide_read_retry(status_code=result.status_code,completed_attempts=self._page_attempt,failed_at_ns=completed,
                        now_ns=completed,deadline_ns=self._deadline_ns,retry_after=result.retry_after)
                    if decision.state!='TERMINAL' and self._attempts<8:
                        attempt.update(outcome='RETRY',retry_not_before_ns=decision.not_before_ns)
                        self._retry_target_ns=decision.not_before_ns;self._state='READY';self._seal_state();return True
                    reason='HTTP_REFUSED' if decision.state=='TERMINAL' else 'PAGE_LIMIT'
                    attempt.update(outcome='TERMINAL',terminal_reason=decision.reason if decision.state=='TERMINAL' else 'TOTAL_ATTEMPT_LIMIT')
                elif not page_ok:reason='PAGE_INVALID'
                else:
                    attempt['outcome']='SELECTED';self._selected.append(json.loads(request)['request_id'])
                    self._records.append((*candidate[:3],validated));self._aggregate=aggregate_candidate;self._aggregate_error=None
                    self._page+=1;self._page_attempt=0
                    if token is None:
                        self._finish(None,'PAGINATION_COMPLETE');self._complete_by_cutoff=True
                    elif self._attempts>=8:self._finish('PAGE_LIMIT')
                    else:self._tokens.add(token);self._cursor=token;self._state='READY'
                    self._seal_state();return True
                self._force_v2=True
                if attempt['outcome'] is None:attempt.update(outcome='TERMINAL',terminal_reason=reason)
                self._finish(reason);return True
            except BaseException as error:
                self._force_v2=True;self._finish('REPLY_REFUSED')
                if isinstance(error,(RuntimeRefused,*_INVALID)):return True
                raise

    def cancel(self):
        with _owner_scope(self._lease):
            self._context();_need(self._state in ('READY','PENDING'),'PAPER_COLLECTION_TERMINAL');self._finish('CANCELLED')
            if self._cleanup_pending is not None:raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')

    def status(self):
        with _owner_scope(self._lease):
            self._context()
            value=dict(state=self._state,reason=self._reason,pages=len(self._records),attempts=self._attempts,purpose='OPERATIONAL_ONLY',financial_accepted=False,research_eligible=False)
            with open_paper_credentials(self._lease,self._protected) as opened:_reject_reflections(canonical(value),tuple(opened.headers().values()))
            return value

    def _snapshot_value(self):
        provenance={json.loads(r[2])['transport_provenance'] for r in self._records}
        common=dict(version=1,record_type='PrivateOperationalCollection',purpose='OPERATIONAL_ONLY',collection_id=self._collection_id,mode=self._mode,
            plan=self._plan.to_payload(),started_at=self._started_at,validated_at=self._validated_at,state=self._state,reason=self._reason,
            attempts=self._attempts,aggregate=None if self._aggregate is None else json.loads(self._aggregate),aggregate_error=self._aggregate_error,
            complete_by_cutoff=self._complete_by_cutoff,native_provenance=next(iter(provenance)) if len(provenance)==1 else 'UNVERIFIED',
            clock_basis='SYNTHETIC_FIXTURE' if self._port is not None else 'LOCAL_CLOCK',research_eligible=False,financial_accepted=False,transport_authorized=False)
        if self._force_v2:
            provenance={a['reply']['diagnostic']['transport_provenance'] for a in self._chain if a['reply'] is not None}
            common.update(version=2,attempt_chain=self._chain,selected_requests=self._selected,started_monotonic_ns=self._started_ns,deadline_monotonic_ns=self._deadline_ns,
                          native_provenance=next(iter(provenance)) if len(provenance)==1 else 'UNVERIFIED')
        else:common['records']=self._wire_records()
        return common

    def private_snapshot(self):
        with _owner_scope(self._lease):
            self._context();_need(self._state in ('PAGINATION_COMPLETE','INCOMPLETE') and self._pending is None,'PAPER_COLLECTION_NOT_TERMINAL')
            if self._snapshot is None:
                value=self._snapshot_value();content=canonical(value);_need(len(content)<=2*1048576,'PAPER_COLLECTION_RETENTION_LIMIT')
                with open_paper_credentials(self._lease,self._protected) as opened:_scan_generated(value,tuple(opened.headers().values()))
                self._snapshot=_PrivateCollectionSnapshot(self,content,_factory=_FACTORY)
            return self._snapshot

    def close(self):
        with _MUTEX:
            try:cancel_producer(self)
            finally:
                self._closed=True;self._complete_by_cutoff=False
                try:
                    if self._pending is not None:
                        self._cleanup_pending=self._pending;self._pending=None
                    if self._cleanup_pending is not None:
                        self._cleanup_pending.close();self._cleanup_pending=None
                finally:
                    self._pending=None
                    if self._snapshot is not None:object.__setattr__(self._snapshot,'_content',b'');self._snapshot=None
                    self._records.clear();self._chain.clear();self._selected.clear();self._aggregate=None
                    if not self._owner_state.closed and self in self._owner_state.resources:self._owner_state.resources.remove(self)
