"""Pure reconciliation; callers must authenticate opening and attempt guard.

Applies only to bounded invented broker evidence.
"""
from decimal import Decimal,DecimalException,Context,localcontext,ROUND_HALF_EVEN,InvalidOperation,DivisionByZero,Overflow
import re
from uuid import UUID,uuid5,NAMESPACE_URL
from compertum.domain import ExecutionIntent,ContractError
from compertum.execution_risk import client_order_id
from compertum.execution_contracts import TERMINAL
from compertum.simulation.policy import number
from compertum.runtime.errors import RuntimeRefused

CODE='FAKE_ECONOMIC_RECONCILIATION'
ORDER_FIELDS={'order_id','client_order_id','symbol','side','quantity','filled_quantity','filled_notional','status','owned'}
def require(value):
 if not value:raise RuntimeRefused(CODE)
def money(value):
 require(type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]{0,20})(?:\.[0-9]{1,8})?',value) is not None)
 return Decimal(value)
def positions(value):
 require(type(value) is dict and len(value)<=64)
 require(all(type(s) is str and re.fullmatch('[A-Z]{1,8}',s) and type(q) is int and 0<=q<=1000000000 for s,q in value.items()))
 return {s:q for s,q in value.items() if q}

def reconcile(opening,evidence,snapshot):
 try:
  # Inputs have <=21 integer and8 fractional digits;512 event deltas need <=32 digits.
  context=Context(prec=40,rounding=ROUND_HALF_EVEN,Emin=-999999,Emax=999999,capitals=1,clamp=0,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow])
  with localcontext(context):return _reconcile(opening,evidence,snapshot)
 except (KeyError,ValueError,TypeError,AttributeError,ContractError,DecimalException):raise RuntimeRefused(CODE) from None

def _reconcile(opening,evidence,s):
 require(type(opening) is dict and set(opening)=={'account_alias','cash','positions'})
 account=opening['account_alias'];require(type(account) is str and re.fullmatch(r'fake-[a-z0-9_-]{1,48}',account))
 cash=money(opening['cash']);owned=positions(opening['positions'])
 require(type(evidence) is dict and evidence['status']=='VERIFIED' and type(evidence['records']) is list and len(evidence['records'])<=256)
 require(type(s) is dict and set(s)=={'scope','account_alias','cash','positions','orders','events','event_sequence','calls'})
 require(s['scope']=='DETERMINISTIC_FAKE' and s['account_alias']==account)
 broker_cash=money(s['cash']);broker_positions=positions(s['positions'])
 require(type(s['orders']) is list and len(s['orders'])<=256 and type(s['events']) is list and len(s['events'])<=512)
 require(type(s['calls']) is list and len(s['calls'])<=512 and type(s['event_sequence']) is int and s['event_sequence']==len(s['events']))
 known={};cancels={};clients=set()
 for record in evidence['records']:
  i=ExecutionIntent(record['intent']);p=i.to_payload();client=client_order_id(i)
  require(p['account_alias']==account and record['client_order_id']==client and client not in clients);clients.add(client)
  if p['kind']=='CANCEL':cancels.setdefault(p['order_id'],[]).append(p)
  else:
   oid=str(uuid5(NAMESPACE_URL,'compertum-fixture:'+account+':'+client))
   require(oid not in known);known[oid]={'order_id':oid,'client_order_id':client,'symbol':p['symbol'],'side':p['side'],'quantity':p['quantity']}
 for oid,items in cancels.items():
  require(oid in known and all(p['symbol']==known[oid]['symbol'] and p['account_alias']==account for p in items))
 def order(value):
  require(type(value) is dict and set(value)==ORDER_FIELDS and value['order_id'] in known)
  require(all(value[k]==v for k,v in known[value['order_id']].items()) and value['owned'] is True)
  q=value['filled_quantity'];total=value['quantity'];require(type(total) is int and type(q) is int and 0<=q<=total)
  n=money(value['filled_notional']);status=value['status'];require(status in TERMINAL|{'ACKNOWLEDGED','PARTIALLY_FILLED'})
  require((q==0)==(n==0))
  if status=='ACKNOWLEDGED':require(q==0)
  elif status=='PARTIALLY_FILLED':require(0<q<total)
  elif status=='FILLED':require(q==total)
  elif status=='CANCELED':require(q<total and value['order_id'] in cancels)
  elif status=='REJECTED':require(q==0)
  elif status=='EXPIRED':require(q<total)
  return q,n
 latest={};event_ids=set()
 for sequence,event in enumerate(s['events'],1):
  require(type(event) is dict and set(event)=={'sequence','event_id','order'} and type(event['sequence']) is int and event['sequence']==sequence)
  eid=event['event_id'];require(type(eid) is str and str(UUID(eid))==eid and UUID(eid).int!=0 and eid not in event_ids);event_ids.add(eid)
  v=event['order'];q,n=order(v);oid=v['order_id'];prior=latest.get(oid)
  if prior is None:
   require(v['status']=='ACKNOWLEDGED' and q==0 and n==0);old_q=0;old_n=Decimal(0)
  else:
   require(prior['status'] not in TERMINAL);old_q=prior['filled_quantity'];old_n=money(prior['filled_notional'])
   require(q>=old_q and n>=old_n and ((q==old_q)==(n==old_n)))
   require(v!=prior and (q>old_q or v['status'] in TERMINAL))
  delta=q-old_q;cost=n-old_n;sign=1 if v['side']=='buy' else -1
  symbol=v['symbol'];owned[symbol]=owned.get(symbol,0)+sign*delta;cash-=sign*cost
  require(owned[symbol]>=0 and cash>=0);latest[oid]=v
 final={}
 for v in s['orders']:
  order(v);oid=v['order_id'];require(oid not in final);final[oid]=v
 require(final==latest)
 owned={symbol:q for symbol,q in owned.items() if q}
 require(owned==broker_positions and abs(broker_cash-cash)<=Decimal('.01'))
 return {'expected_cash':number(cash),'owned_positions':owned,'cash_difference':number(broker_cash-cash),'orders':len(final),'events':len(s['events'])}
