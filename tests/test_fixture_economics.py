"""Controlled local ledgers. Arithmetic alone never supplies source authority."""
import copy,hashlib
from decimal import localcontext
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_paper_reconciliation import inputs

AFTER='2023-11-24T15:00:00Z'
UNTIL='2023-11-24T15:30:00Z'
ASSET='22222222-2222-4222-8222-222222222222'

def seal(value):
    header={k:v for k,v in value.items() if k not in {'events','event_count','ledger_head_sha256','opening_sha256','history_sha256','covered_until'}}
    head=hashlib.sha256(canonical(header)).hexdigest()
    for index,event in enumerate(value['events'],1):
        event.update(sequence=index,previous_sha256=head)
        event.pop('sha256',None)
        head=hashlib.sha256(canonical(event)).hexdigest();event['sha256']=head
    value.update(event_count=len(value['events']),ledger_head_sha256=head)
    return value

def example():
    original=inputs();original.update(current_cash='999.98',activities=(dict(id='fixture::fee-one',activity_type='FEE',date='2023-11-24',net_amount='-0.02'),))
    ledger=seal(dict(version=1,purpose='CONTROLLED_LOCAL_ECONOMICS',project_id=original['project_id'],
        account_alias=original['account_alias'],opening_sha256='a'*64,history_sha256='b'*64,
        asset_id=ASSET,symbol='SPY',opening_cash=original['opening_cash'],covered_after=AFTER,covered_until=UNTIL,
        fee_rules=[dict(rule_id='account-fee',kind='FIXED_USD_PER_EVENT',rate='0.02',currency='USD'),
                   dict(rule_id='transactions',kind='ZERO_TRANSACTION_FEES',rate='0',currency='USD')],
        action_events=[],events=[
            dict(event_id='accrual-one',kind='ACCRUAL',at='2023-11-24T15:01:00Z',rule_id='account-fee',amount='0.02'),
            dict(event_id='payment-one',kind='PAYMENT',at='2023-11-24T15:02:00Z',accrual_id='accrual-one',activity_id='fixture::fee-one',amount='0.02')]))
    return dict(originals=original,ledger=ledger,opening_sha256='a'*64,history_sha256='b'*64,
                asset_id=ASSET,symbol='SPY',required_after=AFTER,required_until=UNTIL)

def calculate(value=None):
    from compertum.fixture_economics import calculate_fixture_economics
    return calculate_fixture_economics(**(example() if value is None else value)).to_payload()

def test_complete_local_payment_preserves_cash_and_proves_no_actual_authority():
    value=example();before=copy.deepcopy(value);result=calculate(value)
    assert value==before
    assert result['outstanding_fees']=='0' and result['paid_fees']=='0.02'
    assert result['cash_matches'] is True and result['observed_cash']=='999.98'
    assert result['local_action_calendar_empty'] is True
    assert result['scope']=='UNQUALIFIED_LOCAL_ECONOMIC_CALCULATION'
    assert result['source_qualified'] is result['financial_accepted'] is result['transport_authorized'] is False

def test_unpaid_accrual_stays_outstanding():
    value=example();value['ledger']['events'].pop();seal(value['ledger'])
    value['originals'].update(current_cash='1000',activities=())
    result=calculate(value)
    assert result['outstanding_fees']=='0.02' and result['paid_fees']=='0'

def test_unlinked_credit_cannot_cancel_unpaid_accrual():
    value=example();value['ledger']['events'][-1]=dict(event_id='fixture::credit-one',kind='UNLINKED_CREDIT',at='2023-11-24T15:02:00Z',activity_id='fixture::fee-one',amount='0.02')
    seal(value['ledger']);value['originals']['activities'][0]['net_amount']='0.02';value['originals']['current_cash']='1000.02'
    result=calculate(value)
    assert result['outstanding_fees']=='0.02' and result['unlinked_credits']=='0.02'

def test_payment_reversal_restores_liability_once():
    value=example();value['ledger']['events'].append(dict(event_id='reversal-one',kind='REVERSAL',at='2023-11-24T15:03:00Z',event_id_reversed='payment-one',activity_id='fixture::credit-one',amount='0.02'))
    seal(value['ledger']);value['originals']['activities']+= (dict(id='fixture::credit-one',activity_type='FEE',date='2023-11-24',net_amount='0.02'),)
    value['originals']['current_cash']='1000'
    result=calculate(value)
    assert result['outstanding_fees']=='0.02' and result['paid_fees']=='0'

