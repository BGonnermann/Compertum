"""Inert retained halt-status frames, never proof of current market-wide state."""
from dataclasses import dataclass, field
import json
from .data.encoding import canonical
from .domain import ContractError
from .paper_contracts import identifier, strict_json
from .paper_market_inputs import OperationalMarketPlan, _day, _ns, _sha

_FIELDS = {'T', 'S', 'sc', 'sm', 'rc', 'rm', 't', 'z'}
_MISSING = ('STATUS_INITIAL_STATE_UNVERIFIED', 'STATUS_CONTINUITY_UNVERIFIED',
            'STATUS_COVERAGE_UNVERIFIED', 'STATUS_FRESHNESS_UNVERIFIED',
            'NATIVE_PROVENANCE_UNVERIFIED', 'FEED_ENTITLEMENT_UNVERIFIED', 'STATUS_IDENTITY_UNVERIFIED')
_CTA = {'2': 'HALTED', '3': 'TRADING_RESUMPTION_REPORTED',
        **{k: 'INFORMATIONAL' for k in ('5', '6', '7', '8', '9', 'A', 'C', 'D', 'E', 'F')}}
_UTP = {'H': 'HALTED', 'P': 'PAUSED', 'Q': 'QUOTE_RESUMPTION_ONLY', 'T': 'TRADING_RESUMPTION_REPORTED'}
_BLOCKING = {'HALTED', 'PAUSED', 'QUOTE_RESUMPTION_ONLY'}


def _need(value):
    if not value:
        raise ContractError('HALT_INPUT_INVALID')


def _plan(market_plan, expected_tape):
    _need(type(market_plan) is OperationalMarketPlan)
    market_plan.__post_init__()
    _need(type(expected_tape) is str and expected_tape in ('A', 'B', 'C', 'O'))
    p = market_plan.to_payload()
    return dict(version=1, record_type='HaltStreamPlan', scope='PREPARATION_ONLY',
                market_plan_sha256=market_plan.sha256, expected_tape=expected_tape,
                expected_tape_identity='UNVERIFIED', url='wss://stream.data.alpaca.markets/v2/iex',
                subscription=dict(action='subscribe', statuses=[p['symbol']]),
                feed_entitlement='UNVERIFIED', transport_authorized=False, financial_accepted=False,
                research_eligible=False)


@dataclass(frozen=True, slots=True)
class HaltStreamPlan:
    market_plan: OperationalMarketPlan
    content: bytes

    def __post_init__(self):
        p = strict_json(self.content)
        _need(type(p) is dict and 'expected_tape' in p)
        _need(canonical(_plan(self.market_plan, p['expected_tape'])) == self.content)

    def to_payload(self):
        return json.loads(self.content)

    @property
    def sha256(self):
        return _sha(self.content)


def prepare_halt_plan(market_plan, *, expected_tape):
    return HaltStreamPlan(market_plan, canonical(_plan(market_plan, expected_tape)))


