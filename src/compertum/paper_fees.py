"""Bounded declared fee arithmetic; no actual billing or account authority."""
from dataclasses import dataclass, field
from decimal import Decimal, Context, localcontext, ROUND_CEILING, ROUND_HALF_UP, Inexact, Rounded
import hashlib
import json
import re
from urllib.parse import urlsplit

from .data.calendar import NY
from .data.encoding import canonical
from .domain import ContractError
from .execution_contracts import WATCHLIST
from .paper_contracts import identifier, session_date, strict_json, timestamp

_COMPONENTS = ('SEC', 'TAF', 'CAT', 'COMMISSION')
_UNITS = ('FILL', 'ORDER', 'ACCOUNT_DAY')
_CENT = Decimal('0.01')


def _need(value):
    if not value:
        raise ContractError('FEE_EVIDENCE_INVALID')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _keys(value, keys):
    _need(type(value) is dict and set(value) == set(keys.split()))


def _number(value, *, positive=False, cents=False):
    _need(type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,12})?', value) is not None)
    result = Decimal(value)
    _need(result <= 100000000 and (not positive or result > 0))
    if cents:
        _need(result.as_tuple().exponent >= -2)
    return result


def _date(value):
    parsed = session_date(value)
    _need(2000 <= parsed.year <= 2100)
    return parsed


def _time(value):
    _need(type(value) is str and value.endswith(('Z', '+00:00')))
    parsed = timestamp(value)
    _need(2000 <= parsed.year <= 2100)
    return parsed


@dataclass(frozen=True, slots=True)
class FeeSource:
    raw: bytes = field(repr=False)
    url: str
    media_type: str
    retrieved_at: str

    def __post_init__(self):
        _need(type(self.raw) is bytes and 0 < len(self.raw) <= 2 * 1024**2)
        _need(type(self.url) is str and len(self.url) <= 512 and re.fullmatch(r'[!-~]+', self.url) is not None)
        try:
            url = urlsplit(self.url)
            _need(url.scheme == 'https' and url.hostname and url.netloc == url.hostname and not url.query and not url.fragment)
        except ValueError:
            raise ContractError('FEE_EVIDENCE_INVALID') from None
        _need(self.media_type in ('application/pdf', 'text/html', 'text/plain') and type(self.media_type) is str)
        _time(self.retrieved_at)

    @property
    def body_sha256(self):
        return _sha(self.raw)

    def to_payload(self):
        return dict(body_sha256=self.body_sha256, bytes=len(self.raw), url=self.url,
                    media_type=self.media_type, retrieved_at=self.retrieved_at, provenance='UNVERIFIED_CAPTURE')

    @property
    def sha256(self):
        return _sha(canonical(self.to_payload()))


def _schedule(sources, content):
    _need(type(sources) is tuple and 1 <= len(sources) <= 4)
    for source in sources:
        _need(type(source) is FeeSource)
        source.__post_init__()
    hashes = sorted(source.sha256 for source in sources)
    _need(len(set(hashes)) == len(hashes))
    value = strict_json(content)
    _keys(value, 'version schedule_id source_sha256 declared_from declared_until currency product rules')
    _need(type(value['version']) is int and value['version'] == 1)
    identifier(value['schedule_id'])
    _need(value['source_sha256'] == hashes)
    _need(_date(value['declared_from']) < _date(value['declared_until']))
    _need(value['currency'] == 'USD' and value['product'] == 'NMS_EQUITY')
    rules = value['rules']
    _need(type(rules) is list and 1 <= len(rules) <= 4)
    seen = set()
    for rule in rules:
        _keys(rule, 'component charged_sides basis rate minimum cap limit_unit rounding_unit rounding')
        code = rule['component']
        _need(type(code) is str and code in _COMPONENTS and code not in seen)
        seen.add(code)
        sides = rule['charged_sides']
        _need(type(sides) is list and sides in (['BUY'], ['SELL'], ['BUY', 'SELL']))
        _need(rule['basis'] in ('SHARES', 'PRINCIPAL') and type(rule['basis']) is str)
        _need(rule['limit_unit'] in _UNITS and type(rule['limit_unit']) is str)
        _need(rule['rounding_unit'] in _UNITS and type(rule['rounding_unit']) is str)
        _need(_UNITS.index(rule['limit_unit']) <= _UNITS.index(rule['rounding_unit']))
        _need(rule['rounding'] in ('CEILING', 'HALF_UP') and type(rule['rounding']) is str)
        _number(rule['rate'])
        minimum = _number(rule['minimum'], cents=True)
        if rule['cap'] is not None:
            _need(_number(rule['cap'], cents=True) >= minimum)
    _need(canonical(value) == content)
    return value


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    sources: tuple[FeeSource, ...] = field(repr=False)
    content: bytes = field(repr=False)

    def __post_init__(self):
        _schedule(self.sources, self.content)

    def to_payload(self):
        return json.loads(self.content)

    @property
    def sha256(self):
        return _sha(self.content)


