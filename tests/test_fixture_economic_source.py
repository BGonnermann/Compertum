"""In-process source journals. These checks supply no native source authority."""
import copy,hashlib
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_economics import example,AFTER,UNTIL

class Clock:
    value=AFTER
    def __call__(self):return self.value

def create(tmp_path):
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    header=example()['ledger'];clock=Clock()
    return ControlledEconomicSource.create(tmp_path/'source.jsonl',header,clock),clock

def snapshot(source):return source.snapshot(opening_sha256='a'*64,history_sha256='b'*64,until=source.clock())

def pay(source,clock):
    clock.value='2023-11-24T15:01:00Z'
    source.append(dict(event_id='accrual-one',kind='ACCRUAL',rule_id='account-fee',amount='0.02'))
    clock.value='2023-11-24T15:02:00Z'
    source.append(dict(event_id='payment-one',kind='PAYMENT',accrual_id='accrual-one',activity_id='fixture::fee-one',amount='0.02'))

def test_original_source_exists_before_first_observation(tmp_path):
    source,clock=create(tmp_path)
    assert source.path.read_bytes();first=snapshot(source);before=source.path.read_bytes()
    assert first['ledger']['events']==[] and first['ledger']['covered_after']==AFTER
    assert first['producer_id'] and first['genesis_sha256']==first['ledger']['ledger_head_sha256']
    assert source.observations()==dict(cash='1000',activities=())
    for _ in range(3):assert snapshot(source)==first
    assert source.path.read_bytes()==before
    source.close()

def test_durable_payment_and_original_cash_rows(tmp_path):
    source,clock=create(tmp_path);pay(source,clock)
    from compertum.fixture_economics import calculate_fixture_economics
    value=example();value['ledger']=snapshot(source)['ledger'];value['required_until']=value['ledger']['covered_until']
    observed=source.observations();value['originals'].update(current_cash=observed['cash'],activities=observed['activities'])
    result=calculate_fixture_economics(**value).to_payload()
    assert result['outstanding_fees']=='0' and result['cash_matches'] and not result['source_qualified']
    assert observed['cash']=='999.98' and observed['activities'][0]['id']=='fixture::fee-one'
    source.close()

def test_reopen_preserves_producer_head_and_events_without_replay(tmp_path):
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    source,clock=create(tmp_path);pay(source,clock)
    first=snapshot(source);path=source.path;original=path.read_bytes();source.close()
    reopened=ControlledEconomicSource.open(path,clock)
    assert snapshot(reopened)==first and reopened.observations()['cash']=='999.98'
    assert path.read_bytes()==original
    reopened.close()

@pytest.mark.parametrize('damage',['partial-tail','changed-amount','duplicate-json-key'])
def test_damaged_source_refuses_without_repair_or_truncation(tmp_path,damage):
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    source,clock=create(tmp_path);pay(source,clock);path=source.path;source.close()
    raw=path.read_bytes();(tmp_path/'original-source.jsonl').write_bytes(raw)
    if damage=='partial-tail':broken=raw+b'{'
    elif damage=='changed-amount':broken=raw.replace(b'"amount":"0.02"',b'"amount":"0.03"',1)
    else:broken=raw.replace(b'"version":1',b'"version":1,"version":1',1)
    assert broken!=raw;path.write_bytes(broken)
    with pytest.raises(RuntimeRefused):ControlledEconomicSource.open(path,clock)
    assert path.read_bytes()==broken

def test_duplicate_event_refuses_without_new_source_bytes(tmp_path):
    source,clock=create(tmp_path);pay(source,clock);raw=source.path.read_bytes()
    with pytest.raises(RuntimeRefused):source.append(dict(event_id='payment-one',kind='UNLINKED_CREDIT',activity_id='other',amount='0.02'))
    assert source.path.read_bytes()==raw;source.close()

def test_backward_clock_refuses_without_new_source_bytes(tmp_path):
    source,clock=create(tmp_path);pay(source,clock);raw=source.path.read_bytes();clock.value=AFTER
    with pytest.raises(RuntimeRefused):snapshot(source)
    assert source.path.read_bytes()==raw;source.close()

