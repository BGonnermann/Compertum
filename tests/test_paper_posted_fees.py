"""Invented posted USD fees. Matching arithmetic never establishes complete billing."""
import copy,json
from decimal import Decimal,Inexact,localcontext
import pytest

from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_paper_reconciliation import inputs,purchased,example
from test_native_attempt_records import attempt
from test_paper_portfolio import position


def fee(**changes):
    value=dict(id='20231124::posted-fee-1',activity_type='FEE',date='2023-11-24',net_amount='-0.02')
    value.update(changes)
    return value


def calculation(**changes):
    from compertum.paper_posted_fees import calculate_posted_fees
    value=inputs();value.update(changes)
    return calculate_posted_fees(**value)


def calculate(**changes):
    return calculation(**changes).to_payload()


def test_original_posted_debit_explains_cash_without_changing_originals():
    value=purchased();value.update(current_cash='849.98',activities=(*value['activities'],fee()))
    before=copy.deepcopy(value);result=calculate(**value)
    assert value==before
    assert result['opening_cash']=='1000' and result['observed_cash']=='849.98'
    assert result['fill_expected_cash']=='850' and result['expected_cash']=='849.98'
    assert result['unadjusted_cash_difference']=='-0.02' and result['cash_difference']=='0'
    assert result['posted_debits']=='0.02' and result['posted_credits']=='0'
    assert result['posted_cash_effect']=='-0.02' and result['calculation_matches'] is True
    assert result['posted_fee_count']==result['posted_debit_count']==1
    assert result['actual_billed_fee'] is result['actual_flat'] is None
    assert result['financial_accepted'] is result['transport_authorized'] is False
    assert {'FEE_POSTING_INTERVAL_UNVERIFIED','FEE_LIABILITIES_UNVERIFIED','FEE_REVERSALS_UNVERIFIED'}<=set(result['deficiencies'])


def test_empty_rows_do_not_establish_zero_liability():
    result=calculate()
    assert result['expected_cash']=='1000' and result['posted_fee_count']==0
    assert result['calculation_matches'] is True and result['status']=='BLOCKED'
    assert result['actual_billed_fee'] is None and 'FEE_POSTING_INTERVAL_UNVERIFIED' in result['deficiencies']


@pytest.mark.parametrize('amount,debits,credits,debit_count,credit_count',[
    ('-0.02','0.02','0',1,0),('0.02','0','0.02',0,1),
    ('0','0','0',0,0),('-0','0','0',0,0),('-0.00','0','0',0,0),
    ('0.000000000001','0','0.000000000001',0,1),
],ids=['debit','credit','zero','negative-zero','negative-zero-cents','small-credit'])
def test_signed_effects_preserve_original_text(amount,debits,credits,debit_count,credit_count):
    observed=format(Decimal('1000')+Decimal(amount),'f')
    result=calculate(activities=(fee(net_amount=amount),),current_cash=observed)
    assert result['posted_debits']==debits and result['posted_credits']==credits
    assert result['posted_debit_count']==debit_count and result['posted_credit_count']==credit_count
    assert result['posted_fees'][0]['net_amount']==amount and result['calculation_matches']
    assert 'FEE_REVERSALS_UNVERIFIED' in result['deficiencies']


def test_a_credit_cannot_fund_an_earlier_unaffordable_purchase():
    p,d,row,fill=example(price='20')
    holding=position();holding.update(avg_entry_price='20',cost_basis='20',market_value='20')
    with pytest.raises(RuntimeRefused):
        calculate(opening_cash='10',current_cash='0',attempts=(attempt(p,d),),orders=(row,),
            positions=(holding,),activities=(fill,fee(net_amount='10')))


def test_cancelling_debit_and_credit_are_not_erased_or_called_a_reversal():
    result=calculate(activities=(fee(),fee(id='20231124::posted-fee-2',net_amount='0.02')))
    assert result['posted_cash_effect']=='0' and result['calculation_matches']
    assert result['posted_debits']==result['posted_credits']=='0.02'
    assert result['posted_debit_count']==result['posted_credit_count']==1 and result['posted_fee_count']==2
    assert result['actual_billed_fee'] is None and 'FEE_REVERSALS_UNVERIFIED' in result['deficiencies']


@pytest.mark.parametrize('date',[
    '2023-11-23','2023-11-24T14:35:00Z','2023-11-24T14:35:00.123456789Z','2000-01-01','2100-12-31',
],ids=['backdated','utc-seconds','utc-nanoseconds','first-year','last-year'])
def test_dates_never_supply_a_posting_interval(date):
    result=calculate(activities=(fee(date=date),),current_cash='999.98')
    assert result['posted_fees'][0]['date']==date and result['calculation_matches']
    assert 'FEE_POSTING_INTERVAL_UNVERIFIED' in result['deficiencies']


@pytest.mark.parametrize('changes',[
    dict(net_amount='1e2'),dict(net_amount='NaN'),dict(net_amount=True),dict(net_amount=None),
    dict(net_amount='+1'),dict(net_amount='01'),dict(net_amount='-01'),
    dict(net_amount='1.1234567890123'),dict(net_amount='100000001'),dict(net_amount='-100000001'),
    dict(date='2023-02-29'),dict(date='2023-11-24T25:00:00Z'),dict(date='2023-11-24T14:35:00+00:00'),
    dict(date='1999-12-31'),dict(date='2101-01-01'),dict(date='2023-11-24T14:35:00.1234567890Z'),
    dict(id='no-separator'),dict(description='x'*1025),dict(description=None),
    dict(currency='EUR'),dict(extra={'unknown':'value'}),dict(activity_type='CFEE'),
    dict(activity_type='DIV'),dict(activity_type='MISC'),
],ids=['exponent','nan','boolean','null','plus','leading-zero','negative-leading-zero','precision',
    'large-debit','large-credit','invalid-day','invalid-hour','offset','early-year','late-year',
    'too-many-nanoseconds','invalid-id','long-description','null-description','currency-field',
    'extra-field','crypto','dividend','unknown'])