def _messages(raw):
    value = strict_json(raw)
    _need(type(value) is list and len(value) <= 100)
    pending, count = [(value, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        _need(depth <= 16 and count <= 10000)
        if type(node) is dict:
            pending.extend((v, depth + 1) for v in node.values())
        elif type(node) is list:
            pending.extend((v, depth + 1) for v in node)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class HaltStatusFrame:
    plan: HaltStreamPlan
    connection_id: str
    connected_at: str
    received_at: str
    gap_before: bool
    raw: bytes = field(repr=False)

    def __post_init__(self):
        _need(type(self.plan) is HaltStreamPlan)
        self.plan.__post_init__()
        identifier(self.connection_id)
        p = self.plan.market_plan.to_payload()
        _need(type(self.gap_before) is bool)
        _need(_day(self.connected_at) == _day(self.received_at) == p['session_date'])
        _need(_ns(p['created_at']) <= _ns(self.connected_at) <= _ns(self.received_at))
        _messages(self.raw)

    def __repr__(self):
        return '<HaltStatusFrame retained body redacted>'


def _evidence(plan, frames):
    _need(type(plan) is HaltStreamPlan)
    plan.__post_init__()
    _need(type(frames) is tuple and len(frames) <= 8)
    records = []
    for frame in frames:
        _need(type(frame) is HaltStatusFrame)
        frame.__post_init__()
        _need(frame.plan == plan)
        records.append(dict(connection_id=frame.connection_id, connected_at=frame.connected_at,
                            received_at=frame.received_at, gap_before=frame.gap_before,
                            connection_evidence='DECLARED', body_utf8=frame.raw.decode('utf-8'),
                            body_sha256=_sha(frame.raw)))
    raw = canonical(dict(plan=plan.to_payload(), frames=records))
    _need(len(raw) <= 1048576)
    return raw


def _row(message, frame, index, message_index, as_of):
    row = dict(frame_index=index, message_index=message_index, connection_id=frame.connection_id,
               body_sha256=_sha(frame.raw), normalized_message_sha256=_sha(canonical(message)),
               classification='UNKNOWN', interpretable=False, event_at=None, age_ns=None,
               status_code=None, reason_code=None, tape=None, issues=[])
    issues = row['issues']
    if type(message) is not dict or not _FIELDS <= set(message):
        issues.append('STATUS_FIELDS')
        return row
    if set(message) != _FIELDS:
        issues.append('STATUS_FIELDS_UNRECOGNIZED')
    bounds = {'T': 1, 'S': 16, 'sc': 16, 'sm': 256, 'rc': 16, 'rm': 256, 't': 40, 'z': 1}
    if any(type(message[k]) is not str or len(message[k]) > size for k, size in bounds.items()):
        issues.append('STATUS_FIELDS')
        return row
    row.update(status_code=message['sc'], reason_code=message['rc'], tape=message['z'])
    p = frame.plan.market_plan.to_payload()
    if message['T'] != 's':
        issues.append('STATUS_MESSAGE_TYPE')
    if message['S'] != p['symbol']:
        issues.append('STATUS_SYMBOL_MISMATCH')
    tape, code = message['z'], message['sc']
    if tape not in ('A', 'B', 'C', 'O'):
        issues.append('STATUS_TAPE_UNKNOWN')
    elif tape != frame.plan.to_payload()['expected_tape']:
        issues.append('STATUS_TAPE_MISMATCH')
    classification = (_CTA if tape in ('A', 'B') else _UTP if tape in ('C', 'O') else {}).get(code)
    if classification is None:
        issues.append('STATUS_CODE_UNKNOWN')
    try:
        at = _ns(message['t'])
        if _day(message['t']) != p['session_date']:
            issues.append('STATUS_TIME_OTHER_SESSION')
        row.update(event_at=message['t'], age_ns=_ns(as_of) - at)
        if at > _ns(frame.received_at):
            issues.append('STATUS_TIME_AFTER_RECEIPT')
    except ContractError:
        issues.append('STATUS_TIME_INVALID')
    if not issues:
        row.update(classification=classification, interpretable=True)
        if at < _ns(frame.connected_at):
            issues.append('STATUS_PREDATES_CONNECTION')
    row['issues'] = sorted(set(issues))
    return row


def _result(plan, frames, as_of):
    evidence = _evidence(plan, frames)
    p = plan.market_plan.to_payload()
    now = _ns(as_of)
    _need(_day(as_of) == p['session_date'] and now >= _ns(p['created_at']))
    issues, events, connections, seen_times = list(_MISSING), [], {}, {}
    last_connection, last_received, greatest_time = None, _ns(p['created_at']), None
    latest_time, latest_status, latest_at = None, 'UNKNOWN', None
    blocking = False
    for index, frame in enumerate(frames):
        _need(last_received <= _ns(frame.received_at) <= now)
        if frame.connection_id != last_connection:
            _need(frame.connection_id not in connections and _ns(frame.connected_at) >= last_received)
            if last_connection is not None:
                issues.append('STATUS_STREAM_RECONNECTED')
            connections[frame.connection_id] = frame.connected_at
        else:
            _need(_ns(connections[frame.connection_id]) == _ns(frame.connected_at))
        if frame.gap_before:
            issues.append('STATUS_STREAM_GAP')
        last_connection, last_received = frame.connection_id, _ns(frame.received_at)
        if last_received > _ns(p['history_cutoff_at']):
            issues.append('STATUS_RECEIVED_AFTER_CUTOFF')
        for message_index, message in enumerate(_messages(frame.raw)):
            row = _row(message, frame, index, message_index, as_of)
            if row['interpretable']:
                at = _ns(row['event_at'])
                fingerprint = _sha(canonical(dict(message, t=at)))
                if greatest_time is not None and at < greatest_time:
                    row['issues'].append('STATUS_TIME_OUT_OF_ORDER')
                greatest_time = at if greatest_time is None else max(at, greatest_time)
                candidates = seen_times.setdefault(at, set())
                if fingerprint in candidates:
                    row['issues'].append('DUPLICATE_STATUS_MESSAGE')
                elif candidates:
                    row['issues'].append('CONFLICTING_STATUS_TIME')
                candidates.add(fingerprint)
                if latest_time is None or at >= latest_time:
                    latest_time, latest_at = at, row['event_at']
                    latest_status = row['classification'] if len(candidates) == 1 else 'AMBIGUOUS'
                blocking = blocking or row['classification'] in _BLOCKING
            row['issues'] = sorted(set(row['issues']))
            issues.extend(row['issues'])
            events.append(row)
    if not frames:
        issues.append('STATUS_FRAMES_MISSING')
    if not events:
        issues.append('STATUS_MESSAGES_MISSING')
    return dict(version=1, record_type='HaltStatusInputDiagnostic', scope='PREPARATION_ONLY',
                plan_sha256=plan.sha256, evidence_sha256=_sha(evidence), project_id=p['project_id'],
                account_alias=p['account_alias'], symbol=p['symbol'], session_date=p['session_date'], as_of=as_of,
                events=events, latest_observed_status=latest_status, latest_observed_at=latest_at,
                last_arrival_event_index=len(events)-1 if events else None,
                has_blocking_observation=blocking, current_halt_state='UNVERIFIED', status='BLOCKED',
                initial_state='UNVERIFIED', continuity='UNVERIFIED', connection_evidence='DECLARED',
                freshness_basis='UNVERIFIED', native_provenance='UNVERIFIED', feed_entitlement='UNVERIFIED',
                identity_mapping='UNVERIFIED', market_wide_coverage='UNVERIFIED', issues=sorted(set(issues)),
                financial_accepted=False, transport_authorized=False, research_eligible=False)


@dataclass(frozen=True, slots=True, repr=False)
class HaltStatusInputs:
    plan: HaltStreamPlan
    frames: tuple = field(repr=False)
    as_of: str
    content: bytes

    def __post_init__(self):
        _need(type(self.content) is bytes and len(self.content) <= 1048576)
        _need(canonical(_result(self.plan, self.frames, self.as_of)) == self.content)

    def __repr__(self):
        return '<HaltStatusInputs unverified current state>'

    def to_payload(self):
        return json.loads(self.content)

    def evidence_bytes(self):
        return _evidence(self.plan, self.frames)

    @property
    def sha256(self):
        return _sha(self.content)


def qualify_halt_inputs(plan, frames, *, as_of):
    return HaltStatusInputs(plan, frames, as_of, canonical(_result(plan, frames, as_of)))
