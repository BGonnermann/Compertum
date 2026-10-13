"""Immutable corporate-action observations and declared-source reconciliation.

These diagnostics never establish inventory completeness, historical provider
availability or financial admission. Tickers alone cannot establish identity.
"""
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from fractions import Fraction
import hashlib
import re

from .alpaca import HOST, HASH, IDENTIFIER, MAX_PAGES, MAX_REQUESTS, MAX_ROWS, SYMBOLS, _fields, _load, _number
from .calendar import session_date, utc_time
from .encoding import canonical
from .errors import DataError
from .snapshot import safe_text

PARAMS = frozenset('symbols start end limit sort data_quality region'.split())
TICKER = re.compile(r'[A-Z][A-Z0-9.\-]{0,15}')
CUSIP = re.compile(r'[A-Z0-9*@#]{9}')
BASE = frozenset(('id', 'process_date'))
SCHEMAS = {
    'cash_dividends': BASE | set('symbol cusip ex_date record_date payable_date rate foreign special'.split()),
    'forward_splits': BASE | set('symbol cusip ex_date record_date payable_date due_bill_redemption_date old_rate new_rate'.split()),
    'name_changes': BASE | set('old_symbol new_symbol old_cusip new_cusip'.split()),
    'cash_mergers': BASE | set('acquiree_symbol acquirer_symbol acquiree_cusip acquirer_cusip effective_date payable_date rate'.split()),
    'stock_mergers': BASE | set('acquiree_symbol acquirer_symbol acquiree_cusip acquirer_cusip effective_date payable_date acquiree_rate acquirer_rate'.split()),
}


@dataclass(frozen=True)
class ActionParty:
    role: str
    symbol: str
    cusip: str | None


@dataclass(frozen=True)
class ProviderAction:
    id: str
    kind: str
    process_date: str
    economic_date: str | None
    parties: tuple[ActionParty, ...]
    issues: tuple[str, ...]
    fields: bytes
    request_id: str
    body_sha256: str


@dataclass(frozen=True)
class ActionEvidence:
    content: bytes
    sha256: str
    actions: tuple[ProviderAction, ...]


@dataclass(frozen=True)
class DeclaredIdentity:
    symbol: str
    cusip: str
    aliases: tuple[str, ...]
    lineage_sha256: str


@dataclass(frozen=True)
class DividendObservation:
    symbol: str
    cusip: str | None
    ex_date: str
    amount: str
    record_date: str | None
    payable_date: str | None
    publication_bound: str | None
    lineage_sha256: str


@dataclass(frozen=True)
class ActionDiagnostic:
    content: bytes
    sha256: str


def _matches(pattern, value):
    return type(value) is str and pattern.fullmatch(value) is not None


def _profile(params):
    _fields(params, PARAMS, 'ACTION_PROFILE')
    start, end = session_date(params['start']), session_date(params['end'])
    if not 2016 <= start.year <= 2023 or not 2016 <= end.year <= 2023:
        raise DataError('PROTECTED_ACTION_DATE')
    if (start > end or start.year != end.year or params['sort'] != 'asc'
            or params['data_quality'] != 'all' or params['region'] != 'us'
            or type(params['limit']) is not int or not 1 <= params['limit'] <= 100
            or type(params['symbols']) is not str):
        raise DataError('ACTION_PROFILE')
    symbols = params['symbols'].split(',')
    if (not 1 <= len(symbols) <= 14 or len(set(symbols)) != len(symbols)
            or any(s not in SYMBOLS | {'FB'} for s in symbols)):
        raise DataError('ACTION_PROFILE')
    return frozenset(symbols), start, end


def _plain(value, depth=0):
    if depth > 16:
        raise DataError('INPUT_BOUND')
    if type(value) is Decimal:
        return _number(value)
    if type(value) is dict:
        return {k: _plain(v, depth + 1) for k, v in value.items()}
    if type(value) is list:
        return [_plain(v, depth + 1) for v in value]
    return value


