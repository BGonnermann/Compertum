"""Bounded execution-owned read sequencing; no transport or approval grant."""
import hashlib
import json
import re
import time
from time import monotonic_ns as _real_ns
from zoneinfo import ZoneInfo
from compertum.domain import ContractError
from compertum.paper_contracts import identifier,number,timestamp,utc
from compertum.paper_read_preparation import PreparedReadPlan,prepare_read_request
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import ProtectedPaperCredentials
from .paper_read_secrecy import qualify_read_reply


def _nanoseconds(value):
    parsed=timestamp(value)
    fraction=re.search(r'\.(\d+)(?:Z|[+-])',value)
    digits=int(fraction.group(1).ljust(9,'0')) if fraction else 0
    seconds=parsed.toordinal()*86400+parsed.hour*3600+parsed.minute*60+parsed.second
    return seconds*1000000000+digits


def _local_time(value):
    parsed=timestamp(value)
    fraction=re.search(r'\.(\d+)(?:Z|[+-])',value)
    if fraction and len(fraction.group(1))>6:raise ContractError('LOCAL_CLOCK_PRECISION_UNSUPPORTED')
    return parsed


class _ReadPacket:
    def __init__(self,lease,plan,protected,*,started_at):
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution')
            if any(isinstance(r,_ReadPacket) and not r._closed for r in state.resources):raise RuntimeRefused('PAPER_PACKET_CAPACITY')
            try:
                if type(plan) is not PreparedReadPlan or type(protected) is not ProtectedPaperCredentials:raise ContractError('INVALID_PACKET')
                plan=PreparedReadPlan(plan.content);protected.__post_init__();p=plan.to_payload();started=_local_time(started_at)
                if (p['project_id']!=state.project.project_id or protected.project_id!=state.project.project_id or protected.account_alias!=p['account_alias']
                        or not timestamp(p['created_at'])<=started<timestamp(p['start_expires_at'])
                        or started.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=p['session_date']):raise ContractError('INVALID_PACKET')
            except (ContractError,ValueError,TypeError):raise RuntimeRefused('PAPER_PACKET_CONTEXT_INVALID') from None
            self._lease=lease;self._owner_state=state;self._plan=plan;self._plan_sha=plan.sha256
            self._protected=protected;self._credential_sha=hashlib.sha256(protected.ciphertext).hexdigest()
            self._started_at=utc(started_at);self._started_real_ns=_real_ns();self._started_mono=time.monotonic();self._last_received=started;self._last_received_ns=_nanoseconds(started_at)
            self._alias=p['account_alias'];self._closed=False;self._state='READY';self._reason=None
            self._pending=None;self._account_id=None;self._records=[];self._request_ids=set();self._attempts=0
            self._next='ACCOUNT';self._pages=0;self._cursor=None;self._order_ids=set();self._client_ids=set();self._last_submission=None
            self._orders=0;self._positions=0;self._deficiencies=[];self._coverage='INCOMPLETE';self._initial_clock=False
            state.resources.append(self)

    def __repr__(self):return '<PaperReadPacket private context redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_READ_PRIVATE_SERIALIZATION_FORBIDDEN')

    def _abort(self,reason):
        self._state='ABORTED';self._reason=reason;self._pending=None

    def _context(self):
        if (self._protected is None or self._plan.sha256!=self._plan_sha
                or hashlib.sha256(self._protected.ciphertext).hexdigest()!=self._credential_sha):
            self._abort('PRIVATE_CONTEXT_CHANGED');raise RuntimeRefused('PAPER_PACKET_CONTEXT_INVALID')

    def _deadline(self):
        elapsed=time.monotonic()-self._started_mono
        if not 0<=elapsed<30 or not 0<=_real_ns()-self._started_real_ns<30*10**9:
            self._abort('PACKET_DEADLINE');raise RuntimeRefused('PAPER_PACKET_DEADLINE')
        return 30-elapsed

    def remaining_seconds(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            if self._closed or self._state not in ('READY','PENDING'):raise RuntimeRefused('PAPER_PACKET_TERMINAL')
            self._context();return self._deadline()

    def issue(self,*,now,request_id):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            if self._closed or self._state not in ('READY','PENDING'):raise RuntimeRefused('PAPER_PACKET_TERMINAL')
            if self._pending is not None:raise RuntimeRefused('PAPER_PACKET_PENDING')
            self._context();self._deadline()
            try:
                if self._attempts>=13 or request_id in self._request_ids or _local_time(now)<self._last_received:raise ContractError('INVALID_PACKET')
                request=prepare_read_request(self._plan,request_id=request_id,operation=self._next,created_at=now,packet_started_at=self._started_at,
                    expected_account_id=self._account_id,credential_sha256=self._credential_sha,after_order_id=self._cursor if self._next=='ORDERS' else None)
            except (ContractError,ValueError,TypeError):
                self._abort('DISPATCH_CONTEXT_INVALID');raise RuntimeRefused('PAPER_PACKET_DISPATCH_INVALID') from None
            self._deadline();self._attempts+=1;self._request_ids.add(request_id);self._pending=request;self._state='PENDING'
            return request

    def fail_pending(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            if self._closed or self._pending is None:raise RuntimeRefused('PAPER_PACKET_NO_PENDING_READ')
            self._abort('READ_ATTEMPT_FAILED')

    def accept(self,raw,*,received_at):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            if self._closed or self._pending is None:raise RuntimeRefused('PAPER_PACKET_NO_PENDING_READ')
            self._context();self._deadline()
            request=self._pending
            try:
                _local_time(received_at)
                parsed=qualify_read_reply(self._lease,self._protected,request,raw,received_at=received_at)
            except (ContractError,ValueError,TypeError):
                self._abort('REPLY_INVALID');raise RuntimeRefused('PAPER_PACKET_REPLY_INVALID') from None
            except RuntimeRefused:
                self._abort('REPLY_INVALID');raise
            self._deadline();p=parsed.to_payload();observation=p['observation'];op=p['operation']
            self._records.append(parsed);self._pending=None;self._last_received=timestamp(received_at);self._last_received_ns=_nanoseconds(received_at);self._state='READY'
            if op=='ACCOUNT':
                self._account_id=parsed.private_account_id;self._next='CLOCK'
                if observation['status']!='ACTIVE' or any(observation[k] for k in ('trading_blocked','account_blocked','trade_suspended_by_user')):self._deficiencies.append('ACCOUNT_BLOCKED')
                if number(observation['cash'])<0:self._deficiencies.append('NEGATIVE_ACCOUNT_CASH')
            elif op=='CLOCK':
                age=self._last_received_ns-_nanoseconds(json.loads(parsed.raw)['timestamp'])
                if not self._initial_clock:
                    self._initial_clock=True;self._next='CALENDAR'
                    if not 0<=age<=5000000000:self._incomplete('INITIAL_CLOCK_INVALID')
                else:
                    self._state='PREPARATION_COMPLETE';self._next=None
                    if not 0<=age<=5000000000:self._incomplete('FINAL_CLOCK_INVALID')
            elif op=='CALENDAR':
                if not observation:self._deficiencies.append('NO_CALENDAR_SESSION')
                self._next='POSITIONS'
            elif op=='POSITIONS':
                self._positions=len(observation['rows']);self._deficiencies.extend('POSITIONS_'+s for s in observation['deficiencies']);self._next='ORDERS'
            elif op=='ORDERS':self._orders_page(observation)
            self._deadline()

    def _incomplete(self,reason):
        self._state='INCOMPLETE';self._reason=reason;self._next=None

    def _orders_page(self,observation):
        rows=observation['rows'];self._pages+=1;self._orders+=len(rows)
        self._deficiencies.extend('ORDERS_'+s for s in observation['deficiencies'])
        try:
            if len(rows)>25:raise ContractError('INVALID_PACKET')
            for row in rows:
                order_id=identifier(row['id']);client_id=row['client_order_id'];submitted=_nanoseconds(row['submitted_at'])
                if (order_id in self._order_ids or (client_id is not None and client_id in self._client_ids)
                        or submitted>self._last_received_ns or (self._last_submission is not None and submitted<self._last_submission)):raise ContractError('INVALID_PACKET')
                self._order_ids.add(order_id)
                if client_id is not None:self._client_ids.add(client_id)
                self._last_submission=submitted
        except (ContractError,ValueError,TypeError):
            self._incomplete('ORDER_COVERAGE_INVALID');return
        if len(rows)<25:
            self._coverage='OBSERVED_SHORT_TERMINAL_PAGE';self._next='CLOCK'
        elif self._pages>=8:self._incomplete('ORDER_PAGE_LIMIT')
        else:self._cursor=rows[-1]['id'];self._next='ORDERS'

    def status(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            return dict(version=1,record_type='PaperReadPacketStatus',scope='PREPARATION_ONLY',state=self._state,reason=self._reason,
                account_alias=self._alias,plan_sha256=self._plan_sha,attempts=self._attempts,responses=len(self._records),order_pages=self._pages,
                positions=self._positions,orders=self._orders,orders_coverage=self._coverage,deficiencies=list(self._deficiencies),
                references=[dict(request_id=r.to_payload()['request_id'],request_sha256=r.to_payload()['request_sha256'],raw_sha256=r.to_payload()['raw_sha256']) for r in self._records],
                native_transport_verified=False,financial_accepted=False,actual_flat=None,account_identity='DISCOVERED_UNCONFIRMED' if self._account_id else 'UNKNOWN')

    def private_evidence(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution');return tuple(self._records)

    def finish_failed(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            if self._closed or self._state not in ('READY','PENDING'):raise RuntimeRefused('PAPER_PACKET_TERMINAL')
            self._abort('READ_ATTEMPT_FAILED')

    def cancel(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            if self._closed or self._state not in ('READY','PENDING'):raise RuntimeRefused('PAPER_PACKET_TERMINAL')
            self._abort('OPERATOR_CANCELED');self._clear_private()

    def _clear_private(self):
        self._pending=None;self._records.clear();self._account_id=None;self._protected=None
        self._cursor=None;self._order_ids.clear();self._client_ids.clear();self._last_submission=None

    def close(self):
        # Owner disposal revokes first. Serialize cleanup without requiring life.
        with _MUTEX:
            if self._closed:return
            self._closed=True;self._clear_private()
            if self._state in ('READY','PENDING'):self._abort('OWNER_RELEASED')
            if not self._owner_state.closed and self in self._owner_state.resources:self._owner_state.resources.remove(self)

