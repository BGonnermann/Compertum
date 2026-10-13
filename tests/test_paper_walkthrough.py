"""A synthetic walkthrough sequence never establishes actual M5 acceptance."""
from dataclasses import replace,FrozenInstanceError
from uuid import UUID
import json
import pytest
from compertum.domain import ContractError
from compertum.paper_contracts import read_request
from compertum.paper_responses import parse_response
from compertum.paper_walkthrough import PaperFixtureStep,check_fixture_walkthrough
from test_paper_fixture_plans import at_portfolio,at_facts,proposal,position,order,ACCOUNT


def at(second):return f'2023-11-24T14:35:{second:02d}Z'


def make_reply(plan,index,received,status='filled'):
    r=read_request(json.dumps(plan.to_payload()['requests'][0],sort_keys=True,separators=(',',':')).encode())
    p=r.to_payload()
    if p['operation']=='CANCEL_ORDER':
        return parse_response(r,origin=p['origin'],account_id=ACCOUNT,status=204,raw=b'',received_at=received),None
    body=p['body'];filled=body['qty'] if status=='filled' else '0'
    row=order(index=index,client_order_id=body['client_order_id'],qty=body['qty'],side=body['side'],type=body['type'],limit_price=body.get('limit_price'),status=status,filled_qty=filled,filled_avg_price='100' if filled!='0' else None,submitted_at=p['created_at'])
    return parse_response(r,origin=p['origin'],account_id=ACCOUNT,status=200,raw=json.dumps(row).encode(),received_at=received),row


def sequence(*,recovery_fill=False,cancel_fill=False):
    baseline=at_portfolio(at(8))
    p=proposal(portfolio=baseline,inputs=at_facts(at(8)),now=at(8))
    r,buy=make_reply(p,1,at(9));buy_after=at_portfolio(at(12),positions=[position()],orders=[buy])
    opening=PaperFixtureStep(p,(r,),buy_after)
    holding_recovery=at_portfolio(at(14),positions=[position()],orders=[buy])
    p=proposal('RESTING_BUY',portfolio=holding_recovery,inputs=at_facts(at(14)),now=at(14),intent_id=str(UUID(int=555)),limit_price='80')
    r,rest=make_reply(p,2,at(15),'new');rest_after=at_portfolio(at(18),positions=[position()],orders=[buy,rest])
    resting=PaperFixtureStep(p,(r,),rest_after)
    recovered=dict(rest,status='pending_cancel',filled_qty='1',filled_avg_price='80') if recovery_fill else rest
    holding_quantity=2 if recovery_fill else 1
    resting_recovery=at_portfolio(at(20),positions=[position(qty=str(holding_quantity))],orders=[buy,recovered])
    p=proposal('CANCEL',portfolio=resting_recovery,inputs=at_facts(at(20)),now=at(20),intent_id=str(UUID(int=666)),order_id=rest['id'])
    r,_=make_reply(p,2,at(21));canceled=dict(recovered,status='canceled')
    if cancel_fill:canceled.update(filled_qty='1',filled_avg_price='80');holding_quantity=2
    cancel_after=at_portfolio(at(24),positions=[position(qty=str(holding_quantity))],orders=[buy,canceled])
    cancellation=PaperFixtureStep(p,(r,),cancel_after)
    p=proposal('CLOSE_LONG',portfolio=cancel_after,inputs=at_facts(at(24)),now=at(24),intent_id=str(UUID(int=777)))
    r,close=make_reply(p,3,at(25));close_after=at_portfolio(at(28),orders=[buy,canceled,close])
    closing=PaperFixtureStep(p,(r,),close_after)
    return dict(baseline=baseline,opening=opening,holding_recovery=holding_recovery,resting=resting,resting_recovery=resting_recovery,cancellation=cancellation,closing=closing)


