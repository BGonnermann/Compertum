"""Test-only steps after authenticated native presence inspection."""
from copy import deepcopy
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import require_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_fixture_orders import install_fixture_orders
from compertum.runtime.paper_fixture_closing import accept_fixture_close
from compertum.runtime.paper_fixture_reconciliation import reconcile_fixture_orders

def need(value):
 if not value:raise RuntimeRefused('CONTROLLED_REHEARSAL_STEP_REFUSED')

class RehearsalOwner:
 def __init__(self,owner,plan):
  self.owner=owner;self.plan=deepcopy(plan);self.component=install_fixture_orders(owner)
  self.parent=None;self.producer=None;self.states={};self.closed=False
 def close(self):
  if self.closed:return
  self.closed=True
  if self.producer is not None:self.producer.close()
  if self.parent is not None:self.parent.close()
 def handle(self,packet,result):
  key=packet['request_id'];step=self.plan['steps'].get(key)
  if step is None:return result
  need(not self.closed and packet['command']==dict(operation='inspect',presence_id=step['presence_id']))
  need(result['presence_status']=='CURRENT' and result['packet_id']==step['packet_id'])
  state=self.states.setdefault(key,dict(status='NEW',scope='CONTROLLED_LOCAL_REHEARSAL',transport_authorized=False,financial_accepted=False))
  if state['status'] not in {'DONE','REFUSED'}:
   try:self._advance(step,packet['subject_key'],state)
   except RuntimeRefused as error:
    if self.producer is not None:self.producer.close();self.producer=None
    state.update(status='REFUSED',reason=error.code)
  return dict(result,fixture_step=deepcopy(state))
 def _advance(self,step,subject,state):
  op=step['operation'];owner=self.owner
  if op=='halt':
   need(self.producer is None)
   before=canonical(require_attempt_guard(owner.store));self.component.close()
   need(self.component.closed and self.component.active is None and all(p.closed for p in self.component.parents.values()))
   try:self.component.prepare(subject=subject,intent_id=step['intent_id'],activity_id=step['activity_id'])
   except RuntimeRefused as error:need(error.code=='FIXTURE_ORDER_CONTEXT_CHANGED')
   else:raise RuntimeRefused('CONTROLLED_CLOSED_DISPATCH_ACCEPTED')
   try:install_fixture_orders(owner)
   except RuntimeRefused as error:need(error.code=='FIXTURE_ORDER_COMPONENT_ALREADY_INSTALLED')
   else:raise RuntimeRefused('CONTROLLED_CLOSED_COMPONENT_REINSTALLED')
   need(canonical(require_attempt_guard(owner.store))==before)
   state.update(status='DONE',native_component_closed=True,dispatch_refused=True,reinstall_refused=True,guard_unchanged=True);return
  if op=='replay':
   before=canonical(require_attempt_guard(owner.store));candidate=None
   original=owner._intents._read(step['intent_id'])
   need(original['owner_generation']!=owner.lease.generation and original['owner_instance']!=owner.lease.identity.process_instance_id)
   try:
    candidate=self.component.prepare(subject=subject,intent_id=step['intent_id'],activity_id=step['activity_id'])
    value=candidate.dispatch()
   except RuntimeRefused as error:
    need(canonical(require_attempt_guard(owner.store))==before)
    state.update(status='DONE',old_grant_refused=True,reason_code=error.code);return
   finally:
    if candidate is not None:candidate.close()
   raise RuntimeRefused('CONTROLLED_REPLAY_NOT_EVALUATED' if value=='WAITING' else 'CONTROLLED_REPLAY_UNEXPECTEDLY_ACCEPTED')
  if op in {'dispatch','close'}:
   if state['status']=='NEW':
    need(self.producer is None)
    if op=='close':
     need(self.parent is None)
     self.parent=accept_fixture_close(owner,subject=subject,intent_id=step['intent_id'],activity_id=step['activity_id'])
     state['status']='PARENT_ACCEPTED';return
    else:self.producer=self.component.prepare(subject=subject,intent_id=step['intent_id'],activity_id=step['activity_id'])
    state['status']='WAITING';return
   if state['status']=='PARENT_ACCEPTED':
    self.producer=self.parent.prepare_child(subject=subject,packet_id=step['packet_id'],fresh_job_id=step['fresh_job_id'],capture_id=step['capture_id'],
     activity_id=step['activity_id'],presence_id=step['presence_id'])
    state['status']='WAITING';return
   p=self.producer
   if state['status']=='WAITING':
    if p.dispatch()=='WAITING':return
    state['status']='PENDING';return
   need(state['status']=='PENDING')
   try:
    reply=p.poll()
    if reply is None:return
    state.update(status='DONE',dispatch=reply,reply_lost=False)
   except RuntimeRefused:
    need(step.get('expect_lost_reply') is True and hasattr(p,'_p'))
    record=self.component.journal._row(p._p['account_alias'],p._p['intent_id'])
    need(record['intent']==p._p and record['status']=='NATIVE_CONSUMED')
    state.update(status='DONE',reply_lost=True,effect_status='UNKNOWN_REQUIRES_ORIGINAL_SOURCE',intent_id=p._p['intent_id'])
   finally:
    if state['status']=='DONE':p.close();self.producer=None
   return
  if op=='reconcile':
   value=reconcile_fixture_orders(owner,subject=subject,packet_id=step['packet_id'],activity_id=step['activity_id'],presence_id=step['presence_id'])
   need(value['unresolved_count']==0);state.update(status='DONE',reconciliation=value);return
  need(op=='finish' and self.parent is not None)
  value=self.parent.finish(subject=subject,packet_id=step['packet_id'],activity_id=step['activity_id'],presence_id=step['presence_id'])
  need(value['fixture_flat'] is True and value['status']=='COMPLETE');state.update(status='DONE',closing=value)