def _action(record, kind, rid, body_hash, profile):
    if type(record) is not dict or not BASE <= record.keys() or not _matches(IDENTIFIER, record['id']):
        raise DataError('ACTION_FIELDS')
    symbols, start, end = profile
    process = session_date(record['process_date'])
    if not start <= process <= end:
        raise DataError('ACTION_PROCESS_WINDOW')
    issues = ['ACTION_KNOWLEDGE_UNVERIFIED']
    if kind not in SCHEMAS:
        issues.append('UNSUPPORTED_ACTION_TYPE')
    elif record.keys() - SCHEMAS[kind]:
        issues.append('UNRECOGNIZED_ACTION_FIELDS')
    parties = []
    roles = [('subject', 'symbol', 'cusip')]
    if kind == 'name_changes':
        roles = [('old', 'old_symbol', 'old_cusip'), ('new', 'new_symbol', 'new_cusip')]
    elif kind in ('cash_mergers', 'stock_mergers'):
        roles = [('acquiree', 'acquiree_symbol', 'acquiree_cusip'), ('acquirer', 'acquirer_symbol', 'acquirer_cusip')]
    for role, symbol_key, cusip_key in roles:
        symbol, cusip = record.get(symbol_key), record.get(cusip_key)
        if not _matches(TICKER, symbol):
            raise DataError('ACTION_PARTICIPANT')
        if cusip in (None, ''):
            issues.append('MISSING_' + cusip_key.upper())
            cusip = None
        elif not _matches(CUSIP, cusip):
            raise DataError('ACTION_PARTICIPANT')
        parties.append(ActionParty(role, symbol, cusip))
    if not any(p.symbol in symbols for p in parties):
        raise DataError('ACTION_SYMBOL_BINDING')
    expected_dates = {
        'cash_dividends': ('ex_date', 'record_date', 'payable_date'),
        'forward_splits': ('ex_date', 'record_date', 'payable_date', 'due_bill_redemption_date'),
        'cash_mergers': ('effective_date', 'payable_date'),
        'stock_mergers': ('effective_date', 'payable_date'),
    }.get(kind, ())
    for name in expected_dates:
        if record.get(name) in (None, ''):
            issues.append('MISSING_' + name.upper())
        else:
            session_date(record[name])
    economic_key = 'ex_date' if kind in ('cash_dividends', 'forward_splits') else 'effective_date'
    economic = record.get(economic_key) if economic_key in expected_dates else None
    if not economic:
        economic = None
        issues.append('ECONOMIC_DATE_UNVERIFIED')
    for name in SCHEMAS.get(kind, ()):
        if name.endswith('rate'):
            if record.get(name) is None:
                issues.append('MISSING_' + name.upper())
            else:
                _number(record[name])
        if name in ('foreign', 'special'):
            if name not in record:
                issues.append('MISSING_' + name.upper())
            elif type(record[name]) is not bool:
                raise DataError('ACTION_FIELDS')
    return ProviderAction(record['id'], kind, process.isoformat(), economic,
                          tuple(parties), tuple(sorted(set(issues))),
                          canonical(_plain(record)), rid, body_hash)


