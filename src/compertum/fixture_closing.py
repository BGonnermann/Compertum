"""Finite closing arithmetic. A returned child carries no execution authority."""
from uuid import UUID,uuid5
from .runtime.errors import RuntimeRefused
from .runtime.paper_native_intent_terms import exact_terms

def _need(value):
 if not value:raise RuntimeRefused('FIXTURE_CLOSING_PROGRESS_UNVERIFIED')

def next_close_child(*,root_id,terms,index,completed_quantity,active):
 try:
  _need(type(root_id) is str and str(UUID(root_id))==root_id)
  _need(exact_terms('CLOSE_LONG',terms,stored=True)==terms)
  children=terms['children'];_need(type(index) is int and 0<=index<=len(children))
  _need(type(completed_quantity) is int and completed_quantity==sum(c['maximum_quantity'] for c in children[:index]))
  _need(active is None)
  if index==len(children):
   _need(completed_quantity==terms['quantity']);return None
  remaining=dict(symbol=terms['symbol'],quantity=terms['quantity']-completed_quantity,children=children[index:])
  _need(exact_terms('CLOSE_LONG',remaining,stored=True)==remaining)
  return dict(intent_id=str(uuid5(UUID(root_id),'CLOSE_LONG:'+str(index))),index=index,
   completed_quantity=completed_quantity,quantity=children[index]['maximum_quantity'],terms=remaining)
 except (ValueError,TypeError,KeyError,AttributeError):raise RuntimeRefused('FIXTURE_CLOSING_PROGRESS_UNVERIFIED') from None

def settle_close_child(child,*,state,filled_quantity):
 _need(state=='NATIVE_FILLED' and type(filled_quantity) is int and filled_quantity==child['quantity'])
 return dict(index=child['index']+1,completed_quantity=child['completed_quantity']+filled_quantity)
