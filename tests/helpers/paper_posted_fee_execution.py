"""Test-only activity owner; account origin is invented and activity origin stays loopback."""
from compertum.runtime.startup import require_entrypoint_startup
proof=require_entrypoint_startup()
import json,sys,time,os
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

# Test-only observations. No method grants order authority.
from compertum.runtime import paper_posted_fee_context as fee_module
original_calculator=fee_module.calculate_posted_fees
calculator_calls=[]
def counted_calculator(**values):
 result=original_calculator(**values);calculator_calls.append(True);return result
fee_module.calculate_posted_fees=counted_calculator
original_activity_handle=paper_activity_owner._ActivityOwner.handle
observations={}
records=Path(__file__).parents[2]/'artifacts/m5/posted-fees-20261017-01/native-posted-fees'

def phase_record(phase,started,error=None):
 value=dict(phase=phase,elapsed_seconds=time.monotonic()-started,error_type=None if error is None else type(error).__name__,
  error_code=getattr(error,'code',None))
 path=records/f'proof-phases-{os.getpid()}.jsonl'
 assert not path.exists() or path.stat().st_size<16384
 with path.open('a',encoding='utf-8') as stream:stream.write(json.dumps(value)+'\n')

def fee_observation(self,packet):
 # Publication acknowledgement stays passive. Each status call performs one
 # phase inside the unchanged five-second owner exchange.
 result=original_activity_handle(self,packet)
 if packet['command']['operation']!='status' or result['state']!='PUBLISHED':return result
 identity=result['activity_id'];state=observations.setdefault(identity,dict(phase='CREATE',context=None,proof=None,public={}))
 phase=state['phase'];started=time.monotonic();error=None
 try:
  if phase=='CREATE':
   value=self._read(identity)
   state['context']=self.o.posted_fee_context(subject=value['subject'],packet_id=value['packet_id'],activity_id=identity)
   state['phase']='PREPARE'
  elif phase=='PREPARE':state['proof']=state['context']._prepare_proof();state['phase']='VERIFY'
  elif phase=='VERIFY':
   fee_proof=state['proof'];state['public']['fixture_posted_fee']=fee_proof._verify()
   state['public']['fixture_calculator_calls']=len(calculator_calls)
   try:fee_proof._verify()
   except paper_read_owner.RuntimeRefused as refused:
    assert refused.code=='PAPER_FINAL_PROOF_CONSUMED';state['public']['fixture_single_use_refused']=True
   else:raise AssertionError('Reused fee proof accepted')
   state['phase']='DONE'
 except paper_read_owner.RuntimeRefused as refused:
  error=refused;state['public']={'fixture_posted_fee_error':refused.code};state['phase']='DONE'
 except BaseException as failed:
  error=failed;raise
 finally:
  if phase!='DONE':phase_record(phase,started,error)
  if state['phase']=='DONE' and state['context'] is not None:state['context'].close();state['context']=None
 result.update(state['public']);result['fixture_fee_phase']=state['phase']
 return result
paper_activity_owner._ActivityOwner.handle=fee_observation
managed_owner._STARTUP_PROOF=proof
raise SystemExit(managed_owner.main())
