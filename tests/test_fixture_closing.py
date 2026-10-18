"""Unqualified closing arithmetic. These cases grant no native authority."""
from copy import deepcopy
from uuid import UUID,uuid5
import pytest
from compertum.runtime.errors import RuntimeRefused

ROOT='11111111-1111-4111-8111-111111111111'
TERMS=dict(symbol='MSFT',quantity=3,children=[dict(maximum_quantity=2,notional_cap='2000'),dict(maximum_quantity=1,notional_cap='1000')])

def next_child(**changes):
 from compertum.fixture_closing import next_close_child
 values=dict(root_id=ROOT,terms=deepcopy(TERMS),index=0,completed_quantity=0,active=None);values.update(changes)
 return next_close_child(**values)

def test_children_have_distinct_durable_ids_and_original_finite_caps():
 first=next_child();second=next_child(index=1,completed_quantity=2)
 assert first['intent_id']==str(uuid5(UUID(ROOT),'CLOSE_LONG:0'))
 assert first['intent_id']!=second['intent_id'] and first['quantity']==2 and second['quantity']==1
 assert first['terms']==TERMS and second['terms']==dict(symbol='MSFT',quantity=1,children=TERMS['children'][1:])
 assert next_child(index=2,completed_quantity=3) is None

@pytest.mark.parametrize('changes',[dict(index=-1),dict(index=True),dict(index=3),dict(index=1,completed_quantity=0),
 dict(index=1,completed_quantity=1),dict(index=0,completed_quantity=1),dict(completed_quantity=True),dict(active='unknown'),
 dict(index=2,completed_quantity=2),dict(root_id='invalid')])
def test_overlap_unknown_progress_and_extra_children_refuse(changes):
 with pytest.raises(RuntimeRefused):next_child(**changes)

def test_only_full_terminal_reconciliation_can_advance_a_child():
 from compertum.fixture_closing import settle_close_child
 child=next_child()
 assert settle_close_child(child,state='NATIVE_FILLED',filled_quantity=2)==dict(index=1,completed_quantity=2)

@pytest.mark.parametrize('state,quantity',[('NATIVE_UNKNOWN',0),('NATIVE_CONSUMED',0),('NATIVE_PARTIALLY_FILLED',1),
 ('NATIVE_CANCELED',0),('NATIVE_REJECTED',0),('NATIVE_FILLED',1),('NATIVE_FILLED',3),('NATIVE_FILLED',True)])
def test_uncertain_partial_or_wrong_quantity_cannot_advance(state,quantity):
 from compertum.fixture_closing import settle_close_child
 with pytest.raises(RuntimeRefused):settle_close_child(next_child(),state=state,filled_quantity=quantity)
