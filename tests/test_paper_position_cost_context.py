"""Current original costs with invented clocks and a labelled 64 KiB reserve."""
import json
import pickle
from uuid import uuid4

import pytest

from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_paper_reconciliation_context import (
    published_activity, pair, connect, owner, publication, invented_paper_origin,
    account, activity, activity_publication,
)
from test_paper_read_preparation import ACCOUNT, KEY, SECRET


def context(fixture, **changes):
    o, packet, saved, _ = fixture
    values = dict(subject='a'*64, packet_id=packet['packet_id'], activity_id=saved['activity_id'])
    values.update(changes)
    return o.a.position_cost_context(**values)


def test_private_original_costs_preserve_authority_and_borrowed_account(published_activity):
    from test_paper_reconciliation_context import context as comparison
    o, _, _, seen = published_activity
    before = o.a.db.total_changes, len(seen)
    old = comparison(published_activity).diagnostic()
    c = context(published_activity)
    value = c.diagnostic()
    assert value['record_type'] == 'PaperPositionCostDiagnostic'
    assert value['position_cost_status'] == 'MATCHING_RECORDED_FILL_COSTS'
    assert value['observation_status'] == 'MATCHING_LOOPBACK_OBSERVATIONS'
    assert value['order_count'] == value['fill_count'] == value['position_count'] == 0
    assert 'POSITION_COST_RECONSTRUCTION_UNVERIFIED' in old['unverified_requirements']
    assert 'POSITION_COST_RECONSTRUCTION_UNVERIFIED' not in value['unverified_requirements']
    assert {'ACTION_EVIDENCE_UNVERIFIED', 'FEE_LIABILITIES_UNVERIFIED', 'RISK_UNVERIFIED',
            'DURABLE_CONSUMPTION_UNVERIFIED'} == set(value['unverified_requirements'])
    assert value['status'] == 'BLOCKED' and value['actual_flat'] is None
    assert value['transport_authorized'] is value['financial_accepted'] is False
    assert (o.a.db.total_changes, len(seen)) == before
    assert all(s.encode() not in canonical(value) for s in (ACCOUNT, KEY, SECRET, '100000', 'expected_cash'))
    with pytest.raises(RuntimeRefused):
        pickle.dumps(c)
    with pytest.raises(RuntimeRefused):
        type(c)()
    c.close()
    assert not c._context._closed
    assert c._context.diagnostic()['confirmation_status'] == 'CONFIRMED_CURRENT_CONTEXT'


@pytest.mark.parametrize('fault', ['subject', 'packet', 'activity'])
def test_foreign_originals_refuse(published_activity, fault):
    values = {'subject': 'b'*64} if fault == 'subject' else {fault+'_id': str(uuid4())}
    with pytest.raises(RuntimeRefused):
        context(published_activity, **values)


@pytest.mark.parametrize('fault', ['expiry', 'clock_gap', 'opening', 'record'])
def test_changed_originals_permanently_refuse(published_activity, fault):
    o, _, saved, _ = published_activity
    c = context(published_activity)
    if fault == 'opening':
        with o.a.db:
            o.a.db.execute("UPDATE state SET value='{}' WHERE key='paper_opening:fixture'")
    elif fault == 'record':
        with o.a.db:
            o.a.db.execute('UPDATE state SET value=? WHERE key=?',
                (canonical(dict(saved, subject='b'*64)).decode(), 'paper_activity:'+saved['activity_id']))
    else:
        o.clock.utc += 31 if fault == 'expiry' else 6
        o.clock.mono += 31 if fault == 'expiry' else 0
    with pytest.raises(RuntimeRefused):
        c.diagnostic()
    assert c._closed
    with pytest.raises(RuntimeRefused):
        c.diagnostic()


@pytest.mark.parametrize('fault', ['wrapper', 'owner', 'database'])
def test_closed_resources_refuse(published_activity, fault):
    o, _, _, _ = published_activity
    c = context(published_activity)
    if fault == 'wrapper':
        c.close()
    elif fault == 'owner':
        o.a.close()
    else:
        o.a.db.close()
    with pytest.raises(RuntimeRefused):
        c.diagnostic()
    assert c._closed


