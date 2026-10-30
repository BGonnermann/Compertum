"""Bounded Alpaca observations and exact split diagnostics, never strategy inputs.

The envelope retains original HTTP body text and binds each page to a frozen
request. Receipt metadata is caller-supplied evidence, not proof of historical
provider availability. Normalization uses declared split knowledge and leaves
coverage and financial acceptance unverified.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re

from .calendar import NY, _calendar, session_date, session_times, utc_time
from .encoding import canonical
from .errors import DataError
from .snapshot import MAX_INPUT, safe_text

HOST = 'https://data.alpaca.markets'
SYMBOLS = frozenset('AAPL MSFT AMZN GOOGL META NVDA JPM XOM JNJ PG UNH HD SPY'.split())
MAX_REQUESTS = 40
MAX_PAGES = 40
MAX_ROWS = 4096
PARAMS = frozenset('symbols start end timeframe adjustment feed asof sort currency limit'.split())
HASH = re.compile(r'[0-9a-f]{64}')
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}')
SYMBOL = re.compile(r'[A-Z]{1,5}(?:\.[A-Z])?')


def _fields(value, fields, code):
    if type(value) is not dict or set(value) != set(fields):
        raise DataError(code)


def _load(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DataError('DUPLICATE_KEY')
            result[key] = value
        return result

    def constant(_):
        raise DataError('INVALID_PROVIDER_NUMBER')

    def decimal_token(token):
        # Bound the token before Decimal construction; huge exponents can raise
        # InvalidOperation and behave differently under caller trap settings.
        if len(token) > 48 or not re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,3})?', token):
            raise DataError('INVALID_PROVIDER_NUMBER')
        return Decimal(token)

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_float=decimal_token,
                          parse_constant=constant)
    except DataError:
        raise
    except (ValueError, RecursionError):
        raise DataError('INVALID_JSON') from None


def _number(value, *, integer=False):
    if type(value) not in (int, Decimal):
        raise DataError('INVALID_PROVIDER_NUMBER')
    d = Decimal(value)
    if (not d.is_finite() or d < 0 or (not integer and d == 0)
            or len(d.as_tuple().digits) > 28 or d.as_tuple().exponent < -12
            or d.adjusted() > 15):
        raise DataError('INVALID_PROVIDER_NUMBER')
    if integer and (type(value) is not int or value > 10**16 - 1):
        raise DataError('INVALID_PROVIDER_NUMBER')
    return format(d, 'f')


def _development(value):
    if value.year >= 2024:
        raise DataError('PROTECTED_PROVIDER_DATE')


def _date(value):
    result = session_date(value)
    _development(result)
    return result


def _timestamp(value):
    result = utc_time(value)
    _development(result)
    return result


def _stamp(value):
    return value.isoformat().replace('+00:00', 'Z')


def _sessions(start, end):
    if end < start or (end - start).days > 366:
        raise DataError('PROVIDER_WINDOW')
    result = []
    for delta in range((end - start).days + 1):
        value = (start + timedelta(days=delta)).isoformat()
        try:
            if _calendar(start.year if value[:4] == str(start.year) else end.year).is_session(value):
                session_times(value)
                result.append(value)
        except (ValueError, OverflowError, KeyError):
            raise DataError('CALENDAR_UNAVAILABLE') from None
    return result


def _profile(params, universe: frozenset | None = SYMBOLS):
    _fields(params, PARAMS, 'PROVIDER_PROFILE')
    start = _timestamp(params['start'])
    end = _timestamp(params['end'])
    asof = _date(params['asof'])
    if (start > end or (end - start).total_seconds() > 367 * 86400
            or params['timeframe'] not in ('1Day', '1Min')
            or params['adjustment'] not in ('raw', 'split')
            or params['feed'] not in ('sip', 'iex')
            or params['sort'] != 'asc' or params['currency'] != 'USD'
            or type(params['limit']) is not int or not 1 <= params['limit'] <= 100
            or type(params['symbols']) is not str):
        raise DataError('PROVIDER_PROFILE')
    symbols = params['symbols'].split(',')
    if (not 1 <= len(symbols) <= 13 or len(set(symbols)) != len(symbols)
            or any((symbol not in universe) if universe is not None else not SYMBOL.fullmatch(symbol) for symbol in symbols)
            or asof < end.date()):
        raise DataError('PROVIDER_PROFILE')
    if params['timeframe'] == '1Day':
        expected = [datetime.combine(session_date(day), time(), NY).astimezone(timezone.utc)
                    for day in _sessions(start.date(), end.date())]
        expected = [stamp for stamp in expected if start <= stamp <= end]
    else:
        session = start.astimezone(NY).date().isoformat()
        times = session_times(session)
        if start not in (times.entry, times.close_reference) or end != start + timedelta(seconds=59):
            raise DataError('PROVIDER_MINUTE_WINDOW')
        expected = [start]
    if not expected:
        raise DataError('PROVIDER_WINDOW')
    return tuple(symbols), tuple(_stamp(stamp) for stamp in expected), start, end


@dataclass(frozen=True)
class ProviderBar:
    request_id: str
    symbol: str
    timestamp: str
    timeframe: str
    adjustment: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    trades: str
    vwap: str
    body_sha256: str


@dataclass(frozen=True)
class BarEvidence:
    content: bytes
    sha256: str
    feed: str
    rows: tuple[ProviderBar, ...]
    missing: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class SplitEvent:
    action_id: str
    symbol: str
    effective_session: str
    new_shares: int
    old_shares: int
    known_at: str | None
    lineage_sha256: str


@dataclass(frozen=True)
class NormalizedEvidence:
    content: bytes
    sha256: str


def read_bar_evidence(raw: bytes, universe: frozenset | None = SYMBOLS) -> BarEvidence:
    """Validate frozen request/page evidence; missing bars remain explicit.
    universe: the symbols a request may name. None accepts any ticker of the SYMBOL form (engine history markets)."""
    value = _load(safe_text(raw))
    _fields(value, ('schema_version', 'host', 'requests', 'pages'), 'PROVIDER_ENVELOPE')
    if value['host'] != HOST:
        raise DataError('PROVIDER_HOST')
    if value['schema_version'] != 'alpaca-bars-v1':
        raise DataError('SCHEMA_VERSION')
    requests, pages = value['requests'], value['pages']
    if (type(requests) is not list or not 1 <= len(requests) <= MAX_REQUESTS
            or type(pages) is not list or not 1 <= len(pages) <= MAX_PAGES):
        raise DataError('INPUT_BOUND')
    profiles = {}
    for request in requests:
        _fields(request, ('id', 'path', 'params'), 'PROVIDER_REQUEST')
        rid = request['id']
        if type(rid) is not str or not IDENTIFIER.fullmatch(rid) or rid in profiles:
            raise DataError('PROVIDER_REQUEST')
        if request['path'] != '/v2/stocks/bars':
            raise DataError('PROVIDER_PROFILE')
        profile = _profile(request['params'], universe)
        profiles[rid] = (request['params'], profile)
    if sum(len(profile[0]) * len(profile[1]) for _, profile in profiles.values()) > MAX_ROWS:
        raise DataError('INPUT_BOUND')
    feeds = {params['feed'] for params, _ in profiles.values()}
    if len(feeds) != 1:
        raise DataError('PROVIDER_MIXED_FEEDS')
    grouped = {rid: [] for rid in profiles}
    for page in pages:
        _fields(page, ('request_id', 'page', 'params', 'status', 'started_utc',
                       'received_utc', 'body_utf8', 'body_sha256'), 'PROVIDER_PAGE')
        rid = page['request_id']
        if type(rid) is not str or rid not in grouped:
            raise DataError('PROVIDER_REQUEST_BINDING')
        if type(page['page']) is not int or page['page'] != len(grouped[rid]):
            raise DataError('PROVIDER_PAGE_ORDER')
        grouped[rid].append(page)
    rows, missing, seen = [], [], set()
    for rid, (params, (symbols, expected, start, end)) in profiles.items():
        chain = grouped[rid]
        if not chain:
            raise DataError('PROVIDER_PAGINATION')
        token, tokens, observed, previous = None, set(), set(), None
        last_received = None
        for index, page in enumerate(chain):
            expected_params = dict(params)
            if token is not None:
                expected_params['page_token'] = token
            actual_params = page['params']
            if (type(actual_params) is not dict or set(actual_params) != set(expected_params)
                    or any(type(actual_params[key]) is not type(expected_params[key])
                           or actual_params[key] != expected_params[key] for key in expected_params)):
                raise DataError('PROVIDER_REQUEST_BINDING')
            if type(page['status']) is not int or page['status'] != 200:
                raise DataError('PROVIDER_STATUS')
            started, received = utc_time(page['started_utc']), utc_time(page['received_utc'])
            if received < started or started < end or (last_received and started < last_received):
                raise DataError('PROVIDER_TIMING')
            last_received = received
            if type(page['body_utf8']) is not str:
                raise DataError('PROVIDER_RESPONSE_FIELDS')
            try:
                body_bytes = page['body_utf8'].encode('utf-8')
            except UnicodeError:
                raise DataError('INVALID_ENCODING') from None
            if (type(page['body_sha256']) is not str or not HASH.fullmatch(page['body_sha256'])
                    or hashlib.sha256(body_bytes).hexdigest() != page['body_sha256']):
                raise DataError('PROVIDER_HASH')
            body = _load(safe_text(body_bytes))
            _fields(body, ('bars', 'next_page_token'), 'PROVIDER_RESPONSE_FIELDS')
            if type(body['bars']) is not dict or any(symbol not in symbols for symbol in body['bars']):
                raise DataError('PROVIDER_RESPONSE_FIELDS')
            page_count = 0
            # JSON object member order carries no meaning. Bar arrays and
            # linked pages must still follow the requested chronological order.
            for symbol in sorted(body['bars']):
                bars = body['bars'][symbol]
                if type(bars) is not list:
                    raise DataError('PROVIDER_RESPONSE_FIELDS')
                for bar in bars:
                    _fields(bar, ('t', 'o', 'h', 'l', 'c', 'v', 'n', 'vw'), 'PROVIDER_BAR_FIELDS')
                    timestamp = _timestamp(bar['t'])
                    stamp = _stamp(timestamp)
                    if stamp not in expected or not start <= timestamp <= end:
                        raise DataError('PROVIDER_BAR_TIME')
                    key = (symbol, params['timeframe'], params['adjustment'], stamp)
                    if key in seen:
                        raise DataError('DUPLICATE_PROVIDER_ROW')
                    order = (symbol, stamp)
                    if previous is not None and order <= previous:
                        raise DataError('PROVIDER_ROW_ORDER')
                    previous = order
                    seen.add(key)
                    observed.add((symbol, stamp))
                    numbers = {name: _number(bar[name], integer=name in ('v', 'n'))
                               for name in ('o', 'h', 'l', 'c', 'v', 'n', 'vw')}
                    o, h, lo, c = (Fraction(numbers[name]) for name in ('o', 'h', 'l', 'c'))
                    if not lo <= o <= h or not lo <= c <= h:
                        raise DataError('INVALID_OHLC')
                    rows.append(ProviderBar(rid, symbol, stamp, params['timeframe'],
                                params['adjustment'], numbers['o'], numbers['h'], numbers['l'],
                                numbers['c'], numbers['v'], numbers['n'], numbers['vw'], page['body_sha256']))
                    page_count += 1
                    if len(rows) > MAX_ROWS:
                        raise DataError('INPUT_BOUND')
            if page_count > params['limit']:
                raise DataError('PROVIDER_PAGE_BOUND')
            token = body['next_page_token']
            if token is not None:
                if (type(token) is not str or not 1 <= len(token) <= 2048
                        or not re.fullmatch(r'[A-Za-z0-9_+/=-]+', token) or token in tokens):
                    raise DataError('PROVIDER_PAGINATION')
                tokens.add(token)
            if (token is None) != (index == len(chain) - 1):
                raise DataError('PROVIDER_PAGINATION')
        missing.extend((rid, symbol, stamp) for symbol in sorted(symbols) for stamp in expected
                       if (symbol, stamp) not in observed)
    return BarEvidence(raw, hashlib.sha256(raw).hexdigest(), next(iter(feeds)),
                       tuple(rows), tuple(missing))


def _events(events):
    if type(events) is not tuple or len(events) > 256:
        raise DataError('INVALID_SPLIT_EVENT')
    ids, effective = set(), set()
    for event in events:
        if (type(event) is not SplitEvent or type(event.action_id) is not str
                or not IDENTIFIER.fullmatch(event.action_id) or type(event.symbol) is not str
                or event.symbol not in SYMBOLS or type(event.lineage_sha256) is not str
                or not HASH.fullmatch(event.lineage_sha256)
                or type(event.new_shares) is not int or type(event.old_shares) is not int
                or not 1 <= event.new_shares <= 1000000 or not 1 <= event.old_shares <= 1000000
                or event.new_shares == event.old_shares):
            raise DataError('INVALID_SPLIT_EVENT')
        session_times(event.effective_session)
        if event.known_at is not None:
            utc_time(event.known_at)
        key = (event.symbol, event.effective_session)
        if event.action_id in ids or key in effective:
            raise DataError('DUPLICATE_SPLIT_EVENT')
        ids.add(event.action_id)
        effective.add(key)
    return events


def normalize_splits(evidence: BarEvidence, symbol: str, start_session: str,
                     end_session: str, decision_at: str,
                     events: tuple[SplitEvent, ...]) -> NormalizedEvidence:
    """Scale raw daily bars to end-session units using exact declared factors.

    A required split with absent or future declared knowledge is refused. A
    later split is irrelevant to this window and cannot change its identity.
    Historical action coverage remains unverified even when all declared
    events pass these checks.
    """
    if type(evidence) is not BarEvidence:
        raise DataError('PROVIDER_EVIDENCE_CORRUPT')
    if read_bar_evidence(evidence.content) != evidence:
        raise DataError('PROVIDER_EVIDENCE_CORRUPT')
    if type(symbol) is not str or symbol not in SYMBOLS:
        raise DataError('PROVIDER_PROFILE')
    start, end = _date(start_session), _date(end_session)
    sessions = _sessions(start, end)
    session_times(start_session)
    last = session_times(end_session)
    cutoff = _timestamp(decision_at)
    if cutoff < last.close:
        raise DataError('NORMALIZATION_CUTOFF')
    used = tuple(sorted((event for event in _events(events)
                         if event.symbol == symbol and start_session < event.effective_session <= end_session),
                        key=lambda event: (event.effective_session, event.action_id)))
    if any(event.known_at is None or utc_time(event.known_at) > cutoff for event in used):
        raise DataError('ACTION_KNOWLEDGE_UNVERIFIED')
    bars = {bar.timestamp[:10]: bar for bar in evidence.rows
            if bar.symbol == symbol and bar.timeframe == '1Day' and bar.adjustment == 'raw'
            and start_session <= bar.timestamp[:10] <= end_session}
    if any(session not in bars for session in sessions):
        raise DataError('MISSING_PROVIDER_ROW')
    normalized = []
    for session in sessions:
        bar = bars[session]
        factor = Fraction(1)
        for event in used:
            if session < event.effective_session:
                factor *= Fraction(event.new_shares, event.old_shares)
        normalized.append({'session': session, 'symbol': symbol, 'factor': str(factor),
                           **{name: str(Fraction(getattr(bar, name)) / factor)
                              for name in ('open', 'high', 'low', 'close', 'vwap')},
                           'volume': str(Fraction(bar.volume) * factor),
                           'trades': bar.trades, 'source_body_sha256': bar.body_sha256})
    result = {'schema_version': 'alpaca-split-diagnostic-v1',
              'status': 'REAL_DATA_ENGINEERING_DIAGNOSTIC', 'financial_accepted': False,
              'action_coverage': 'UNVERIFIED_PROVIDER_COVERAGE',
              'historical_availability': 'UNVERIFIED', 'knowledge_basis': 'DECLARED_SOURCE_BOUND',
              'source_sha256': evidence.sha256, 'feed': evidence.feed,
              'start_session': start_session, 'end_session': end_session,
              'decision_at': _stamp(cutoff), 'events': [asdict(event) for event in used],
              'rows': normalized}
    content = canonical(result)
    if len(content) > MAX_INPUT:
        raise DataError('INPUT_BOUND')
    return NormalizedEvidence(content, hashlib.sha256(content).hexdigest())