def _batch(content):
    value = strict_json(content)
    _keys(value, 'version project_id account_alias execution_date currency product executions')
    _need(type(value['version']) is int and value['version'] == 1)
    _need(type(value['project_id']) is str and re.fullmatch('[0-9a-f]{64}', value['project_id']) is not None)
    _need(type(value['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value['account_alias']) is not None)
    _date(value['execution_date'])
    _need(value['currency'] == 'USD' and value['product'] == 'NMS_EQUITY')
    executions = value['executions']
    _need(type(executions) is list and len(executions) <= 128)
    seen = set()
    orders = {}
    for execution in executions:
        _keys(execution, 'execution_id order_id symbol side executed_at quantity price')
        identifier(execution['execution_id'])
        identifier(execution['order_id'])
        _need(execution['execution_id'] not in seen)
        seen.add(execution['execution_id'])
        _need(type(execution['symbol']) is str and execution['symbol'] in (*WATCHLIST, 'SPY'))
        _need(type(execution['side']) is str and execution['side'] in ('BUY', 'SELL'))
        _need(_time(execution['executed_at']).astimezone(NY).date().isoformat() == value['execution_date'])
        _number(execution['quantity'], positive=True)
        _number(execution['price'], positive=True)
        identity = (execution['symbol'], execution['side'])
        _need(orders.setdefault(execution['order_id'], identity) == identity)
    _need(canonical(value) == content)
    return value


@dataclass(frozen=True, slots=True)
class FeeBatch:
    content: bytes = field(repr=False)

    def __post_init__(self):
        _batch(self.content)

    def to_payload(self):
        return json.loads(self.content)

    @property
    def sha256(self):
        return _sha(self.content)


def _decimal_text(value):
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _group_key(execution, unit):
    return execution['execution_id'] if unit == 'FILL' else execution['order_id'] if unit == 'ORDER' else 'ACCOUNT_DAY'


def _calculate_component(executions, rule):
    limits = {}
    for execution in executions:
        if execution['side'] not in rule['charged_sides']:
            continue
        key = _group_key(execution, rule['limit_unit'])
        group = limits.setdefault(key, dict(quantity=Decimal(0), principal=Decimal(0), execution_ids=[],
                                            rounding_key=_group_key(execution, rule['rounding_unit'])))
        quantity = Decimal(execution['quantity'])
        group['quantity'] += quantity
        group['principal'] += quantity * Decimal(execution['price'])
        group['execution_ids'].append(execution['execution_id'])
    limit_output = []
    rounded_groups = {}
    for key, group in sorted(limits.items()):
        base = group['quantity'] if rule['basis'] == 'SHARES' else group['principal']
        raw = base * Decimal(rule['rate'])
        limited = max(Decimal(rule['minimum']), raw)
        if rule['cap'] is not None:
            limited = min(Decimal(rule['cap']), limited)
        limit_output.append(dict(group_id=key, execution_ids=sorted(group['execution_ids']),
                                 quantity=_decimal_text(group['quantity']), principal=_decimal_text(group['principal']),
                                 raw_fee=_decimal_text(raw), limited_fee=_decimal_text(limited)))
        rounding = rounded_groups.setdefault(group['rounding_key'], dict(quantity=Decimal(0), principal=Decimal(0),
                                  raw_fee=Decimal(0), limited_fee=Decimal(0), execution_ids=[], limit_group_ids=[]))
        for field in ('quantity', 'principal'):
            rounding[field] += group[field]
        rounding['raw_fee'] += raw
        rounding['limited_fee'] += limited
        rounding['execution_ids'].extend(group['execution_ids'])
        rounding['limit_group_ids'].append(key)
    output = []
    total = Decimal(0)
    for key, group in sorted(rounded_groups.items()):
        # Round once after summing limited fees; never per fill by accident.
        with localcontext(Context(prec=80)) as context:
            context.traps[Inexact] = False
            context.traps[Rounded] = False
            fee = group['limited_fee'].quantize(_CENT, rounding=ROUND_CEILING if rule['rounding'] == 'CEILING' else ROUND_HALF_UP)
        total += fee
        output.append(dict(group_id=key, execution_ids=sorted(group['execution_ids']), limit_group_ids=sorted(group['limit_group_ids']),
                           **{field:_decimal_text(group[field]) for field in ('quantity', 'principal', 'raw_fee', 'limited_fee')}, fee=format(fee, '.2f')))
    return dict(declared_fee=format(total, '.2f'), limit_groups=limit_output, groups=output)


def _calculation(batch, schedules):
    _need(type(batch) is FeeBatch)
    b = _batch(batch.content)
    _need(type(schedules) is tuple and len(schedules) <= 8)
    for schedule in schedules:
        _need(type(schedule) is FeeSchedule)
        schedule.__post_init__()
    sources = {source.sha256:source for schedule in schedules for source in schedule.sources}
    _need(sum(len(source.raw) for source in sources.values()) <= 8 * 1024**2)
    hashes = sorted(schedule.sha256 for schedule in schedules)
    _need(len(set(hashes)) == len(hashes))
    ids = [schedule.to_payload()['schedule_id'] for schedule in schedules]
    _need(len(set(ids)) == len(ids))
    effective = []
    for schedule in schedules:
        value = schedule.to_payload()
        if value['declared_from'] <= b['execution_date'] < value['declared_until']:
            effective.extend((schedule.sha256, rule) for rule in value['rules'])
    components = []
    with localcontext(Context(prec=80)) as context:
        context.traps[Inexact] = True
        total = Decimal(0)
        complete = True
        for code in _COMPONENTS:
            matches = [(sha, rule) for sha, rule in effective if rule['component'] == code]
            if len(matches) != 1:
                complete = False
                components.append(dict(component=code, status='MISSING_EFFECTIVE_RULE' if not matches else 'AMBIGUOUS_EFFECTIVE_RULE', declared_fee=None, groups=[]))
                continue
            sha, rule = matches[0]
            calculation = _calculate_component(b['executions'], rule)
            total += Decimal(calculation['declared_fee'])
            components.append(dict(component=code, status='DECLARED_BATCH_CALCULATED', schedule_sha256=sha, rule=rule, **calculation))
        declared_total = format(total, '.2f') if complete else None
    return dict(version=1, record_type='FeeCalculation', scope='DECLARED_SCENARIO_ONLY', status='BLOCKED', batch_sha256=batch.sha256,
                schedule_sha256=hashes, project_id=b['project_id'], account_alias=b['account_alias'], execution_date=b['execution_date'],
                currency='USD', product='NMS_EQUITY', calculation_status='DECLARED_BATCH_CALCULATED' if complete else 'INCOMPLETE_DECLARATIONS',
                declared_batch_fee=declared_total, components=components, source_interpretation='UNVERIFIED', effective_interval='DECLARED_NOT_VERIFIED',
                account_applicability='UNVERIFIED', execution_provenance='UNVERIFIED', daily_fill_completeness='UNVERIFIED', order_lifetime_completeness='UNVERIFIED', trade_to_order_mapping='DECLARED_NOT_VERIFIED', actual_billed_fee=None,
                financial_accepted=False, transport_authorized=False)


@dataclass(frozen=True, slots=True)
class FeeCalculation:
    batch: FeeBatch = field(repr=False)
    schedules: tuple[FeeSchedule, ...] = field(repr=False)
    content: bytes = field(repr=False)

    def __post_init__(self):
        _need(type(self.content) is bytes and 0 < len(self.content) <= 1024**2)
        _need(canonical(_calculation(self.batch, self.schedules)) == self.content)

    @property
    def sha256(self):
        return _sha(self.content)


def calculate_fees(batch, schedules):
    value = _calculation(batch, schedules)
    ordered = tuple(sorted(schedules, key=lambda schedule: schedule.sha256))
    return FeeCalculation(batch, ordered, canonical(value))