def test_cancel_unpaid_accrual_keeps_every_original_event():
    value=example();value['ledger']['events'][-1]=dict(event_id='cancel-one',kind='REVERSAL',at='2023-11-24T15:02:00Z',event_id_reversed='accrual-one',activity_id=None,amount='0.02')
    seal(value['ledger']);value['originals'].update(current_cash='1000',activities=())
    assert calculate(value)['outstanding_fees']=='0' and len(value['ledger']['events'])==2

@pytest.mark.parametrize('field,bad',[
    ('purpose','ACTUAL_ACCOUNT'),('version',True),('project_id','c'*64),('account_alias','other'),
    ('opening_sha256','c'*64),('history_sha256','c'*64),('asset_id','33333333-3333-4333-8333-333333333333'),
    ('symbol','QQQ'),('opening_cash','999'),('covered_after','2023-11-24T15:00:01Z'),
    ('covered_until','2023-11-24T15:29:59Z'),('event_count',1),('ledger_head_sha256','c'*64),
],ids=['purpose','version','project','alias','opening','history','asset','symbol','cash','late-start','early-end','missing-event','head'])
def test_changed_or_incomplete_original_binding_refuses(field,bad):
    value=example();value['ledger'][field]=bad
    with pytest.raises(RuntimeRefused):calculate(value)

@pytest.mark.parametrize('kind',['SPLIT','DIVIDEND','SYMBOL_CHANGE','UNKNOWN'])
def test_relevant_or_unsupported_action_refuses(kind):
    value=example();value['ledger']['action_events']=[dict(kind=kind,asset_id=ASSET)]
    seal(value['ledger'])
    with pytest.raises(RuntimeRefused):calculate(value)

@pytest.mark.parametrize('problem',['duplicate-id','unknown-accrual','excess-payment','wrong-cash-sign','unknown-rule','wrong-rule-amount','reversed-order','duplicate-payment-link'])
def test_bad_event_or_payment_link_refuses(problem):
    value=example();ledger=value['ledger'];events=ledger['events']
    if problem=='duplicate-id':events[1]['event_id']=events[0]['event_id']
    elif problem=='unknown-accrual':events[1]['accrual_id']='absent'
    elif problem=='excess-payment':events[1]['amount']='0.03'
    elif problem=='wrong-cash-sign':value['originals']['activities'][0]['net_amount']='0.02'
    elif problem=='unknown-rule':events[0]['rule_id']='absent'
    elif problem=='wrong-rule-amount':events[0]['amount']='0.03'
    elif problem=='reversed-order':events.reverse()
    else:events.append(dict(events[1],event_id='payment-two'))
    seal(ledger)
    with pytest.raises(RuntimeRefused):calculate(value)

def test_hostile_decimal_settings_do_not_round_original_amounts():
    with localcontext() as context:
        context.prec=2
        assert calculate()['paid_fees']=='0.02'

def test_calculation_revalidates_immutable_original_bytes():
    from compertum.fixture_economics import calculate_fixture_economics
    result=calculate_fixture_economics(**example())
    assert '999.98' not in repr(result)
    original=result.content;object.__setattr__(result,'content',original.replace(b'999.98',b'999.97'))
    with pytest.raises(RuntimeRefused):result.to_payload()

def purchase_example():
    from test_paper_reconciliation import purchased
    value=example();fee=value['originals']['activities'][0]
    value['originals'].update(purchased())
    value['originals']['activities']+=(fee,);value['originals']['current_cash']='849.98'
    value['symbol']=value['ledger']['symbol']='AAPL';seal(value['ledger'])
    return value

def test_original_purchase_matches_covered_security():
    result=calculate(purchase_example())
    assert result['cash_matches'] and result['observed_cash']=='849.98'

@pytest.mark.parametrize('field,bad',[('symbol','SPY'),('asset_id','33333333-3333-4333-8333-333333333333')])
def test_original_purchase_cannot_use_another_security_calendar(field,bad):
    value=purchase_example();value[field]=value['ledger'][field]=bad;seal(value['ledger'])
    with pytest.raises(RuntimeRefused):calculate(value)