def test_complete_fixture_is_immutable_but_actual_gates_stay_unverified():
    args=sequence();v=check_fixture_walkthrough(**args);p=v.to_payload()
    assert p['status']=='INTERNAL_FIXTURE_SEQUENCE_VALID' and p['actual_m5_accepted'] is False
    assert p['financial_accepted'] is p['transport_authorized'] is False
    assert p['fixture_final_empty'] is True and p['actual_flat'] is None
    assert p['opening_quantity']==p['closed_quantity']==1
    assert p['missing_actual_evidence'] and 'NATIVE_RESTART_IDENTITY_AND_NO_RESUBMISSION' in p['missing_actual_evidence']
    assert check_fixture_walkthrough(**args).content==v.content
    p['actual_m5_accepted']=True;assert not v.to_payload()['actual_m5_accepted']
    with pytest.raises((FrozenInstanceError,AttributeError)):v.content=b'{}'


@pytest.mark.parametrize('field',['baseline','opening','holding_recovery','resting','resting_recovery','cancellation','closing'])
def test_missing_or_untyped_evidence_cannot_pass(field):
    args=sequence();args[field]={}
    with pytest.raises(ContractError):check_fixture_walkthrough(**args)


def test_cancellation_204_is_not_terminal_evidence():
    args=sequence();step=args['cancellation'];rows=[dict(row) for row in json.loads(args['resting_recovery'].orders[0].raw)]
    pending=at_portfolio(at(24),positions=[position()],orders=rows)
    args['cancellation']=replace(step,after=pending)
    with pytest.raises(ContractError):check_fixture_walkthrough(**args)


def test_a_final_empty_list_cannot_erase_unfilled_close():
    args=sequence();step=args['closing'];rows=json.loads(step.after.orders[0].raw);rows[-1].update(status='canceled',filled_qty='0',filled_avg_price=None)
    args['closing']=replace(step,after=at_portfolio(at(28),orders=rows))
    with pytest.raises(ContractError):check_fixture_walkthrough(**args)


@pytest.mark.parametrize('change',['id','client_order_id','qty','positions','extra_order'])
def test_restart_must_preserve_identified_activity_and_quantity(change):
    args=sequence();rows=json.loads(args['resting_recovery'].orders[0].raw);positions=[position()]
    if change=='id':rows[-1]['id']=str(UUID(int=999))
    elif change=='client_order_id':rows[-1]['client_order_id']='cmp-another'
    elif change=='qty':rows[-1]['qty']='2'
    elif change=='positions':positions=[position(qty='2')]
    else:rows.append(order(index=9))
    args['resting_recovery']=at_portfolio(at(20),positions=positions,orders=rows)
    with pytest.raises(ContractError):check_fixture_walkthrough(**args)


def test_reply_must_bind_the_exact_draft_and_cannot_be_404():
    args=sequence();step=args['opening'];r=step.replies[0]
    failed=parse_response(r.request,origin=r.origin,account_id=r.account_id,status=404,raw=b'{}',received_at=r.received_at)
    for replies in ((failed,),args['resting'].replies,(),(r,r)):
        args=sequence();args['opening']=replace(args['opening'],replies=replies)
        with pytest.raises(ContractError):check_fixture_walkthrough(**args)


def test_recovery_or_reconciliation_cannot_precede_recorded_response():
    args=sequence();step=args['opening'];rows=json.loads(step.after.orders[0].raw)
    args['opening']=replace(step,after=at_portfolio(at(9),positions=[position()],orders=rows))
    with pytest.raises(ContractError):check_fixture_walkthrough(**args)


def test_incomplete_recovery_is_not_an_empty_recovery():
    from compertum.paper_portfolio import build_portfolio_bundle
    args=sequence();old=args['holding_recovery']
    args['holding_recovery']=build_portfolio_bundle(account=old.account,positions=None,orders=old.orders,clock=old.clock,calendar=old.calendar,as_of=old.as_of)
    with pytest.raises(ContractError):check_fixture_walkthrough(**args)

@pytest.mark.parametrize('kwargs',[{'cancel_fill':True},{'recovery_fill':True}])
def test_observed_fills_increase_the_required_closing_quantity(kwargs):
    args=sequence(**kwargs);result=check_fixture_walkthrough(**args).to_payload()
    assert result['closed_quantity']==2 and result['fixture_final_empty'] is True
    assert result['actual_flat'] is None and not result['actual_m5_accepted']