def test_file_replacement_is_blocked_or_invalidates_source(tmp_path):
    source,clock=create(tmp_path);path=source.path
    raw=path.read_bytes()
    try:path.rename(tmp_path/'original-source.jsonl')
    except PermissionError as error:
        assert error.winerror==32 and path.read_bytes()==raw
        assert snapshot(source)['ledger']['events']==[]
    else:
        path.write_bytes((tmp_path/'original-source.jsonl').read_bytes())
        with pytest.raises(RuntimeRefused):snapshot(source)
    source.close()

def test_existing_source_is_never_replaced(tmp_path):
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    source,clock=create(tmp_path);raw=source.path.read_bytes()
    with pytest.raises(RuntimeRefused):ControlledEconomicSource.create(source.path,example()['ledger'],clock)
    assert source.path.read_bytes()==raw;source.close()

def test_closed_source_cannot_supply_observations(tmp_path):
    source,clock=create(tmp_path);source.close()
    with pytest.raises(RuntimeRefused):snapshot(source)

def test_source_cannot_claim_an_earlier_birth_time(tmp_path):
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    header=example()['ledger'];clock=Clock();clock.value='2023-11-24T15:20:00Z'
    source=ControlledEconomicSource.create(tmp_path/'source.jsonl',header,clock)
    assert snapshot(source)['ledger']['covered_after']==clock.value
    from compertum.fixture_economics import calculate_fixture_economics
    value=example();value['ledger']=snapshot(source)['ledger'];value['required_until']=value['ledger']['covered_until']
    with pytest.raises(RuntimeRefused):calculate_fixture_economics(**value)
    source.close()

def test_source_cannot_claim_future_coverage(tmp_path):
    source,clock=create(tmp_path);raw=source.path.read_bytes()
    with pytest.raises(RuntimeRefused):source.snapshot(opening_sha256='a'*64,history_sha256='b'*64,until=UNTIL)
    assert source.path.read_bytes()==raw;source.close()

def test_reopen_cannot_insert_events_inside_acknowledged_coverage(tmp_path):
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    source,clock=create(tmp_path);pay(source,clock);clock.value='2023-11-24T15:10:00Z'
    assert snapshot(source)['ledger']['covered_until']==clock.value
    path=source.path;source.close();raw=path.read_bytes();clock.value='2023-11-24T15:05:00Z'
    with pytest.raises(RuntimeRefused):ControlledEconomicSource.open(path,clock)
    assert path.read_bytes()==raw

@pytest.mark.parametrize('when',['open','live'])
def test_additional_hard_link_refuses_without_changing_either_name(tmp_path,when):
    import os
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    source,clock=create(tmp_path);path=source.path;raw=path.read_bytes()
    if when=='open':source.close()
    alias=tmp_path/'retained-source.jsonl';os.link(path,alias)
    assert path.stat().st_nlink==2 and alias.read_bytes()==raw
    try:
        with pytest.raises(RuntimeRefused):
            if when=='open':ControlledEconomicSource.open(path,clock)
            else:snapshot(source)
        assert path.read_bytes()==alias.read_bytes()==raw
    finally:source.close()

@pytest.mark.parametrize('reopen',[False,True])
def test_event_at_closed_coverage_end_refuses(tmp_path,reopen):
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    source,clock=create(tmp_path);pay(source,clock);clock.value='2023-11-24T15:10:00Z';snapshot(source)
    if reopen:
        path=source.path;source.close();source=ControlledEconomicSource.open(path,clock)
    raw=source.path.read_bytes()
    try:
        with pytest.raises(RuntimeRefused):source.append(dict(event_id='late-fee',kind='ACCRUAL',rule_id='account-fee',amount='0.02'))
        assert source.path.read_bytes()==raw
    finally:source.close()

def test_event_after_closed_coverage_survives_reopen(tmp_path):
    from helpers.stateful_economic_fixture import ControlledEconomicSource
    source,clock=create(tmp_path);pay(source,clock);clock.value='2023-11-24T15:10:00Z';first=snapshot(source)
    path=source.path;source.close();source=ControlledEconomicSource.open(path,clock)
    assert snapshot(source)==first
    clock.value='2023-11-24T15:10:01Z'
    source.append(dict(event_id='next-fee',kind='ACCRUAL',rule_id='account-fee',amount='0.02'))
    assert len(snapshot(source)['ledger']['events'])==3
    source.close()
