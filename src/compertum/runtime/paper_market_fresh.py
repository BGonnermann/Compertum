"""Execution-private fresh ASSET/QUOTE pair; no current data grant or trading authority."""
from dataclasses import dataclass
from datetime import datetime,timezone
import json,math,time
from uuid import uuid4
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier
from compertum.paper_market_inputs import OperationalMarketPlan,OperationalMarketRequest,MarketObservation,prepare_market_request,qualify_market_inputs,_ns,_day,_sha
from .errors import RuntimeRefused
from .service_budget import producer_permit,cancel_producer,bind_producer_permit
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import ProtectedPaperCredentials,open_paper_credentials
from .paper_market_collection import _scan_generated
from .paper_market_qualification import prepare_market_exchange,start_market_exchange,qualify_market_reply

_FACTORY=object();_INVALID=(ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,AttributeError,OverflowError)

def _need(value,code='PAPER_FRESH_INVALID'):
    if not value:raise RuntimeRefused(code)

def _utc():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PrivateFreshView:
    _pair:object
    def __init__(self,pair,*,_factory=None):
        _need(_factory is _FACTORY);object.__setattr__(self,'_pair',pair)
    def __repr__(self):return '<PrivateFreshInputs original data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_FRESH_SERIALIZATION_FORBIDDEN')
    @property
    def content(self):
        return self._capture()[0]
    def _capture(self):
        with _owner_scope(self._pair._lease):
            self._pair._context();_need(self._pair._view is self);return self._pair._capture_at_use()
    def to_payload(self):return json.loads(self.content)

