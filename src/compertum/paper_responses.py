"""Bind retained synthetic paper replies to inert requests; never dispatch."""
from dataclasses import dataclass, field
from datetime import time
import hashlib
import json
import re

from .data.encoding import canonical
from .paper_contracts import (MAX_BYTES, PaperRequest, identifier, number, read_request,
                              require, session_date, strict_json, symbol, timestamp, utc)

ACCOUNT_STATES = ('ACCOUNT_UPDATED', 'APPROVAL_PENDING', 'APPROVED', 'REJECTED', 'SUBMITTED',
                  'SUBMISSION_FAILED', 'ACTION_REQUIRED', 'ACTIVE', 'DISABLED')
ORDER_STATES = ('new', 'partially_filled', 'filled', 'done_for_day', 'canceled', 'expired',
                'replaced', 'pending_cancel', 'pending_replace', 'pending_review', 'accepted',
                'pending_new', 'accepted_for_bidding', 'stopped', 'rejected', 'suspended', 'calculated')


def _fields(p, names):
    require(type(p) is dict and set(names) <= set(p))


def _account(p, request):
    names = ('id', 'status', 'currency', 'cash', 'equity', 'buying_power', 'trading_blocked',
             'account_blocked', 'trade_suspended_by_user')
    _fields(p, names)
    require(identifier(p['id']) == request['account_id'])
    require(type(p['status']) is str and p['status'] in ACCOUNT_STATES and p['currency'] == 'USD')
    for key in ('cash', 'equity', 'buying_power'):
        number(p[key])
    for key in ('trading_blocked', 'account_blocked', 'trade_suspended_by_user'):
        require(type(p[key]) is bool)
    return {key: p[key] for key in names}


def _clock(p):
    names = ('timestamp', 'is_open', 'next_open', 'next_close')
    _fields(p, names)
    require(type(p['is_open']) is bool)
    at, opened, closed = (timestamp(p[key]) for key in ('timestamp', 'next_open', 'next_close'))
    require(opened > at and closed > at)
    require(closed < opened if p['is_open'] else opened < closed)
    return {key: p[key] if key == 'is_open' else utc(p[key]) for key in names}


def _calendar(p, request):
    require(type(p) is list and len(p) <= 31)
    start = session_date(request['parameters']['start'])
    end = session_date(request['parameters']['end'])
    previous = None
    result = []
    for row in p:
        _fields(row, ('date', 'open', 'close'))
        day = session_date(row['date'])
        require(start <= day <= end and (previous is None or day > previous))
        for key in ('open', 'close'):
            require(type(row[key]) is str and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', row[key]) is not None)
        require(time.fromisoformat(row['open']) < time.fromisoformat(row['close']))
        result.append({key: row[key] for key in ('date', 'open', 'close')})
        previous = day
    return result


def _order(p, request):
    names = ('id', 'client_order_id', 'symbol', 'qty', 'filled_qty', 'filled_avg_price',
             'side', 'type', 'time_in_force', 'extended_hours', 'status', 'limit_price')
    _fields(p, names)
    identifier(p['id'])
    require(type(p['client_order_id']) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', p['client_order_id']) is not None)
    symbol(p['symbol'])
    qty, filled = number(p['qty'], positive=True), number(p['filled_qty'])
    require(qty == qty.to_integral_value() and filled == filled.to_integral_value() and 0 <= filled <= qty)
    require(p['side'] in ('buy', 'sell') and p['type'] in ('market', 'limit') and p['time_in_force'] == 'day')
    require(p['extended_hours'] is False and type(p['status']) is str and p['status'] in ORDER_STATES)
    if filled > 0:
        number(p['filled_avg_price'], positive=True)
    else:
        require(p['filled_avg_price'] is None)
    if p['status'] == 'filled':
        require(filled == qty)
    elif p['status'] == 'partially_filled':
        require(0 < filled < qty)
    elif p['status'] in ('new', 'pending_new', 'rejected', 'accepted', 'accepted_for_bidding'):
        require(filled == 0)
    if p['type'] == 'limit':
        number(p['limit_price'], positive=True)
    else:
        require(p['limit_price'] is None)
    operation = request['operation']
    if operation == 'ORDER_BY_ID':
        require(p['id'] == request['parameters']['order_id'])
    elif operation == 'ORDER_BY_CLIENT_ID':
        require(p['client_order_id'] == request['parameters']['client_order_id'])
    else:
        body = request['body']
        for key in ('client_order_id', 'symbol', 'side', 'type', 'time_in_force', 'extended_hours'):
            require(p[key] == body[key])
        require(qty == number(body['qty']))
        if body['type'] == 'limit':
            require(number(p['limit_price']) == number(body['limit_price']))
    return {key: p[key] for key in names}


def _response_payload(request, *, origin, account_id, status, raw, received_at):
    require(type(request) is PaperRequest)
    request = read_request(request.content)
    p = request.to_payload()
    require(type(origin) is str and origin == p['origin'] and identifier(account_id) == p['account_id'])
    require(type(raw) is bytes and len(raw) <= MAX_BYTES)
    require(status is None or (type(status) is int and 200 <= status <= 599 and not 300 <= status < 400))
    elapsed = timestamp(received_at) - timestamp(p['created_at'])
    require(elapsed.total_seconds() >= 0)
    age_us = (elapsed.days * 86400 + elapsed.seconds) * 1000000 + elapsed.microseconds
    observation = None
    outcome = 'UNCONFIRMED'
    if status is not None and status < 300:
        if p['operation'] == 'CANCEL_ORDER':
            require(status == 204 and raw == b'')
            outcome = 'CANCEL_REQUEST_ACCEPTED_UNCONFIRMED'
        else:
            require(status == 200)
            body = strict_json(raw)
            if p['operation'] == 'ACCOUNT':
                observation = _account(body, p)
            elif p['operation'] in ('POSITIONS', 'ORDERS'):
                from .paper_portfolio import parse_portfolio_rows
                observation = parse_portfolio_rows(body, p)
            elif p['operation'] == 'CLOCK':
                observation = _clock(body)
            elif p['operation'] == 'CALENDAR':
                observation = _calendar(body, p)
            else:
                observation = _order(body, p)
            outcome = 'SUCCESS_FIXTURE'
    return dict(version=1, record_type='PaperResponse', scope='PAPER_WIRE_FIXTURE',
                transport_authorized=False, financial_accepted=False, retry_authorized=False,
                account_binding='CALLER_CONTEXT_UNVERIFIED', calendar_admitted=False,
                request_sha256=request.sha256, request_id=p['request_id'], origin=origin,
                account_id=account_id, account_alias=p['account_alias'], operation=p['operation'],
                received_at=utc(received_at), age_since_request_creation_us=age_us,
                older_than_5s=age_us > 5000000, status=status, outcome=outcome,
                raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw), observation=observation)


@dataclass(frozen=True, slots=True)
class PaperResponse:
    request: PaperRequest
    origin: str
    account_id: str
    status: int | None
    raw: bytes
    received_at: str
    content: bytes = field(init=False)

    def __post_init__(self):
        p = _response_payload(self.request, origin=self.origin, account_id=self.account_id,
                              status=self.status, raw=self.raw, received_at=self.received_at)
        content = canonical(p)
        require(len(content) <= MAX_BYTES)
        object.__setattr__(self, 'content', content)

    def to_payload(self):
        return json.loads(self.content)


def parse_response(request: PaperRequest, *, origin, account_id, status: int | None, raw: bytes, received_at: str):
    return PaperResponse(request, origin, account_id, status, raw, received_at)
