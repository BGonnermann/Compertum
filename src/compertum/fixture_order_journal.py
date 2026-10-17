"""Committed controlled order history. Parsing alone grants no source authority."""
from decimal import Context,Decimal,Inexact,InvalidOperation,Overflow,Rounded,localcontext
import hashlib,json,re
from uuid import UUID,uuid5
from .data.encoding import canonical
from .domain import ContractError
from .fixture_order_origin import decode_order_origin
from .attempt_records import record_key
from .native_attempt_records import validate_pair
from .paper_activity_records import _FILL,_token
from .paper_contracts import number,utc
from .paper_portfolio import parse_portfolio_rows,TERMINAL
from .runtime.errors import RuntimeRefused
from .runtime.paper_read_packet import _nanoseconds

_FIELDS={'version','kind','transaction_id','sequence','previous_sha256','at','economic_head_sha256','attempt','events','sha256','commit_sha256'}
_ORDER={'id','client_order_id','asset_id','asset_class','order_class','symbol','qty','filled_qty','filled_avg_price','side','type','time_in_force','extended_hours','status','limit_price','submitted_at','legs'}
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,InvalidOperation,Inexact,Rounded)
def _need(value):
 if not value:raise RuntimeRefused('FIXTURE_ORDER_JOURNAL_UNVERIFIED')
def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def _hash(value):_need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)
def _uuid(value):_need(type(value) is str and str(UUID(value))==value)
def _text(value):
 value=format(value,'f');return value.rstrip('0').rstrip('.') if '.' in value else value
def _time(value):_need(type(value) is str and utc(value)==value);return _nanoseconds(value)
def _same(first,second):return all(first[key]==second[key] for key in _ORDER-{'status','filled_qty','filled_avg_price'})

def _order(value,begin):
 _need(type(value) is dict and set(value)==_ORDER)
 _need(value['asset_id']==begin['asset_id'] and value['symbol']==begin['symbol'])
 parsed=parse_portfolio_rows([value],dict(operation='ORDERS',parameters={'limit':25}))
 _need(not parsed['deficiencies']);_time(value['submitted_at'])
 _need(value['order_class']=='simple' and value['legs'] is None and value['extended_hours'] is False)

def decode_order_journal(raw,*,economic_heads=()):
 try:
  with localcontext(Context(prec=160,traps=[InvalidOperation,Overflow,Inexact,Rounded])):
   return _decode(raw,economic_heads)
 except _INVALID:raise RuntimeRefused('FIXTURE_ORDER_JOURNAL_UNVERIFIED') from None

