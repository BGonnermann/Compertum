"""Test-only activity owner; account origin is invented and activity origin stays loopback."""
from compertum.runtime.startup import require_entrypoint_startup
proof=require_entrypoint_startup()
import json,sys
from pathlib import Path
from compertum.runtime import managed_owner,paper_read_owner
from compertum.runtime._winhttp_get import _OwnedGet
public=json.loads(sys.argv[2]);root=Path(public['root']).resolve()
assert '.cache' in root.parts and 'test-runs' in root.parts and public['role']=='execution'
fixture=json.loads((root/'loopback-fixture.json').read_text())
assert set(fixture)=={'port','kind'} and fixture['kind']=='invented-native-read-test' and type(fixture['port']) is int

def local_get(lease,request,protected,timeout,*,_permit=None):
 return _OwnedGet(lease,host='127.0.0.1',port=fixture['port'],secure=False,path=request.to_payload()['target'],headers={'X-Compertum-Test':'synthetic'},timeout=timeout,_permit=_permit,_read_request=request)

from compertum.runtime.service_budget import _install_loopback_queue
original_init=paper_read_owner.PaperReadOwner.__init__
def fixture_init(self,store,reserve,health):
 class Clock:
  ns=0
  def __call__(self):return self.ns
 clock=Clock();_install_loopback_queue(store.lease,clock);clock.ns=60*10**9
 original_init(self,store,reserve,health)
paper_read_owner.PaperReadOwner.__init__=fixture_init
paper_read_owner._start_get=local_get
original_public=paper_read_owner.PaperReadOwner._public

def expose_fixture_preflight(self,value):
 result=original_public(self,value);result['fixture_preflight']=None
 if self._preflight is not None:
  try:result['fixture_preflight']=self.preflight(value['packet_id']).diagnostic()
  except paper_read_owner.RuntimeRefused as error:result['fixture_preflight_error']=error.code
 return result

paper_read_owner.PaperReadOwner._public=expose_fixture_preflight
from compertum.runtime import paper_activity_owner,paper_preflight
from compertum.runtime.paper_activity_owner import _ActivityProducer
paper_activity_owner._new_producer=lambda *a,**kw:_ActivityProducer(*a,**kw,_test_port=fixture['port'])
original_origin=paper_preflight.native_read_provenance
# This fixture-only substitution permits an invented immutable opening.
# Native activity provenance remains LOOPBACK_FIXTURE.
paper_preflight.native_read_provenance=lambda *a:dict(original_origin(*a),origin='PAPER_TLS')

# Test-only observation. No production route exposes this private context.
original_activity_public=paper_activity_owner._ActivityOwner._public
def reconciliation_observation(self,value):
 result=original_activity_public(self,value)
 if value['state']=='PUBLISHED':
  context=None
  try:
   context=self.o.reconciliation_context(subject=value['subject'],packet_id=value['packet_id'],activity_id=value['activity_id'])
   proof=context._prepare_proof()
   result['fixture_reconciliation']=proof._verify()
   try:proof._verify()
   except paper_read_owner.RuntimeRefused as error:
    assert error.code=='PAPER_FINAL_PROOF_CONSUMED'
    result['fixture_single_use_refused']=True
   else:raise AssertionError('Reused proof accepted')
  except paper_read_owner.RuntimeRefused as error:result['fixture_reconciliation_error']=error.code
  finally:
   if context is not None:context.close()
 return result
paper_activity_owner._ActivityOwner._public=reconciliation_observation

managed_owner._STARTUP_PROOF=proof
raise SystemExit(managed_owner.main())
