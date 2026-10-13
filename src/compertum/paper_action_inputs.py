"""Retained operational corporate-action observations; no coverage or authority grant."""
from dataclasses import dataclass, field
from decimal import Decimal
import json
from urllib.parse import urlencode

from .data.actions import IDENTIFIER, SCHEMAS, _action
from .data.calendar import session_date
from .data.encoding import canonical
from .data.errors import DataError
from .domain import ContractError
from .paper_contracts import identifier
from .paper_market_inputs import OperationalMarketPlan, _body, _day, _ns, _sha, _token

_MISSING = ('ACTION_COVERAGE_UNVERIFIED', 'ACTION_KNOWLEDGE_UNVERIFIED',
            'NATIVE_PROVENANCE_UNVERIFIED', 'ACTION_IDENTITY_UNVERIFIED', 'HALT_STATUS_UNVERIFIED')


def _need(value):
    if not value:
        raise ContractError('ACTION_INPUT_INVALID')


def _query(plan):
    _need(type(plan) is OperationalMarketPlan)
    plan.__post_init__()
    p = plan.to_payload()
    return dict(version=1, record_type='CurrentActionQuery', scope='PREPARATION_ONLY',
                plan_sha256=plan.sha256, origin='https://data.alpaca.markets', method='GET',
                path='/v1/corporate-actions', parameters=dict(symbols=p['symbol'],
                start=p['history_sessions'][0], end=p['session_date'], limit=100,
                sort='asc', data_quality='all', region='us'), transport_authorized=False,
                financial_accepted=False, research_eligible=False)


@dataclass(frozen=True, slots=True)
class CurrentActionQuery:
    plan: OperationalMarketPlan
    content: bytes

    def __post_init__(self):
        _need(type(self.content) is bytes and len(self.content) <= 65536)
        _need(canonical(_query(self.plan)) == self.content)

    def to_payload(self):
        return json.loads(self.content)

    @property
    def sha256(self):
        return _sha(self.content)


def prepare_action_query(plan):
    return CurrentActionQuery(plan, canonical(_query(plan)))


@dataclass(frozen=True, slots=True, repr=False)
class CurrentActionPage:
    query: CurrentActionQuery
    request_id: str
    page_token: str | None
    requested_at: str
    received_at: str
    status: int
    raw: bytes = field(repr=False)

    def __post_init__(self):
        _need(type(self.query) is CurrentActionQuery)
        self.query.__post_init__()
        identifier(self.request_id)
        _token(self.page_token)
        p = self.query.plan.to_payload()
        _need(type(self.status) is int and (self.status == 200 or 400 <= self.status <= 599))
        _need(_day(self.requested_at) == _day(self.received_at) == p['session_date'])
        _need(_ns(p['created_at']) <= _ns(self.requested_at) <= _ns(self.received_at))
        _need(_ns(self.received_at) - _ns(self.requested_at) <= 10 * 10**9)
        _body(self.raw)

    def __repr__(self):
        return '<CurrentActionPage retained body redacted>'

    def request_payload(self):
        self.__post_init__()
        return _request_payload(self.query, self.request_id, self.requested_at, self.page_token)


def _request_payload(query, request_id, requested_at, page_token):
    _need(type(query) is CurrentActionQuery)
    query.__post_init__()
    identifier(request_id)
    _token(page_token)
    p = query.plan.to_payload()
    _need(_day(requested_at) == p['session_date'] and _ns(requested_at) >= _ns(p['created_at']))
    q = query.to_payload()
    if page_token is not None:
        q['parameters']['page_token'] = page_token
    return dict(query_sha256=query.sha256, request_id=request_id,
            requested_at=requested_at, origin=q['origin'], method=q['method'],
            path=q['path'], parameters=q['parameters'],
            target=q['path'] + '?' + urlencode(q['parameters']), transport_authorized=False)