def read_action_evidence(raw: bytes) -> ActionEvidence:
    """Validate original bytes and their complete, frozen process-window pages."""
    value = _load(safe_text(raw))
    _fields(value, ('schema_version', 'host', 'requests', 'pages'), 'PROVIDER_ENVELOPE')
    if value['host'] != HOST:
        raise DataError('PROVIDER_HOST')
    if value['schema_version'] != 'alpaca-actions-v1':
        raise DataError('SCHEMA_VERSION')
    requests, pages = value['requests'], value['pages']
    if (type(requests) is not list or not 1 <= len(requests) <= MAX_REQUESTS
            or type(pages) is not list or not 1 <= len(pages) <= MAX_PAGES):
        raise DataError('INPUT_BOUND')
    profiles = {}
    for request in requests:
        _fields(request, ('id', 'path', 'params'), 'PROVIDER_REQUEST')
        rid = request['id']
        if not _matches(IDENTIFIER, rid) or rid in profiles:
            raise DataError('PROVIDER_REQUEST')
        if request['path'] != '/v1/corporate-actions':
            raise DataError('ACTION_PROFILE')
        profiles[rid] = (request['params'], _profile(request['params']))
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
    actions, seen = [], set()
    for rid, (params, profile) in profiles.items():
        chain = grouped[rid]
        if not chain:
            raise DataError('PROVIDER_PAGINATION')
        token, tokens, last_received = None, set(), None
        for index, page in enumerate(chain):
            expected = dict(params)
            if token is not None:
                expected['page_token'] = token
            actual = page['params']
            if (type(actual) is not dict or set(actual) != set(expected)
                    or any(type(actual[k]) is not type(expected[k]) or actual[k] != expected[k] for k in expected)):
                raise DataError('PROVIDER_REQUEST_BINDING')
            if type(page['status']) is not int or page['status'] != 200:
                raise DataError('PROVIDER_STATUS')
            started, received = utc_time(page['started_utc']), utc_time(page['received_utc'])
            if received < started or started.date() < profile[2] or (last_received and started < last_received):
                raise DataError('PROVIDER_TIMING')
            last_received = received
            if type(page['body_utf8']) is not str:
                raise DataError('PROVIDER_RESPONSE_FIELDS')
            try:
                body_bytes = page['body_utf8'].encode('utf-8')
            except UnicodeError:
                raise DataError('INVALID_ENCODING') from None
            if (not _matches(HASH, page['body_sha256'])
                    or hashlib.sha256(body_bytes).hexdigest() != page['body_sha256']):
                raise DataError('PROVIDER_HASH')
            body = _load(safe_text(body_bytes))
            _fields(body, ('corporate_actions', 'next_page_token'), 'PROVIDER_RESPONSE_FIELDS')
            groups = body['corporate_actions']
            if type(groups) is not dict:
                raise DataError('PROVIDER_RESPONSE_FIELDS')
            page_count = 0
            for kind, records in groups.items():
                if not _matches(IDENTIFIER, kind) or type(records) is not list:
                    raise DataError('PROVIDER_RESPONSE_FIELDS')
                for record in records:
                    action = _action(record, kind, rid, page['body_sha256'], profile)
                    if action.id in seen:
                        raise DataError('DUPLICATE_ACTION_ID')
                    seen.add(action.id)
                    actions.append(action)
                    page_count += 1
                    if len(actions) > MAX_ROWS:
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
    return ActionEvidence(raw, hashlib.sha256(raw).hexdigest(), tuple(actions))


def _revalidate(evidence):
    if type(evidence) is not ActionEvidence or read_action_evidence(evidence.content) != evidence:
        raise DataError('ACTION_EVIDENCE_CORRUPT')


def _diagnostic(evidence, rows, declared, kind):
    value = {'schema_version': kind, 'input_sha256': evidence.sha256,
             'declared_sources': declared, 'rows': rows,
             'counts': dict(sorted(Counter(r['state'] for r in rows).items())),
             'coverage': 'UNVERIFIED_PROVIDER_COVERAGE',
             'historical_provider_availability': 'UNVERIFIED', 'financial_accepted': False}
    content = canonical(value)
    return ActionDiagnostic(content, hashlib.sha256(content).hexdigest())


def classify_actions(evidence: ActionEvidence, identities: tuple[DeclaredIdentity, ...]) -> ActionDiagnostic:
    """Bind declared aliases to CUSIPs; an acquirer's existing shares are unaffected."""
    _revalidate(evidence)
    if type(identities) is not tuple or not 1 <= len(identities) <= 13:
        raise DataError('INVALID_ACTION_IDENTITY')
    cusips, aliases, symbols = set(), set(), set()
    for identity in identities:
        if (type(identity) is not DeclaredIdentity or type(identity.symbol) is not str
                or identity.symbol not in SYMBOLS
                or not _matches(CUSIP, identity.cusip) or not _matches(HASH, identity.lineage_sha256)
                or type(identity.aliases) is not tuple or not 1 <= len(identity.aliases) <= 4
                or any(not _matches(TICKER, s) for s in identity.aliases)
                or len(set(identity.aliases)) != len(identity.aliases) or identity.symbol not in identity.aliases):
            raise DataError('INVALID_ACTION_IDENTITY')
        if identity.cusip in cusips or identity.symbol in symbols or aliases.intersection(identity.aliases):
            raise DataError('AMBIGUOUS_ACTION_IDENTITY')
        cusips.add(identity.cusip)
        symbols.add(identity.symbol)
        aliases.update(identity.aliases)
    rows = []
    for action in evidence.actions:
        affected, counterparty = set(), set()
        conflict, unknown = False, False
        for party in action.parties:
            by_alias = [i for i in identities if party.symbol in i.aliases]
            by_cusip = [i for i in identities if i.cusip == party.cusip]
            if by_alias and party.cusip is None:
                unknown = True
            elif by_alias != by_cusip:
                conflict = True
            elif by_alias:
                target = counterparty if party.role == 'acquirer' else affected
                target.add(by_alias[0].symbol)
        if 'UNSUPPORTED_ACTION_TYPE' in action.issues or 'UNRECOGNIZED_ACTION_FIELDS' in action.issues:
            state = 'ACTION_SCHEMA_UNVERIFIED'
        elif conflict:
            state = 'SYMBOL_IDENTITY_CONFLICT'
        elif unknown:
            state = 'IDENTITY_UNVERIFIED'
        elif affected:
            state = 'IDENTITY_MATCHED'
        elif counterparty:
            state = 'COUNTERPARTY_ONLY'
        else:
            state = 'OUTSIDE_DECLARED_IDENTITIES'
        rows.append({'action_id': action.id, 'kind': action.kind, 'state': state,
                     'affected_assets': sorted(affected) if state == 'IDENTITY_MATCHED' else [],
                     'counterparty_assets': sorted(counterparty), 'issues': list(action.issues)})
    return _diagnostic(evidence, rows, [asdict(i) for i in identities], 'action-identity-v1')