def _decode(raw,economic_heads):
 _need(type(raw) is bytes and 0<len(raw)<=128*1024 and raw.endswith(b'\n'))
 lines=raw.splitlines(keepends=True);_need(1<=len(lines)<=65)
 first=decode_order_origin(lines[0]);begin=first['origin'];head=first['genesis_sha256'];last=_time(begin['created_at'])
 _need(type(economic_heads) in (tuple,list) and len(economic_heads)<=129)
 for value in economic_heads:_hash(value)
 digest=hashlib.sha256(lines[0]);prefixes=[digest.hexdigest()]
 transactions=[];tx_ids=set();event_ids=set();fill_ids=set();orders={};clients={};attempts={};outcomes={}
 fills=[];cash=Decimal(0);held=cost=Decimal(0);order_totals={}
 for sequence,line in enumerate(lines[1:],1):
  _need(len(line)<=65536 and line.endswith(b'\n'))
  tx=json.loads(line);_need(type(tx) is dict and set(tx)==_FIELDS and canonical(tx)+b'\n'==line)
  _need(type(tx['version']) is int and tx['version']==1 and tx['kind']=='ORDER_TRANSACTION')
  _need(type(tx['sequence']) is int and tx['sequence']==sequence and tx['previous_sha256']==head)
  _uuid(tx['transaction_id']);_need(tx['transaction_id'] not in tx_ids);tx_ids.add(tx['transaction_id'])
  _hash(tx['sha256']);_hash(tx['commit_sha256']);_hash(tx['economic_head_sha256'])
  _need(tx['sha256']==_sha({key:value for key,value in tx.items() if key not in {'sha256','commit_sha256'}}))
  _need(tx['commit_sha256']==_sha(dict(scope='CONTROLLED_ORDER_TRANSACTION_COMMIT_V1',transaction_sha256=tx['sha256'])))
  _need(tx['economic_head_sha256'] in economic_heads)
  at=_time(tx['at']);_need(at>=last);last=at
  record=tx['attempt'];key=record_key(record);p,d,client=validate_pair(record['intent'],record['decision'])
  _need(p['project_id']==begin['project_id'] and p['account_alias']==begin['account_alias'])
  _need(at>=_time(record['attempted_at']))
  token=p['intent_id'];previous=attempts.get(token)
  _need(previous is None or canonical(previous)==canonical(record));attempts[token]=record
  request=p['request'];operation=request['operation'];events=tx['events']
  _need(type(events) is list and 1<=len(events)<=4);pending_cash={};accepted=terminal=False
  for index,event in enumerate(events):
   _need(type(event) is dict and 'event_id' in event and 'kind' in event)
   identity=event['event_id'];_uuid(identity)
   _need(identity==str(uuid5(UUID(tx['transaction_id']),'event:'+str(index))) and identity not in event_ids);event_ids.add(identity)
   kind=event['kind'];_need(kind in begin['event_kinds'])
   if kind=='CASH_MOVEMENT':
    _need(set(event)=={'event_id','kind','order_id','fill_id','currency','amount'} and event['currency']=='USD')
    _need(event['fill_id'] in pending_cash)
    expected_order,expected_amount=pending_cash.pop(event['fill_id'])
    _need(event['order_id']==expected_order and number(event['amount'])==expected_amount)
    cash+=expected_amount;_need(Decimal(begin['initial_cash'])+cash>=0)
    continue
   fields={'event_id','kind','order'}|({'fill'} if kind in {'ORDER_FILLED','ORDER_PARTIALLY_FILLED'} else set())
   _need(set(event)==fields);row=event['order'];_order(row,begin);order_id=row['id']
   if operation=='CANCEL_ORDER':
    _need(len(events)==1 and kind in {'ORDER_CANCELED','ORDER_REJECTED'} and order_id==request['parameters']['order_id'])
    _need(order_id in orders and orders[order_id]['status'] not in TERMINAL)
    old=orders[order_id];_need(_same(old,row) and row['filled_qty']==old['filled_qty'] and row['filled_avg_price']==old['filled_avg_price'])
    _need(row['status']=='canceled' if kind=='ORDER_CANCELED' else row==old)
    orders[order_id]=row;outcomes[token]='CANCELED' if kind=='ORDER_CANCELED' else 'REJECTED';terminal=True
    continue
   body=request['body'];_need(operation=='SUBMIT_ORDER' and body['symbol']==begin['symbol'])
   _need(row['client_order_id']==client and row['qty']==body['qty'] and all(row[key]==body[key] for key in ('symbol','side','type','time_in_force','extended_hours')))
   _need(row['limit_price']==body.get('limit_price'))
   if kind in {'ORDER_ACCEPTED','ORDER_REJECTED'}:
    _need(previous is None and not accepted and order_id not in orders and client not in clients)
    _need(order_id==str(uuid5(UUID(begin['producer_id']),client)))
    _need(row['filled_qty']=='0' and row['filled_avg_price'] is None)
    _need(row['status']==('new' if kind=='ORDER_ACCEPTED' else 'rejected'))
    _need(max(_time(record['attempted_at']),_time(begin['created_at']))<=_time(row['submitted_at'])<=at)
    orders[order_id]=row;clients[client]=order_id;order_totals[order_id]=(Decimal(0),Decimal(0));accepted=True
    outcomes[token]='ACKNOWLEDGED' if kind=='ORDER_ACCEPTED' else 'REJECTED';terminal=kind=='ORDER_REJECTED'
    if terminal:_need(len(events)==1)
   else:
    _need(kind in {'ORDER_FILLED','ORDER_PARTIALLY_FILLED'} and not terminal and order_id in orders)
    old=orders[order_id];_need(old['status'] not in TERMINAL and _same(old,row))
    fill=event['fill'];_need(type(fill) is dict and set(fill)==_FILL and fill['activity_type']=='FILL')
    _token(fill['id']);_need(fill['id'] not in fill_ids);fill_ids.add(fill['id'])
    _need(fill['order_id']==order_id and fill['symbol']==begin['symbol'] and fill['side']==row['side'] and fill['transaction_time']==tx['at'])
    quantity=number(fill['qty'],positive=True);price=number(fill['price'],positive=True);total=number(row['qty'],positive=True)
    if row['type']=='limit':
     limit=number(row['limit_price'],positive=True);_need(price<=limit if row['side']=='buy' else price>=limit)
    old_quantity,old_notional=order_totals[order_id];cumulative=old_quantity+quantity;notional=old_notional+quantity*price
    _need(cumulative<=total and number(fill['cum_qty'])==cumulative and number(fill['leaves_qty'])==total-cumulative)
    complete=cumulative==total
    _need(kind==('ORDER_FILLED' if complete else 'ORDER_PARTIALLY_FILLED') and fill['type']==('fill' if complete else 'partial_fill'))
    _need(row['status']==('filled' if complete else 'partially_filled') and number(row['filled_qty'])==cumulative and number(row['filled_avg_price'])==notional/cumulative)
    if row['side']=='buy':held+=quantity;cost+=quantity*price;effect=-quantity*price
    else:
     _need(row['side']=='sell' and 0<quantity<=held);cost-=cost*quantity/held;held-=quantity;effect=quantity*price
    _need(held>=0 and cost>=0)
    orders[order_id]=row;order_totals[order_id]=(cumulative,notional);fills.append(fill)
    pending_cash[fill['id']]=(order_id,effect);outcomes[token]='FILLED' if complete else 'PARTIALLY_FILLED';terminal=complete
  _need(not pending_cash)
  # A new request has one explicit acceptance, cancellation, or rejection.
  if previous is None:
   _need(accepted or operation=='CANCEL_ORDER' and terminal)
   # A future explicit denial records its actual time. It cannot authorize or
   # backdate acceptance, and its stable client remains denied thereafter.
   if outcomes[token]!='REJECTED':_need(at-_time(record['attempted_at'])<=10*10**9)
  else:_need(not accepted and operation=='SUBMIT_ORDER' and any(event['kind'] in {'ORDER_FILLED','ORDER_PARTIALLY_FILLED'} for event in events))
  head=tx['sha256'];transactions.append(tx);digest.update(line);prefixes.append(digest.hexdigest())
 positions=[]
 if held:
  positions.append(dict(asset_id=begin['asset_id'],symbol=begin['symbol'],asset_class='us_equity',qty=_text(held),side='long',avg_entry_price=_text(cost/held),cost_basis=_text(cost)))
 result=dict(first,origin=begin,journal_sha256=digest.hexdigest(),prefix_sha256=prefixes,head_sha256=head,
  transaction_count=len(transactions),transactions=transactions,attempts=list(attempts.values()),request_outcomes=outcomes,cash_delta=_text(cash),
  inventory=dict(orders=sorted(orders.values(),key=lambda row:(row['submitted_at'],row['id'])),positions=positions,fills=fills),
  source_qualified=False,financial_accepted=False,transport_authorized=False)
 return json.loads(canonical(result))