def test_pending_transactions_preserve_original_caller_work(published_activity):
    o, _, _, _ = published_activity
    o.a.db.execute("INSERT INTO state VALUES('caller-uncommitted','true')")
    with pytest.raises(RuntimeRefused):
        context(published_activity)
    assert o.a.db.in_transaction and not o.a._account_context._closed
    o.a.db.rollback()
    c = context(published_activity)
    proof = c._prepare_proof()
    o.a.db.execute("INSERT INTO state VALUES('caller-uncommitted','true')")
    with pytest.raises(RuntimeRefused):
        proof._verify()
    assert not proof._used and not c._closed and o.a.db.in_transaction
    o.a.db.rollback()
    assert proof._verify()['record_type'] == 'PaperPositionCostDiagnostic'


def test_closed_database_refuses_before_portfolio_callbacks(published_activity, monkeypatch):
    from compertum.runtime import paper_reconciliation_context as module
    o, _, _, _ = published_activity
    def unexpected(*args, **kwargs):
        raise AssertionError('Unexpected portfolio callback')
    monkeypatch.setattr(module, '_portfolio_context', unexpected)
    o.a.db.close()
    with pytest.raises(RuntimeRefused) as refused:
        context(published_activity)
    assert refused.value.code == 'PAPER_RECONCILIATION_DATABASE_CLOSED'


def test_single_use_and_borrowed_account_survive_wrapper_closure(published_activity):
    c = context(published_activity)
    proof = c._prepare_proof()
    assert proof._verify()['status'] == 'BLOCKED'
    with pytest.raises(RuntimeRefused):
        proof._verify()
    proof = c._prepare_proof()
    c.close()
    with pytest.raises(RuntimeRefused):
        proof._verify()
    assert not c._context._closed


@pytest.mark.parametrize('mode', [False, 1, None])
def test_mode_substitution_refuses_permanently(published_activity, mode):
    c = context(published_activity)
    object.__setattr__(c, '_position_costs', mode)
    with pytest.raises(RuntimeRefused):
        c.diagnostic()
    assert c._closed and not c._context._closed


@pytest.mark.parametrize('stage', ['decryption', 'calculation', 'verification'])
def test_mode_change_during_callbacks_refuses(published_activity, monkeypatch, stage):
    from contextlib import contextmanager
    from compertum.runtime import paper_reconciliation_context as module
    c = context(published_activity)
    if stage == 'decryption':
        original = module.open_activity_evidence
        @contextmanager
        def changed(*args, **kwargs):
            with original(*args, **kwargs) as opened:
                yield opened
            object.__setattr__(c, '_position_costs', False)
        monkeypatch.setattr(module, 'open_activity_evidence', changed)
    else:
        name = 'calculate_position_costs' if stage == 'calculation' else '_published'
        original = getattr(module, name)
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            object.__setattr__(c, '_position_costs', False)
            return result
        if stage == 'verification':
            proof = c._prepare_proof()
        monkeypatch.setattr(module, name, changed)
    with pytest.raises(RuntimeRefused):
        proof._verify() if stage == 'verification' else c.diagnostic()
    assert c._closed and not c._context._closed


def test_late_original_clock_still_refuses(published_activity, monkeypatch):
    from compertum.runtime import paper_reconciliation_context as module
    o, _, _, _ = published_activity
    c = context(published_activity)
    proof = c._prepare_proof()
    original = module._published
    def delayed(*args):
        result = original(*args)
        o.clock.utc += 31
        o.clock.mono += 31
        return result
    monkeypatch.setattr(module, '_published', delayed)
    with pytest.raises(RuntimeRefused):
        proof._verify()
    assert c._closed


def test_final_diagnostic_uses_actual_credential_reflection_check(published_activity, monkeypatch):
    from compertum.runtime import paper_reconciliation_context as module
    def reject(raw, secrets):
        assert json.loads(raw)['record_type'] == 'PaperPositionCostDiagnostic'
        assert KEY in secrets and SECRET in secrets
        raise RuntimeRefused('SIMULATED_DIAGNOSTIC_SECRET_REFLECTION')
    monkeypatch.setattr(module, '_reject_reflections', reject)
    with pytest.raises(RuntimeRefused):
        context(published_activity)