@pytest.mark.parametrize('change',['remove_old_order','decrease_old_fill','change_old_price','swap_stage','residual'])
def test_evidence_cannot_rewrite_history_or_skip_stages(change):
    args=sequence()
    if change=='swap_stage':args['opening']=args['resting']
    elif change=='residual':
        from test_paper_fixture_plans import facts
        p=proposal('CLOSE_LONG',portfolio=args['cancellation'].after,inputs=at_facts(at(24),ask='2000',bid='1999'),now=at(24),intent_id=str(UUID(int=777)))
        args['closing']=PaperFixtureStep(p,(),args['closing'].after)
    else:
        rows=json.loads(args['holding_recovery'].orders[0].raw)
        if change=='remove_old_order':rows=[]
        elif change=='decrease_old_fill':rows[0].update(status='canceled',filled_qty='0',filled_avg_price=None)
        else:rows[0]['filled_avg_price']='101'
        args['holding_recovery']=at_portfolio(at(14),positions=[position()],orders=rows)
    with pytest.raises(ContractError):check_fixture_walkthrough(**args)


def test_terminal_response_fill_price_cannot_be_rewritten_by_order_list():
    args=sequence();s=args['opening'];rows=json.loads(s.after.orders[0].raw);rows[0]['filled_avg_price']='101'
    args['opening']=replace(s,after=at_portfolio(at(12),positions=[position()],orders=rows))
    with pytest.raises(ContractError):check_fixture_walkthrough(**args)


def test_decimal_context_does_not_change_sequence_result():
    from decimal import localcontext
    args=sequence();expected=check_fixture_walkthrough(**args).content
    with localcontext() as ctx:
        ctx.prec=3
        assert check_fixture_walkthrough(**args).content==expected

# Rebind every dependent proposal to the changed portfolio. These mutations
# must fail semantic checks, rather than an incidental snapshot-hash mismatch.
def transform_sequence(args,change):
    from compertum.paper_portfolio import build_portfolio_bundle
    from compertum.paper_responses import parse_response
    def transform(p):
        def reply(r,positions):
            rows=json.loads(r.raw)
            for row in rows:change(row,positions,p.as_of)
            return parse_response(r.request,origin=r.origin,account_id=r.account_id,status=r.status,raw=json.dumps(rows).encode(),received_at=r.received_at)
        return build_portfolio_bundle(account=p.account,positions=reply(p.positions,True),orders=tuple(reply(r,False) for r in p.orders),clock=p.clock,calendar=p.calendar,as_of=p.as_of)
    result={}
    for key,value in args.items():
        if isinstance(value,PaperFixtureStep):
            result[key]=replace(value,proposal=replace(value.proposal,portfolio=transform(value.proposal.portfolio)),after=transform(value.after))
        else:result[key]=transform(value)
    return result


@pytest.mark.parametrize('mutation',['position_asset','close_asset','backdated_submission','future_submission','numeric_fill_price_change'])
def test_semantic_identity_cannot_hide_behind_rebound_fixture_hashes(mutation):
    args=sequence(recovery_fill=mutation=='numeric_fill_price_change')
    def change(row,is_position,observed):
        if mutation=='position_asset' and is_position:row['asset_id']=str(UUID(int=888))
        elif mutation=='close_asset' and not is_position and row['side']=='sell':row['asset_id']=str(UUID(int=888))
        elif mutation=='backdated_submission' and not is_position and row['id']==order(index=1)['id']:row['submitted_at']='2023-11-24T14:30:00Z'
        elif mutation=='future_submission' and not is_position and row['id']==order(index=1)['id']:row['submitted_at']=at(10)
        elif mutation=='numeric_fill_price_change' and not is_position and row['id']==order(index=2)['id'] and observed>=at(24):row.update(filled_qty='1.0',filled_avg_price='81')
    with pytest.raises(ContractError):check_fixture_walkthrough(**transform_sequence(args,change))


def test_equivalent_nonterminal_fill_format_preserves_unchanged_price():
    def change(row,is_position,observed):
        if not is_position and row['id']==order(index=2)['id'] and observed>=at(24):row['filled_qty']='1.0'
    p=check_fixture_walkthrough(**transform_sequence(sequence(recovery_fill=True),change)).to_payload()
    assert p['closed_quantity']==2 and p['fixture_final_empty'] is True
