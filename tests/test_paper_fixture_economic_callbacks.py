"""Calculator callbacks cannot replace original facts with a zero liability."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from test_paper_fixture_economics import context,simulated_source,published_activity,pair,connect,owner,publication,invented_paper_origin,account,activity,activity_publication
from test_fixture_economics import seal
from compertum.runtime.errors import RuntimeRefused

@pytest.fixture
def outstanding_source(simulated_source,monkeypatch):
 from compertum.runtime import paper_fixture_economics as module
 original=module._source_snapshot
 def outstanding(*args):
  values,pin,check=original(*args);ledger=values['ledger']
  now=datetime.fromisoformat(ledger['covered_until'].replace('Z','+00:00'))
  rule=next(r for r in ledger['fee_rules'] if r['kind']=='FIXED_USD_PER_EVENT')
  ledger['events']=[dict(event_id='outstanding-original',kind='ACCRUAL',amount=rule['rate'],rule_id=rule['rule_id'],
   at=(now-timedelta(seconds=1)).isoformat().replace('+00:00','Z'))]
  seal(ledger)
  return values,pin,check
 monkeypatch.setattr(module,'_source_snapshot',outstanding)
 return simulated_source

def test_original_outstanding_accrual_remains_outstanding(outstanding_source):
 value=context(outstanding_source)
 assert value.diagnostic()['fee_liability_status']=='OUTSTANDING_CONTROLLED_FEES'

@pytest.mark.parametrize('phase',['construction','recapture'])
def test_calculator_cannot_remove_original_accrual(outstanding_source,monkeypatch,phase):
 from compertum.runtime import paper_fixture_economics as module
 value=context(outstanding_source) if phase=='recapture' else None
 original=module.calculate_fixture_economics
 def changed(**values):
  values['ledger']['events']=[];seal(values['ledger'])
  return original(**values)
 monkeypatch.setattr(module,'calculate_fixture_economics',changed)
 with pytest.raises(RuntimeRefused):
  if value is None:context(outstanding_source)
  else:value.diagnostic()
 if value is not None:assert value._closed