def test_mode_change_during_final_account_clock_refuses(published_activity, monkeypatch):
    from compertum.runtime import paper_account_context as module
    c = context(published_activity)
    proof = c._prepare_proof()
    original = module._final_account
    def changed(*args):
        result = original(*args)
        object.__setattr__(c, '_position_costs', False)
        return result
    monkeypatch.setattr(module, '_final_account', changed)
    with pytest.raises(RuntimeRefused):
        proof._verify()
    assert c._closed and not c._context._closed


def test_actual_account_corruption_retains_revocation(published_activity, monkeypatch):
    import test_paper_reconciliation_context as old
    monkeypatch.setattr(old, 'context', context)
    old.test_actual_account_failure_still_revokes_borrowed_account(published_activity)


def final_clock_mode_change(monkeypatch, c):
    from types import SimpleNamespace
    from compertum.runtime import execution_health
    clocks = execution_health.time
    def changed():
        value = clocks.monotonic()
        object.__setattr__(c, '_position_costs', False)
        return value
    monkeypatch.setattr(execution_health, 'time', SimpleNamespace(monotonic=changed, time=clocks.time))


@pytest.mark.parametrize('path', ['captured', 'diagnostic'])
def test_final_health_clock_cannot_switch_cost_mode(published_activity, monkeypatch, path):
    c = context(published_activity)
    proof = c._prepare_proof() if path == 'captured' else None
    final_clock_mode_change(monkeypatch, c)
    with pytest.raises(RuntimeRefused):
        proof._verify() if proof else c.diagnostic()
    assert c._closed and not c._context._closed
    if proof:
        assert proof._used and proof._owner is None and proof._check is None


def test_grouped_default_and_cost_proofs_attribute_failure_and_clear_consumed_hooks(published_activity, monkeypatch):
    from compertum.runtime.paper_final_proof import _verify_proofs
    c = context(published_activity)
    default = c._context._prepare_proof()
    assert default._final_identity is None
    cost = c._prepare_proof()
    values = _verify_proofs(default, cost)
    assert [v['record_type'] for v in values] == ['PaperAccountInputDiagnostic', 'PaperPositionCostDiagnostic']
    assert default._final_identity is cost._final_identity is None
    default, cost = c._context._prepare_proof(), c._prepare_proof()
    final_clock_mode_change(monkeypatch, c)
    with pytest.raises(RuntimeRefused):
        _verify_proofs(default, cost)
    assert c._closed and not c._context._closed
    assert default._used and cost._used
    assert default._owner is cost._owner is default._final_identity is cost._final_identity is None


@pytest.mark.parametrize('mismatch', [False, True])
def test_original_nonempty_costs_reach_the_verified_calculation(activity_publication, publication, monkeypatch, mismatch):
    import test_paper_reconciliation_context as old
    import test_paper_portfolio as portfolio
    original_position = portfolio.position
    if mismatch:
        def changed(**values):
            return original_position(**dict(values, cost_basis='149', avg_entry_price='149'))
        monkeypatch.setattr(portfolio, 'position', changed)
    original_factory = old.context
    observed = []
    def compare_then_cost(fixture, **changes):
        original = original_factory(fixture, **changes)
        assert original.diagnostic()['record_type'] == 'PaperReconciliationDiagnostic'
        try:
            c = context(fixture, **changes)
        except RuntimeRefused:
            assert mismatch
            assert not original._context._closed
            raise
        assert not mismatch
        assert c.diagnostic()['position_cost_status'] == 'MATCHING_RECORDED_FILL_COSTS'
        observed.append(True)
        return c
    monkeypatch.setattr(old, 'context', compare_then_cost)
    if mismatch:
        with pytest.raises(RuntimeRefused):
            old.test_native_retained_buy_and_original_nonempty_observations(activity_publication, publication, monkeypatch, 'complete')
    else:
        old.test_native_retained_buy_and_original_nonempty_observations(activity_publication, publication, monkeypatch, 'complete')
        assert observed == [True]