class _MarketFresh:
    def __init__(self,lease,plan,protected,*,pair_id,_test_port=None,_test_clock=None,_test_monotonic=None):
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution')
            try:
                _need(not any(type(r) is _MarketFresh and not r._closed for r in state.resources),'PAPER_FRESH_CAPACITY')
                _need(type(plan) is OperationalMarketPlan and type(protected) is ProtectedPaperCredentials)
                plan=OperationalMarketPlan(plan.content);protected.__post_init__();p=plan.to_payload();identifier(pair_id)
                _need(p['project_id']==lease.project_id==protected.project_id and p['account_alias']==protected.account_alias)
                _need(_test_port is None or type(_test_port) is int and 1<=_test_port<=65535)
                _need(_test_port is not None or _test_clock is _test_monotonic is None)
                _need(_test_clock is None or callable(_test_clock));_need(_test_monotonic is None or callable(_test_monotonic))
                self._lease=lease;self._owner_state=state;self._plan=plan;self._protected=protected;self._pair_id=pair_id;self._port=_test_port
                self._clock=_test_clock or _utc;self._monotonic=_test_monotonic or time.monotonic
                self._credential_sha=_sha(protected.ciphertext);self._generation=lease.generation;self._instance=lease.identity.process_instance_id
                self._closed=False;self._state='READY';self._reason=None;self._pending=None;self._view=None;self._records=[];self._dispatch_times={};self._ids=set();self._attempts=0
                self._completed_timing=None
                self._real_started=time.monotonic();self._last_clock=p['created_at'];self._last_mono=None;self._start_mono=self._mono();self._started_at=self._stamp()
                self._validated_at=self._started_at;self._context_sha=self._binding()
                self._scan(dict(plan=p,pair_id=pair_id,purpose='OPERATIONAL_ONLY'));self._seal();state.resources.append(self)
            except _INVALID:raise RuntimeRefused('PAPER_FRESH_INVALID') from None
    def __repr__(self):return '<OwnedFreshInputs original data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_FRESH_SERIALIZATION_FORBIDDEN')
    def _binding(self):
        return _sha(canonical(dict(plan=self._plan.sha256,credential=self._credential_sha,pair=self._pair_id,port=self._port,
            generation=self._generation,instance=self._instance,started=self._started_at,mono=self._start_mono,real=self._real_started,clock=id(self._clock),monotonic=id(self._monotonic))))
    def _data_hash(self):
        return _sha(canonical(dict(state=self._state,reason=self._reason,attempts=self._attempts,ids=sorted(self._ids),dispatch=self._dispatch_times,
            records=[[_sha(req),_sha(raw),_sha(diag),at] for req,raw,diag,at in self._records],validated=self._validated_at,completion=self._completed_timing,
            pending=None if self._pending is None else _sha(self._pending._content))))
    def _state_hash(self):
        return _sha(canonical(dict(data=self._data_hash(),last_clock=self._last_clock,last_mono=self._last_mono)))
    def _seal(self):self._state_sha=self._state_hash()
    def _context(self):
        try:
            require_live_owner(self._lease,'execution');_need(not self._closed and self in self._owner_state.resources)
            self._plan.__post_init__();self._protected.__post_init__();p=self._plan.to_payload()
            _need(self._binding()==self._context_sha and _sha(self._protected.ciphertext)==self._credential_sha)
            _need(p['project_id']==self._lease.project_id==self._protected.project_id and p['account_alias']==self._protected.account_alias)
            _need(self._generation==self._lease.generation and self._instance==self._lease.identity.process_instance_id)
            _need(self._state_hash()==self._state_sha,'PAPER_FRESH_EVIDENCE_CHANGED')
        except _INVALID:raise RuntimeRefused('PAPER_FRESH_CONTEXT_CHANGED') from None
    def _scan(self,value):
        _need(len(canonical(value))<=524288,'PAPER_FRESH_RETENTION_LIMIT')
        with open_paper_credentials(self._lease,self._protected) as opened:_scan_generated(value,tuple(opened.headers().values()))
    def _stamp(self):
        at=self._clock();_need(_day(at)==self._plan.to_payload()['session_date'] and _ns(at)>=_ns(self._last_clock),'PAPER_FRESH_CLOCK_INVALID')
        self._last_clock=at;return at
    def _mono(self):
        value=self._monotonic();_need(type(value) in (int,float) and 0<=value<=10**12 and math.isfinite(value) and (self._last_mono is None or value>=self._last_mono),'PAPER_FRESH_CLOCK_INVALID')
        self._last_mono=value;return value
    def _remaining(self):
        at=self._stamp();budget=min(10,20-(self._mono()-self._start_mono),self._real_started+20-time.monotonic())
        _need(budget>0,'PAPER_FRESH_DEADLINE');return at,budget
    def _before_send(self,rid,deadline):
        self._context();at,_=self._remaining();_need(time.monotonic()<deadline,'PAPER_FRESH_DEADLINE');self._dispatch_times[rid]=at;self._seal()
    def _close_pending(self):
        if self._pending is not None:self._pending.close();self._pending=None
    def _finish(self,reason,state='INCOMPLETE'):
        cancel_producer(self)
        self._state=state;self._reason=reason
        try:self._close_pending()
        finally:self._seal()
    def dispatch(self):
        with _owner_scope(self._lease):
            self._context();_need(self._state=='READY' and self._pending is None,'PAPER_FRESH_NOT_READY')
            try:
                at,budget=self._remaining();_need(self._attempts<2)
                self._seal();permit=producer_permit(self)
                if permit is None:return 'WAITING'
                deadline=min(self._real_started+20,time.monotonic()+budget);rid=str(uuid4());identifier(rid);_need(rid not in self._ids)
                request=prepare_market_request(self._plan,operation=('ASSET','QUOTE')[self._attempts],request_id=rid,created_at=at)
                self._pending=prepare_market_exchange(self._lease,self._protected,request);self._attempts+=1;self._ids.add(rid);self._state='PENDING';self._seal()
                bind_producer_permit(self,permit)
                _,budget=self._remaining();deadline=min(deadline,time.monotonic()+budget);self._seal()
                start_market_exchange(self._pending,timeout=budget,_test_port=self._port,_deadline_at=deadline,_pre_send=lambda:self._before_send(rid,deadline),_permit=permit)
            except BaseException as error:
                self._finish('DISPATCH_FAILED')
                if isinstance(error,_INVALID):raise RuntimeRefused('PAPER_FRESH_DISPATCH_INVALID') from None
                raise
    def _observations(self,records=None):
        records=self._records if records is None else records
        return tuple(MarketObservation(OperationalMarketRequest(self._plan,req),raw,json.loads(diag)['status'],json.loads(diag)['received_at']) for req,raw,diag,_ in records)
    def _wire_records(self,records=None,dispatch=None):
        records=self._records if records is None else records;dispatch=self._dispatch_times if dispatch is None else dispatch
        return [dict(request=json.loads(req),body_utf8=raw.decode('utf-8'),diagnostic=json.loads(diag),dispatched_at=dispatch.get(json.loads(req)['request_id']),validated_at=at) for req,raw,diag,at in records]
    def poll(self):
        with _owner_scope(self._lease):
            self._context();_need(self._state=='PENDING' and self._pending is not None,'PAPER_FRESH_NO_PENDING')
            try:
                if self._mono()-self._start_mono>=20 or time.monotonic()>=self._real_started+20:self._finish('TOTAL_DEADLINE');return True
                result=self._pending._transport.poll()
                if result is None:self._seal();return False
                received=self._stamp();reply=qualify_market_reply(self._lease,self._protected,self._pending,result.body,status=result.status_code,received_at=received,result=result)
                self._records.append((self._pending.content,reply.raw,reply.content,None));self._close_pending()
                diagnostic=qualify_market_inputs(self._plan,self._observations(),as_of=received).to_payload()
                self._scan(dict(records=self._wire_records(),diagnostic=diagnostic))
                validated=self._stamp();self._validated_at=validated;self._records[-1]=(*self._records[-1][:3],validated)
                completed_mono=self._mono();completed_real=time.monotonic()
                if completed_mono-self._start_mono>=20 or completed_real>=self._real_started+20:self._finish('TOTAL_DEADLINE')
                elif result.status_code!=200:self._finish('HTTP_REFUSED')
                elif len(self._records)==2:
                    self._completed_timing=dict(monotonic_elapsed_seconds=completed_mono-self._start_mono,native_elapsed_seconds=completed_real-self._real_started)
                    self._finish(None,'PAIR_COMPLETE')
                else:self._state='READY';self._seal()
                return True
            except BaseException as error:
                self._finish('REPLY_REFUSED')
                if isinstance(error,(RuntimeRefused,*_INVALID)):return True
                raise
    def cancel(self):
        with _owner_scope(self._lease):
            self._context();_need(self._state in ('READY','PENDING'),'PAPER_FRESH_TERMINAL');self._finish('CANCELLED')
    def status(self):
        with _owner_scope(self._lease):
            self._context();v=dict(state=self._state,reason=self._reason,attempts=self._attempts,responses=len(self._records),purpose='OPERATIONAL_ONLY',financial_accepted=False,research_eligible=False)
            self._scan(v);return v
    def private_snapshot(self):
        with _owner_scope(self._lease):
            self._context();_need(self._state in ('PAIR_COMPLETE','INCOMPLETE') and self._pending is None,'PAPER_FRESH_NOT_TERMINAL')
            if self._view is None:self._view=_PrivateFreshView(self,_factory=_FACTORY)
            return self._view
    def _content_at_use(self):
        return self._capture_at_use()[0]
    def _capture_at_use(self):
        try:
            data_sha=self._data_hash();binding=self._binding();seal=self._state_sha
            records=tuple(self._records);dispatch=dict(self._dispatch_times)
            value=dict(version=1,record_type='PrivateFreshInputs',purpose='OPERATIONAL_ONLY',pair_id=self._pair_id,plan=self._plan.to_payload(),
                state=self._state,reason=self._reason,attempts=self._attempts,started_at=self._started_at,validated_at=self._validated_at,
                clock_basis='SYNTHETIC_FIXTURE' if self._port is not None else 'LOCAL_CLOCK',records=self._wire_records(records,dispatch),
                financial_accepted=False,transport_authorized=False,research_eligible=False)
            now=self._stamp();mono=self._mono();elapsed=mono-self._start_mono;wall_elapsed=(_ns(now)-_ns(self._started_at))/10**9
            _need(abs(wall_elapsed-elapsed)<=5,'PAPER_FRESH_CLOCK_INVALID')
            age_ns=max(_ns(now),_ns(self._started_at)+math.ceil(elapsed*10**9))
            seconds,nanos=divmod(age_ns,10**9)
            age_at=datetime.fromtimestamp(seconds,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')+f'.{nanos:09d}Z'
            _need(_day(age_at)==value['plan']['session_date'],'PAPER_FRESH_CLOCK_INVALID')
            diagnostic=None
            try:
                candidate=qualify_market_inputs(self._plan,self._observations(records),as_of=age_at).to_payload();self._scan(candidate);diagnostic=candidate
            except (RuntimeRefused,*_INVALID):pass
            value.update(observed_at=now,age_basis_at=age_at,age_basis='MAX_WALL_MONOTONIC',diagnostic=diagnostic,
                diagnostic_error='DIAGNOSTIC_UNVERIFIED' if diagnostic is None else None)
            self._scan(value)
            _need(self._binding()==binding and self._data_hash()==data_sha and self._state_sha==seal
                and self._last_clock==now and self._last_mono==mono,'PAPER_FRESH_EVIDENCE_CHANGED')
            content=canonical(value);self._seal()
            return content,dict(elapsed_seconds=elapsed,elapsed_ns=math.ceil(elapsed*10**9),completion=None if self._completed_timing is None else dict(self._completed_timing))
        except _INVALID:raise RuntimeRefused('PAPER_FRESH_INVALID') from None
    def close(self):
        with _MUTEX:
            cancel_producer(self)
            self._closed=True;self._records.clear();self._view=None;self._close_pending()
            if self in self._owner_state.resources:self._owner_state.resources.remove(self)