def _evidence(query, pages):
    _need(type(query) is CurrentActionQuery)
    query.__post_init__()
    _need(type(pages) is tuple and len(pages) <= 8)
    records, ids = [], set()
    for page in pages:
        _need(type(page) is CurrentActionPage)
        page.__post_init__()
        _need(page.query == query and page.request_id not in ids)
        ids.add(page.request_id)
        records.append(dict(request=page.request_payload(), received_at=page.received_at,
                            status=page.status, body_utf8=page.raw.decode('utf-8'), body_sha256=_sha(page.raw)))
    raw = canonical(dict(query=query.to_payload(), responses=records))
    _need(len(raw) <= 1048576)
    return raw


def _date(value):
    try:
        return session_date(value).isoformat()
    except DataError:
        return None


def _normalized(value):
    # Type tags prevent a provider string/object from impersonating a decoded number.
    if type(value) is dict:
        return ['object', [[k, _normalized(v)] for k, v in sorted(value.items())]]
    if type(value) is list:
        return ['array', [_normalized(v) for v in value]]
    if type(value) in (int, Decimal):
        return ['number', format(value, 'f') if type(value) is Decimal else str(value)]
    return [type(value).__name__, value]


def _event(record, kind, page, page_index, record_index, profile, day):
    issues = []
    valid_kind = IDENTIFIER.fullmatch(kind) is not None
    if not valid_kind:
        issues.append('ACTION_GROUP_FIELDS')
    value = dict(id=None, kind=kind if valid_kind else None, kind_sha256=_sha(canonical(kind)),
                 process_date=None, economic_date=None, payable_date=None,
                 affects_session=None, page_index=page_index, record_index=record_index,
                 request_id=page.request_id, body_sha256=_sha(page.raw),
                 normalized_record_sha256=_sha(canonical(_normalized(record))))
    if kind not in SCHEMAS:
        issues.append('UNSUPPORTED_ACTION_TYPE')
    if type(record) is dict:
        rid = record.get('id')
        if type(rid) is str and IDENTIFIER.fullmatch(rid):
            value['id'] = rid
        value['process_date'] = _date(record.get('process_date'))
    try:
        action = _action(record, kind, page.request_id, value['body_sha256'], profile)
        issues.extend(action.issues)
        value['process_date'] = action.process_date
        value['economic_date'] = action.economic_date
        if kind in ('cash_dividends', 'forward_splits', 'cash_mergers', 'stock_mergers'):
            value['payable_date'] = _date(json.loads(action.fields).get('payable_date'))
        dates = (value['economic_date'], value['payable_date'])
        value['affects_session'] = True if day in dates else False if all(dates) else None
    except DataError as exc:
        issues.append(exc.code)
    value['issues'] = sorted(set(issues))
    return value


