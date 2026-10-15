"""Proposed exact terms remain separate from ownership/risk/dispatch authority."""
import copy,json
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_input_context import inputs,confirmed,context
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication
from test_paper_account_binding import invented_paper_origin,call,confirm
from test_paper_presence import acknowledge,packet
from test_native_intent_cancel import inspect,confirm_intent


TERMS={
    'FIXTURE_BUY':dict(fixture_id='native-wire-1',symbol='MSFT'),
    'FIXTURE_RESTING_BUY':dict(fixture_id='native-wire-1',symbol='MSFT',limit_price='75'),
    'CLOSE_LONG':dict(symbol='MSFT',quantity=3,children=[dict(maximum_quantity=2,notional_cap='2000'),dict(maximum_quantity=1,notional_cap='2000')]),
    'STRATEGY':dict(candidate_id='momentum-h01',candidate_version='v1',protocol_sha256='1'*64,
                    symbol='MSFT',side='buy',quantity=1,rebalance_session='2023-11-24'),
}


def prepare_combined(fixture,purpose,**changes):
    o,read,fresh,capture,pub=fixture;_,presence=acknowledge((o,pub,read))
    values=dict(packet_id=read['packet_id'],fresh_job_id=fresh['job_id'],capture_id=capture,
                presence_id=presence['presence_id'],purpose=purpose,terms=copy.deepcopy(TERMS[purpose]))
    values.update(changes);p=packet('prepare',**values)
    return p,o.a.intent_handle(p)


@pytest.mark.parametrize('purpose',list(TERMS))
def test_purpose_specific_intent_and_confirmation_never_grant_missing_risk_authority(confirmed,purpose):
    o=confirmed[0];calls=len(o.calls);_,r=prepare_combined(confirmed,purpose);_,c=confirm_intent(o,r);v=inspect(o,r)
    assert r['purpose']==c['purpose']==purpose and v['intent_status']=='CURRENT_CONFIRMED'
    assert v['order_admission']=='BLOCKED' and v['transport_authorized'] is v['financial_accepted'] is False
    assert {'OWNERSHIP_UNVERIFIED','ECONOMIC_RECONCILIATION_UNVERIFIED','RISK_UNVERIFIED','EXACT_CONSUMPTION_UNVERIFIED'}<=set(v['unverified_requirements'])
    assert len(o.calls)==calls and o.a.db.execute("SELECT 1 FROM sqlite_master WHERE name='fake_intents'").fetchone() is None
    if purpose.startswith('FIXTURE_'):
        assert r['terms']['quantity']==1 and r['terms']['maximum_exposure']=='250'
    elif purpose=='CLOSE_LONG':
        assert r['terms']['quantity']==3 and len(r['terms']['children'])<=12
        from compertum.paper_contracts import timestamp
        assert 0<(timestamp(r['operation_deadline'])-timestamp(r['created_at'])).total_seconds()<=600
    else:
        assert r['terms']['order_type']=='market' and r['terms']['time_in_force']=='day' and r['terms']['extended_hours'] is False


@pytest.mark.parametrize('purpose,change',[
    ('FIXTURE_BUY',dict(quantity=2)),('FIXTURE_BUY',dict(maximum_exposure='251')),
    ('FIXTURE_RESTING_BUY',dict(limit_price='0')),('FIXTURE_RESTING_BUY',dict(limit_price='NaN')),
    ('FIXTURE_BUY',dict(candidate_id='strategy-cannot-be-fixture')),
    ('STRATEGY',dict(fixture_id='fixture-cannot-be-strategy')),('STRATEGY',dict(quantity=True)),
    ('STRATEGY',dict(side='short')),('STRATEGY',dict(protocol_sha256='invalid')),
    ('STRATEGY',dict(order_type='limit')),('STRATEGY',dict(extended_hours=True)),
    ('CLOSE_LONG',dict(quantity=0)),('CLOSE_LONG',dict(quantity=1.5)),
    ('CLOSE_LONG',dict(children=[])),('CLOSE_LONG',dict(children=[dict(maximum_quantity=1,notional_cap='2000')]*13)),
    ('CLOSE_LONG',dict(children=[dict(maximum_quantity=3,notional_cap='2001')])),
    ('CLOSE_LONG',dict(children=[dict(maximum_quantity=4,notional_cap='2000')])),
])
def test_cross_purpose_or_unbounded_terms_refuse(confirmed,purpose,change):
    terms=copy.deepcopy(TERMS[purpose]);terms.update(change)
    with pytest.raises(RuntimeRefused):prepare_combined(confirmed,purpose,terms=terms)


