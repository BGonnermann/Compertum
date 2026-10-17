"""Controlled order decoder review one. Every source and order is invented."""
from copy import deepcopy
import json
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_journal import example,append,changed,decode,sha

def test_buy_limit_fill_cannot_exceed_its_exact_limit():
 raw,record,observed=example(resting=True)
 fill=dict(id='trade::'+observed['id'],activity_type='FILL',order_id=observed['id'],transaction_time='2026-10-17T19:00:03Z',
  type='fill',symbol='MSFT',side='buy',qty='1',cum_qty='1',leaves_qty='0',price='81')
 # Keep the original acceptance and append a distinct later fill transaction.
 events=[dict(kind='ORDER_FILLED',order=dict(observed,status='filled',filled_qty='1',filled_avg_price='81'),fill=fill),
  dict(kind='CASH_MOVEMENT',order_id=observed['id'],fill_id=fill['id'],currency='USD',amount='-81')]
 # One accepted request may receive later fills with a new transaction identity.
 from test_fixture_order_journal import seal
 from uuid import uuid4,uuid5,UUID
 tx=json.loads(append(raw,record,events,at='2026-10-17T19:00:03Z').splitlines()[-1]);tx['transaction_id']=str(uuid4())
 for index,event in enumerate(tx['events']):event['event_id']=str(uuid5(UUID(tx['transaction_id']),'event:'+str(index)))
 with pytest.raises(RuntimeRefused):decode(raw+canonical(seal(tx))+b'\n')

@pytest.mark.parametrize('before',['consumption','source'])
def test_submission_cannot_precede_its_authority_or_empty_beginning(before):
 raw,_,_=example()
 def damage(tx):
  record=tx['attempt'];p=record['intent']
  if before=='consumption':record['attempted_at']='2026-10-17T19:00:02Z'
  else:
   p['created_at']=p['request']['created_at']='2026-10-17T18:59:59Z';p['expires_at']='2026-10-17T19:00:59Z'
   for event in tx['events']:
    if 'order' in event:event['order']['submitted_at']='2026-10-17T18:59:59Z'
   p['request_sha256']=sha(p['request']);record['decision']['intent_sha256']=sha(p)
 with pytest.raises(RuntimeRefused):decode(changed(raw,damage))

def test_fill_identity_must_pass_the_original_activity_cursor_contract():
 raw,_,_=example()
 def damage(tx):tx['events'][1]['fill']['id']=tx['events'][2]['fill_id']='x'
 with pytest.raises(RuntimeRefused):decode(changed(raw,damage))