@pytest.mark.parametrize('second_symbol_conflict', [False, True])
def test_original_close_reopen_keeps_uncertain_costs_and_other_symbol_checks(activity_publication, publication, monkeypatch, second_symbol_conflict):
    from compertum.fake_execution_journal import FakeIntentJournal
    from compertum.fake_attempt_guard import append_record
    from compertum.native_attempt_records import sha
    from test_native_attempt_records import records, attempt
    from test_paper_portfolio import order, position
    from test_paper_portfolio_context import fresh
    from test_paper_activity_owner import pages, pub_start, finish
    import test_paper_read_owner as reader
    o, _, pub, module, remote = activity_publication
    FakeIntentJournal(o.a.store)
    orders, fills = [], []
    trades = [('buy', '150', 'AAPL'), ('buy', '151', 'AAPL'), ('sell', '152', 'AAPL'),
              ('sell', '153', 'AAPL'), ('buy', '154', 'AAPL')]
    if second_symbol_conflict:
        trades.append(('buy', '20', 'MSFT'))
    for index, (side, price, symbol) in enumerate(trades, 1):
        p, d = records(o.e.lease)
        stamp = f'2023-11-24T14:30:00.{index}00000Z'
        p.update(created_at=stamp, expires_at=f'2023-11-24T14:31:00.{index}00000Z',
                 purpose='CLOSE_LONG' if side == 'sell' else 'FIXTURE_BUY')
        p['request']['created_at'] = stamp
        p['request']['body']['side'] = side
        p['request']['body']['symbol'] = symbol
        p['request_sha256'] = sha(p['request'])
        d['intent_sha256'] = sha(p)
        a = dict(attempt(p, d), attempted_at=stamp)
        with o.a.db:
            append_record(o.a.store, a)
        observed = order(index, client_order_id=p['client_order_id'], qty='1', filled_qty='1',
            filled_avg_price=price, status='filled', submitted_at=stamp, side=side, symbol=symbol)
        if symbol == 'MSFT':
            observed['asset_id'] = '33333333-3333-4333-8333-333333333333'
        orders.append(observed)
        fills.append(dict(activity_type='FILL', id=f'20231124::cost-{index}', order_id=observed['id'],
            symbol=symbol, side=side, qty='1', cum_qty='1', leaves_qty='0', price=price,
            transaction_time=stamp, type='fill'))
    original = reader.body
    def body(operation):
        if operation == 'POSITIONS':
            rows = [position(avg_entry_price='154', cost_basis='154')]
            if second_symbol_conflict:
                rows.append(position(symbol='MSFT', asset_id='33333333-3333-4333-8333-333333333333',
                    avg_entry_price='19', cost_basis='19'))
            return rows
        if operation == 'ORDERS':
            return orders
        value = original(operation)
        return dict(value, cash='99830' if second_symbol_conflict else '99850') if operation == 'ACCOUNT' else value
    monkeypatch.setattr(reader, 'body', body)
    o.clock.utc += 1
    o.clock.mono += 1
    _, _, packet = fresh(publication)
    o.a.account_context(subject='a'*64, packet_id=packet['packet_id'])
    o.clock.utc += 1
    o.clock.mono += 1
    with pages([canonical(fills)]) as (port, seen):
        o.activity_port = port
        started = pub_start((o, packet, pub, module, remote))
        finish(o, started)
        for _ in range(12):
            pub.tick()
        saved = o.a._activities._read(started['activity_id'])
        if second_symbol_conflict:
            with pytest.raises(RuntimeRefused):
                context((o, packet, saved, seen))
            assert not o.a._account_context._closed
            return
        c = context((o, packet, saved, seen))
        value = c.diagnostic()
        assert value['position_cost_status'] == 'UNSUPPORTED_FILL_COST_HISTORY'
        assert {'UNSUPPORTED_FILL_COST_HISTORY', 'POSITION_COST_RECONSTRUCTION_UNVERIFIED'} <= set(value['unverified_requirements'])
        assert value['order_count'] == value['fill_count'] == 5 and value['position_count'] == 1
        assert value['transport_authorized'] is value['financial_accepted'] is False