@pytest.mark.parametrize('field',['packet_id','fresh_job_id','capture_id','presence_id'])
def test_combined_records_bind_original_inputs(confirmed,field):
    from uuid import uuid4
    with pytest.raises(RuntimeRefused):prepare_combined(confirmed,'FIXTURE_BUY',**{field:str(uuid4())})


@pytest.mark.parametrize('fault',['context','replacement','producer','history','composition'])
def test_confirmation_cannot_recreate_or_rebind_original_combined_inputs(confirmed,fault):
    o=confirmed[0];_,r=prepare_combined(confirmed,'FIXTURE_BUY');original=o.a._input_context
    if fault=='context':original.close()
    elif fault=='replacement':context(confirmed)
    elif fault=='producer':o.a._market._producer.close()
    elif fault=='history':o.a._market._opened.close()
    else:o.a._market._combined.close()
    with pytest.raises(RuntimeRefused):confirm_intent(o,r)
    assert inspect(o,r)['intent_status']=='INVALIDATED'


@pytest.mark.parametrize('purpose,at,deadline',[
    ('STRATEGY','2023-11-24T14:35:59+00:00','2023-11-24T14:36:00+00:00'),
    ('FIXTURE_BUY','2023-11-24T15:04:59+00:00','2023-11-24T15:05:00+00:00'),
    ('CLOSE_LONG','2023-11-24T17:59:59+00:00','2023-11-24T18:00:00+00:00'),
])
def test_owner_derives_window_and_session_boundaries_from_original_calendar(request,invented_paper_origin,purpose,at,deadline):
    from datetime import datetime
    from test_paper_presence import advance
    o=request.getfixturevalue('history');stamp=datetime.fromisoformat(at).timestamp()
    o.clock.mono+=stamp-o.clock.utc;o.clock.utc=stamp
    fixture=request.getfixturevalue('confirmed');_,r=prepare_combined(fixture,purpose);confirm_intent(o,r)
    assert r['expires_at']==deadline
    if purpose=='CLOSE_LONG':assert r['operation_deadline']==deadline
    advance(o,.999);assert inspect(o,r)['intent_status']=='CURRENT_CONFIRMED'
    advance(o,.001);assert inspect(o,r)['intent_status']=='INVALIDATED'


@pytest.mark.parametrize('purpose,at',[
    ('STRATEGY','2023-11-24T14:34:59+00:00'),
    ('STRATEGY','2023-11-24T14:36:00+00:00'),
    ('FIXTURE_BUY','2023-11-24T14:34:59+00:00'),
    ('FIXTURE_BUY','2023-11-24T15:05:00+00:00'),
    ('FIXTURE_RESTING_BUY','2023-11-24T15:05:00+00:00'),
])
def test_fresh_preparation_outside_its_exact_window_is_refused(request,invented_paper_origin,purpose,at):
    from datetime import datetime
    o=request.getfixturevalue('history');stamp=datetime.fromisoformat(at).timestamp()
    o.clock.mono+=stamp-o.clock.utc;o.clock.utc=stamp
    fixture=request.getfixturevalue('confirmed')
    # Confirm that the newly observed account/calendar is coherent before the
    # intent window rejects this otherwise fresh input.
    value=o.a.preflight(fixture[1]['packet_id']).diagnostic()
    assert value['calendar_agreement']=='MATCHES_PINNED_CALENDAR'
    assert not any('CLOCK' in reason for reason in value['deficiencies'])
    with pytest.raises(RuntimeRefused,match='PAPER_INTENT_WINDOW'):
        prepare_combined(fixture,purpose)