def test_malformed_or_unsupported_fee_rows_refuse(changes):
    with pytest.raises(RuntimeRefused):calculate(activities=(fee(**changes),))


def test_missing_required_fee_date_refuses():
    value=fee();del value['date']
    with pytest.raises(RuntimeRefused):calculate(activities=(value,))


def test_description_is_retained_privately_and_bound_by_utf8_bytes():
    text='\u00e9'*512
    result=calculate(activities=(fee(description=text),),current_cash='999.98')
    assert result['posted_fees'][0]['description']==text
    with pytest.raises(RuntimeRefused):calculate(activities=(fee(description=text+'a'),))


@pytest.mark.parametrize('kind',['fee','fill'],ids=['same-kind','cross-kind'])
def test_duplicate_original_ids_refuse_before_any_fee_is_counted(kind):
    if kind=='fee':changes=dict(activities=(fee(),fee()))
    else:
        changes=purchased();original=changes['activities'][0]
        changes['activities']=(*changes['activities'],fee(id=original['id']))
    with pytest.raises(RuntimeRefused):calculate(**changes)


@pytest.mark.parametrize('kind',['row-count','combined-bytes'])
def test_combined_bounds_apply_before_filtering_or_fill_work(monkeypatch,kind):
    from compertum import paper_posted_fees as module
    def unexpected(**values):pytest.fail('Fill work ran before the combined bound.')
    monkeypatch.setattr(module,'validate_fill_history',unexpected)
    values=(fee(id=f'bounded::fee-{index}') for index in range(201))
    rows=tuple(values) if kind=='row-count' else (fee(description='x'*(1024**2)),)
    with pytest.raises(RuntimeRefused):calculate(activities=rows)


@pytest.mark.parametrize('difference,matched',[('0.01',True),('-0.01',True),('0.010000000001',False)])
def test_original_cash_tolerance_and_difference_are_retained(difference,matched):
    observed=format(Decimal('999.98')+Decimal(difference),'f')
    result=calculate(activities=(fee(),),current_cash=observed)
    assert result['cash_difference']==difference and result['calculation_matches'] is matched
    assert result['observed_cash']==observed


def test_hostile_decimal_settings_do_not_change_exact_cash():
    with localcontext() as ctx:
        ctx.prec=1;ctx.traps[Inexact]=True
        result=calculate(activities=(fee(net_amount='-0.020000000001'),),current_cash='999.979999999999')
    assert result['expected_cash']=='999.979999999999' and result['cash_difference']=='0'


def test_fee_cash_does_not_hide_a_foreign_order():
    value=purchased();value['orders'][0]['client_order_id']='foreign-client'
    value['activities']=(*value['activities'],fee())
    with pytest.raises(RuntimeRefused):calculate(**value)


def test_immutable_calculation_rejects_changed_content_and_arguments():
    result=calculation(activities=(fee(),),current_cash='999.98')
    assert '999.98' not in repr(result)
    original=result.content
    object.__setattr__(result,'content',canonical(dict(json.loads(original),financial_accepted=True)))
    with pytest.raises(RuntimeRefused):result.to_payload()
    object.__setattr__(result,'content',original)
    object.__setattr__(result,'arguments',b'{}')
    with pytest.raises(RuntimeRefused):result.to_payload()


def test_two_hundred_original_fees_above_64_kib_round_trip_without_changing_inputs():
    from compertum.paper_contracts import strict_json
    from compertum.domain import ContractError
    values=inputs()
    values.update(current_cash='996',activities=tuple(
        fee(id=f'original::fee-{index}',description='x'*400) for index in range(200)))
    original=copy.deepcopy(values)
    assert 65536<len(canonical(values))<=1024**2
    with pytest.raises(ContractError):strict_json(canonical(values))
    result=calculation(**values)
    first=result.to_payload();second=result.to_payload()
    assert values==original and first==second
    assert first['opening_cash']=='1000' and first['observed_cash']=='996'
    assert first['posted_debits']=='4' and first['posted_fee_count']==200
    assert first['posted_fees']==list(values['activities']) and first['calculation_matches']
    assert 'FEE_POSTING_INTERVAL_UNVERIFIED' in first['deficiencies']
    assert first['financial_accepted'] is first['transport_authorized'] is False


@pytest.mark.parametrize('kind',['malformed','duplicate-key','depth','nonfinite','over-one-mib'])
def test_reconstructed_arguments_refuse_invalid_json(kind):
    from compertum.paper_posted_fees import PostedFeeCalculation
    result=calculation()
    raw={
        'malformed':b'{',
        'duplicate-key':result.arguments[:-1]+b',"opening_cash":"1000"}',
        'depth':b'['*34+b'0'+b']'*34,
        'nonfinite':b'{"unexpected":NaN}',
        'over-one-mib':b' '*(1024**2+1),
    }[kind]
    with pytest.raises(RuntimeRefused):PostedFeeCalculation(raw,result.content)
