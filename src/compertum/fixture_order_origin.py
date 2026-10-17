"""Original controlled order inventory. This parser grants no authority."""
import hashlib
from uuid import UUID
from .data.encoding import canonical
from .paper_contracts import identifier,strict_json,utc
from .runtime.errors import RuntimeRefused

POLICY=dict(persist_before_reply=True,append_only=True,stable_client_order_ids=True,hash_chained=True,
 no_event_replay=True,all_cash_changes_recorded=True,history_restores_freshness=False)
KINDS=['ORDER_ACCEPTED','ORDER_PARTIALLY_FILLED','ORDER_FILLED','ORDER_CANCELED','ORDER_REJECTED','CASH_MOVEMENT']
FIELDS={'version','kind','scope','project_id','producer_id','created_at','account_alias','account_identity_sha256',
 'asset_id','symbol','currency','initial_cash','economic_producer_id','economic_genesis_sha256',
 'initial_inventory','event_kinds','event_policy','actual_broker_actions'}

def decode_order_origin(raw):
 try:
  def need(value):
   if not value:raise RuntimeRefused('FIXTURE_ORDER_ORIGIN_UNVERIFIED')
  need(type(raw) is bytes and 0<len(raw)<=16384 and raw.endswith(b'\n') and raw.count(b'\n')==1)
  value=strict_json(raw);need(type(value) is dict and set(value)==FIELDS and canonical(value)+b'\n'==raw)
  need(type(value['version']) is int and value['version']==1 and value['kind']=='ORDER_SOURCE_BEGIN')
  need(value['scope']=='CONTROLLED_LOCAL_ORDER_SOURCE' and value['actual_broker_actions'] is False)
  for key in ('producer_id','economic_producer_id','asset_id'):identifier(value[key]);need(str(UUID(value[key]))==value[key])
  for key in ('project_id','account_identity_sha256','economic_genesis_sha256'):
   need(type(value[key]) is str and len(value[key])==64 and all(c in '0123456789abcdef' for c in value[key]))
  need(value['created_at']==utc(value['created_at']) and value['account_alias']=='fixture')
  need(value['currency']=='USD' and value['initial_cash']=='1000' and value['symbol']=='MSFT')
  need(canonical(value['initial_inventory'])==canonical(dict(orders=[],positions=[],fills=[])))
  need(canonical(value['event_policy'])==canonical(POLICY) and value['event_kinds']==KINDS)
  return dict(producer_id=value['producer_id'],genesis_sha256=hashlib.sha256(canonical(value)).hexdigest(),
   journal_sha256=hashlib.sha256(raw).hexdigest(),origin=value)
 except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):
  raise RuntimeRefused('FIXTURE_ORDER_ORIGIN_UNVERIFIED') from None