def _result(query, pages, as_of):
    evidence = _evidence(query, pages)
    p = query.plan.to_payload()
    now = _ns(as_of)
    _need(_day(as_of) == p['session_date'] and now >= _ns(p['created_at']))
    params = query.to_payload()['parameters']
    profile = (frozenset((p['symbol'],)), session_date(params['start']), session_date(params['end']))
    reasons, events, seen = list(_MISSING), [], {}
    token, tokens, stopped, terminal = None, set(), False, False
    last_received, prior_process_max = _ns(p['created_at']), None
    for index, page in enumerate(pages):
        _need(not stopped and page.page_token == token)
        _need(last_received <= _ns(page.requested_at) <= _ns(page.received_at) <= now)
        last_received = _ns(page.received_at)
        if last_received > _ns(p['history_cutoff_at']):
            reasons.append('ACTION_RECEIVED_AFTER_CUTOFF')
        if page.status != 200:
            reasons.append('ACTION_HTTP_REFUSED')
            stopped = True
            continue
        body = _body(page.raw)
        groups = body.get('corporate_actions')
        shape_ok = type(groups) is dict
        if not shape_ok:
            reasons.append('ACTION_RESPONSE_FIELDS')
            groups = {}
        if set(body) - {'corporate_actions', 'next_page_token'}:
            reasons.append('UNRECOGNIZED_ACTION_RESPONSE_FIELDS')
        count, dates = 0, []
        for kind, records in groups.items():
            if type(records) is not list:
                reasons.append('ACTION_GROUP_FIELDS')
                shape_ok = False
                continue
            if not IDENTIFIER.fullmatch(kind):
                reasons.append('ACTION_GROUP_FIELDS')
                shape_ok = False
            count += len(records)
            _need(count <= 100)
            group_last = None
            for row, record in enumerate(records):
                event = _event(record, kind, page, index, row, profile, p['session_date'])
                process = event['process_date']
                if process is not None:
                    if group_last is not None and process < group_last:
                        event['issues'].append('ACTION_PROCESS_ORDER')
                    group_last = process
                    dates.append(process)
                rid = event['id']
                if rid is not None:
                    fingerprint = (kind, event['normalized_record_sha256'])
                    if rid in seen:
                        event['issues'].append('DUPLICATE_ACTION_ID' if fingerprint == seen[rid] else 'CONFLICTING_ACTION_ID')
                    else:
                        seen[rid] = fingerprint
                event['issues'] = sorted(set(event['issues']))
                reasons.extend(event['issues'])
                events.append(event)
        if dates:
            if prior_process_max is not None and min(dates) < prior_process_max:
                reasons.append('ACTION_PROCESS_ORDER')
            prior_process_max = max(dates) if prior_process_max is None else max(prior_process_max, max(dates))
        if 'next_page_token' not in body:
            reasons.append('ACTION_TERMINAL_TOKEN_MISSING')
            stopped = True
        else:
            try:
                token = _token(body['next_page_token'])
            except ContractError:
                reasons.append('ACTION_TERMINAL_TOKEN_INVALID')
                stopped = True
                continue
            if token is None:
                stopped, terminal = True, shape_ok
            else:
                _need(token not in tokens)
                tokens.add(token)
        # An invalid group cannot become a complete query on a subsequent page.
        if not shape_ok:
            reasons.append('ACTION_QUERY_SHAPE_UNVERIFIED')
    if not pages:
        reasons.append('ACTION_RESPONSES_MISSING')
    if 'ACTION_QUERY_SHAPE_UNVERIFIED' in reasons:
        terminal = False
    if not terminal:
        reasons.append('ACTION_QUERY_INCOMPLETE')
    return dict(version=1, record_type='CurrentActionInputDiagnostic', scope='PREPARATION_ONLY',
                query_sha256=query.sha256, evidence_sha256=_sha(evidence), project_id=p['project_id'],
                account_alias=p['account_alias'], symbol=p['symbol'], session_date=p['session_date'], as_of=as_of,
                process_window=dict(start=params['start'], end=params['end'], inclusive=True),
                query_pages_terminal=terminal, events=events, issues=sorted(set(reasons)), status='BLOCKED',
                current_action_coverage='UNVERIFIED', knowledge_timing='UNVERIFIED',
                native_provenance='UNVERIFIED', identity_mapping='UNVERIFIED', halt_status='UNVERIFIED',
                financial_accepted=False, transport_authorized=False, research_eligible=False)


@dataclass(frozen=True, slots=True, repr=False)
class CurrentActionInputs:
    query: CurrentActionQuery
    pages: tuple = field(repr=False)
    as_of: str
    content: bytes

    def __post_init__(self):
        _need(type(self.content) is bytes and len(self.content) <= 1048576)
        _need(canonical(_result(self.query, self.pages, self.as_of)) == self.content)

    def __repr__(self):
        return '<CurrentActionInputs unverified coverage and provenance>'

    def to_payload(self):
        return json.loads(self.content)

    def evidence_bytes(self):
        return _evidence(self.query, self.pages)

    @property
    def sha256(self):
        return _sha(self.content)


def qualify_action_inputs(query, pages, *, as_of):
    return CurrentActionInputs(query, pages, as_of, canonical(_result(query, pages, as_of)))
