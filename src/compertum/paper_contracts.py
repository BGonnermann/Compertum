"""Inert, immutable paper wire fixtures. No transport or account authority."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from uuid import UUID

from .data.encoding import canonical
from .domain import ContractError

PAPER_ORIGIN = 'https://paper-api.alpaca.markets'
MAX_BYTES = 65536


def require(condition):
    if not condition:
        raise ContractError('INVALID_PAPER_FIXTURE')


def strict_json(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES)

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    def constant(value):
        raise ContractError('INVALID_PAPER_FIXTURE')

    def depth(value, level=0):
        require(level <= 32)
        if type(value) is dict:
            for item in value.values():
                depth(item, level + 1)
        elif type(value) is list:
            for item in value:
                depth(item, level + 1)
        elif type(value) is float:
            import math
            require(math.isfinite(value))

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        depth(value)
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ContractError('INVALID_PAPER_FIXTURE') from exc


def identifier(value):
    require(type(value) is str)
    try:
        parsed = UUID(value)
        require(str(parsed) == value and parsed.int != 0)
    except (ValueError, AttributeError) as exc:
        raise ContractError('INVALID_PAPER_FIXTURE') from exc
    return value


def timestamp(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)', value) is not None)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.utcoffset() is not None)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ContractError('INVALID_PAPER_FIXTURE') from exc


def utc(value):
    return timestamp(value).isoformat().replace('+00:00', 'Z')


def session_date(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d\d-\d\d', value) is not None)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError('INVALID_PAPER_FIXTURE') from exc


def number(value, *, positive=False):
    require(type(value) is str and len(value) <= 64 and re.fullmatch(r'-?(?:0|[1-9]\d*)(?:\.\d+)?', value) is not None)
    result = Decimal(value)
    require(result.is_finite() and (not positive or result > 0))
    return result


def client_id(value):
    require(type(value) is str and re.fullmatch(r'cmp-[A-Za-z0-9_-]{1,124}', value) is not None)
    return value


def symbol(value):
    require(type(value) is str and re.fullmatch(r'[A-Z][A-Z0-9.-]{0,11}', value) is not None)
    return value


def order_body(body):
    require(type(body) is dict)
    fields = {'symbol', 'qty', 'side', 'type', 'time_in_force', 'extended_hours', 'client_order_id'}
    require(body.get('type') in ('market', 'limit'))
    if body['type'] == 'limit':
        fields.add('limit_price')
    require(set(body) == fields)
    symbol(body['symbol'])
    require(type(body['qty']) is str and re.fullmatch(r'[1-9]\d{0,17}', body['qty']) is not None)
    require(body['side'] in ('buy', 'sell') and body['time_in_force'] == 'day' and body['extended_hours'] is False)
    client_id(body['client_order_id'])
    if body['type'] == 'limit':
        number(body['limit_price'], positive=True)
    body = body.copy()
    return body


def _payload(*, origin, account_alias, account_id, request_id, created_at, operation, parameters=None, body=None):
    require(type(origin) is str and origin == PAPER_ORIGIN)
    require(type(account_alias) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', account_alias) is not None)
    identifier(account_id)
    identifier(request_id)
    require(type(operation) is str)
    require(parameters is None or type(parameters) is dict)
    parameters = {} if parameters is None else parameters.copy()
    method = 'GET'
    query = {}
    if operation in ('ACCOUNT', 'CLOCK', 'POSITIONS'):
        require(not parameters)
        path = '/v2/' + operation.lower()
    elif operation == 'ORDERS':
        required = {'status', 'direction', 'nested', 'limit'}
        require(required <= set(parameters) <= required | {'after_order_id'})
        require(parameters['status'] == 'all' and parameters['direction'] == 'asc' and parameters['nested'] is False)
        require(type(parameters['limit']) is int and 1 <= parameters['limit'] <= 25)
        if 'after_order_id' in parameters:
            identifier(parameters['after_order_id'])
        path = '/v2/orders'
        query = parameters.copy()
    elif operation == 'CALENDAR':
        require(set(parameters) == {'start', 'end'})
        start, end = session_date(parameters['start']), session_date(parameters['end'])
        require(0 <= (end - start).days < 31)
        path = '/v2/calendar'
        query = parameters.copy()
    elif operation in ('ORDER_BY_ID', 'CANCEL_ORDER'):
        require(set(parameters) == {'order_id'})
        path = '/v2/orders/' + identifier(parameters['order_id'])
        if operation == 'CANCEL_ORDER':
            method = 'DELETE'
    elif operation == 'ORDER_BY_CLIENT_ID':
        require(set(parameters) == {'client_order_id'})
        client_id(parameters['client_order_id'])
        path = '/v2/orders:by_client_order_id'
        query = parameters.copy()
    elif operation == 'SUBMIT_ORDER':
        require(not parameters and type(body) is dict)
        body = order_body(body)
        method, path = 'POST', '/v2/orders'
    else:
        raise ContractError('INVALID_PAPER_FIXTURE')
    if operation != 'SUBMIT_ORDER':
        require(body is None)
    return dict(version=1, record_type='PaperRequest', scope='PAPER_WIRE_FIXTURE', transport_authorized=False,
                financial_accepted=False, account_binding='UNVERIFIED', origin=origin, account_alias=account_alias,
                account_id=account_id, request_id=request_id, created_at=utc(created_at), operation=operation,
                method=method, path=path, parameters=parameters, query=query, body=body)


@dataclass(frozen=True, slots=True)
class PaperRequest:
    content: bytes

    def __post_init__(self):
        p = strict_json(self.content)
        require(type(p) is dict)
        fields = ('origin', 'account_alias', 'account_id', 'request_id', 'created_at', 'operation', 'parameters', 'body')
        require(all(key in p for key in fields))
        expected = _payload(**{key: p[key] for key in fields})
        # Comparing canonical bytes also rejects bool/integer equality and extra fields.
        require(canonical(expected) == self.content)

    @property
    def sha256(self):
        return hashlib.sha256(self.content).hexdigest()

    def to_payload(self):
        return json.loads(self.content)


def build_request(*, origin, account_alias, account_id, request_id, created_at, operation, parameters=None, body=None):
    return PaperRequest(canonical(_payload(origin=origin, account_alias=account_alias, account_id=account_id,
                                          request_id=request_id, created_at=created_at, operation=operation,
                                          parameters=parameters, body=body)))


def read_request(content: bytes):
    return PaperRequest(content)
