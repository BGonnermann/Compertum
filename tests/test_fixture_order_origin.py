"""The original empty inventory has no restored freshness or broker authority."""
import copy
import pytest
from compertum.data.encoding import canonical
from compertum.fixture_order_origin import POLICY,KINDS,decode_order_origin
from compertum.runtime.errors import RuntimeRefused

def origin():
 return dict(version=1,kind='ORDER_SOURCE_BEGIN',scope='CONTROLLED_LOCAL_ORDER_SOURCE',project_id='a'*64,
  producer_id='11111111-1111-4111-8111-111111111111',created_at='2026-10-17T19:00:00Z',account_alias='fixture',
  account_identity_sha256='b'*64,asset_id='12345678-1234-4234-8234-123456789099',symbol='MSFT',currency='USD',
  initial_cash='1000',economic_producer_id='22222222-2222-4222-8222-222222222222',economic_genesis_sha256='c'*64,
  initial_inventory=dict(orders=[],positions=[],fills=[]),event_kinds=copy.deepcopy(KINDS),
  event_policy=copy.deepcopy(POLICY),actual_broker_actions=False)

def test_original_inventory_and_recording_contract_are_retained():
 value=origin();result=decode_order_origin(canonical(value)+b'\n')
 assert result['origin']==value and len(result['genesis_sha256'])==len(result['journal_sha256'])==64
 assert result['genesis_sha256']!=result['journal_sha256']

@pytest.mark.parametrize('fault',['version','inventory','cash','policy','replay','producer','hash','asset','unknown','extra-line','partial','large'])
def test_changed_or_incomplete_order_beginning_refuses(fault):
 value=origin()
 if fault=='version':value['version']=True
 elif fault=='inventory':value['initial_inventory']['orders']=[{}]
 elif fault=='cash':value['initial_cash']='999.98'
 elif fault=='policy':value['event_policy']['persist_before_reply']=1
 elif fault=='replay':value['event_policy']['history_restores_freshness']=True
 elif fault=='producer':value['producer_id']='unknown'
 elif fault=='hash':value['economic_genesis_sha256']='c'*63
 elif fault=='asset':value['asset_id']='unknown'
 elif fault=='unknown':value['accepted']=True
 raw=canonical(value)+b'\n'
 if fault=='extra-line':raw+=b'{}\n'
 elif fault=='partial':raw=raw[:-1]
 elif fault=='large':raw=b'x'*16384+b'\n'
 with pytest.raises(RuntimeRefused):decode_order_origin(raw)