def _observation(o):
    if (type(o) is not DividendObservation or not _matches(TICKER, o.symbol)
            or not _matches(HASH, o.lineage_sha256) or type(o.amount) is not str
            or not re.fullmatch(r'\d{1,16}(?:\.\d{1,12})?', o.amount)
            or (o.cusip is not None and not _matches(CUSIP, o.cusip))):
        raise DataError('INVALID_SOURCE_OBSERVATION')
    _number(Decimal(o.amount))
    session_date(o.ex_date)
    for name in ('record_date', 'payable_date'):
        if getattr(o, name) is not None:
            session_date(getattr(o, name))
    if o.publication_bound is not None:
        utc_time(o.publication_bound)


def reconcile_dividends(evidence: ActionEvidence, observations: tuple[DividendObservation, ...]) -> ActionDiagnostic:
    """Compare an explicitly declared subset without claiming full action coverage."""
    _revalidate(evidence)
    if type(observations) is not tuple or not 1 <= len(observations) <= MAX_ROWS:
        raise DataError('INVALID_SOURCE_OBSERVATION')
    seen, rows = set(), []
    for o in observations:
        _observation(o)
        key = (o.symbol, o.ex_date)
        if key in seen:
            raise DataError('DUPLICATE_SOURCE_OBSERVATION')
        seen.add(key)
        candidates = [a for a in evidence.actions if a.kind == 'cash_dividends'
                      and a.economic_date == o.ex_date and a.parties[0].symbol == o.symbol]
        conflict, unknown = [], []
        if not candidates:
            state = 'MISSING_PROVIDER_ACTION'
        elif len(candidates) > 1:
            state = 'AMBIGUOUS_PROVIDER_ACTION'
        else:
            fields = _load(candidates[0].fields)
            for name, provider_name in (('cusip', 'cusip'), ('amount', 'rate'), ('record_date', 'record_date'), ('payable_date', 'payable_date')):
                source, provider = getattr(o, name), fields.get(provider_name)
                if source is None or provider in (None, ''):
                    unknown.append(name)
                elif (Fraction(source) != Fraction(provider) if name == 'amount' else source != provider):
                    conflict.append(name)
            state = 'PROVIDER_SOURCE_CONFLICT' if conflict else 'PROVIDER_FIELDS_UNVERIFIED' if unknown else 'MATCHED_DECLARED_FIELDS'
        rows.append({'symbol': o.symbol, 'ex_date': o.ex_date, 'state': state,
                     'provider_action_ids': [a.id for a in candidates],
                     'conflicting_fields': conflict, 'unverified_fields': unknown,
                     'issues': ['SOURCE_PUBLICATION_UNVERIFIED'] if o.publication_bound is None else ['DECLARED_PUBLICATION_BOUND_ONLY']})
    return _diagnostic(evidence, rows, [asdict(o) for o in observations], 'action-dividends-v1')
