"""Native economic test owner. Every account value is invented and local."""
from compertum.runtime.startup import require_entrypoint_startup
proof=require_entrypoint_startup()
import json,os,sys,time
from pathlib import Path
import traceback
def failed_start(kind,value,frames):
 path=Path(__file__).parents[2]/'artifacts/m5/native-economics-20261017-01'/f'economic-child-failure-{os.getpid()}.json'
 with path.open('x') as stream:json.dump(dict(error_type=kind.__name__,frames=[dict(file=x.filename,line=x.lineno,function=x.name) for x in traceback.extract_tb(frames)],values_recorded=False),stream)
sys.excepthook=failed_start
from compertum.runtime import managed_owner,paper_read_owner,paper_activity_owner,paper_preflight
from compertum.runtime.fixture_source_binding import start_fixture_get,native_source_peer
from compertum.runtime.paper_activity_owner import _ActivityProducer
from compertum.runtime.service_budget import _install_loopback_queue
public=json.loads(sys.argv[2]);root=Path(public['root']).resolve();master=Path(__file__).parents[2]
expected=master/'.cache/test-runs/native-economic-fresh-20261017-01/native-shared'
with (master/'artifacts/m5/native-economics-20261017-01'/f'economic-path-{os.getpid()}.json').open('x') as stream:
 json.dump(dict(literal_path_match=root==expected,same_native_directory=os.path.samefile(root,expected)),stream)
assert os.path.samefile(root,expected) and public['role']=='execution'
fixture=json.loads((root/'loopback-fixture.json').read_text())
assert set(fixture)=={'port','kind','foreign_port'} and fixture['kind']=='original-native-economic-test'
original_init=paper_read_owner.PaperReadOwner.__init__
def fixture_init(self,store,reserve,health):
 class Clock:
  ns=0
  def __call__(self):return self.ns
 clock=Clock();_install_loopback_queue(store.lease,clock);clock.ns=60*10**9
 original_init(self,store,reserve,health)
paper_read_owner.PaperReadOwner.__init__=fixture_init
def local_get(lease,request,protected,timeout,*,_permit=None):
 return start_fixture_get(lease,request,fixture['port'],timeout,_permit=_permit)
paper_read_owner._start_get=local_get
paper_activity_owner._new_producer=lambda *a,**kw:_ActivityProducer(*a,**kw,_test_port=fixture['port'])
original_origin=paper_preflight.native_read_provenance
# This test-only substitution permits an invented immutable opening.
# The source guard still checks the actual Windows peer and original bytes.
paper_preflight.native_read_provenance=lambda *a:dict(original_origin(*a),origin='PAPER_TLS')
original_handle=paper_activity_owner._ActivityOwner.handle;observations={}
records=master/'artifacts/m5/native-economics-20261017-01'
def economic_observation(self,packet):
 result=original_handle(self,packet)
 if packet['command']['operation']!='status' or result['state']!='PUBLISHED':return result
 identity=result['activity_id'];state=observations.setdefault(identity,dict(phase='CREATE',context=None,proof=None,public={}))
 phase=state['phase'];started=time.monotonic();error=None
 try:
  if phase=='CREATE':
   value=self._read(identity)
   try:native_source_peer(self.o.lease,fixture['foreign_port'])
   except paper_read_owner.RuntimeRefused:state['public']['fixture_foreign_listener_refused']=True
   else:raise AssertionError('Foreign process listener accepted')
   state['context']=self.o.fixture_economic_context(subject=value['subject'],packet_id=value['packet_id'],activity_id=identity)
   state['phase']='PREPARE'
  elif phase=='PREPARE':state['proof']=state['context']._prepare_proof();state['phase']='VERIFY'
  elif phase=='VERIFY':
   economic=state['proof'];state['public']['fixture_economic']=economic._verify()
   try:economic._verify()
   except paper_read_owner.RuntimeRefused as refused:
    assert refused.code=='PAPER_FINAL_PROOF_CONSUMED';state['public']['fixture_single_use_refused']=True
   else:raise AssertionError('Reused economic proof accepted')
   state['phase']='DONE'
 except paper_read_owner.RuntimeRefused as refused:
  error=refused;state['public']['fixture_economic_error']=refused.code;state['phase']='DONE'
 finally:
  if phase!='DONE':
   path=records/f'economic-phases-{os.getpid()}.jsonl'
   assert not path.exists() or path.stat().st_size<16384
   with path.open('a') as stream:stream.write(json.dumps(dict(phase=phase,elapsed_seconds=time.monotonic()-started,error_code=getattr(error,'code',None)))+'\n')
  if state['phase']=='DONE' and state['context'] is not None:state['context'].close();state['context']=None
 result.update(state['public']);result['fixture_economic_phase']=state['phase'];return result
paper_activity_owner._ActivityOwner.handle=economic_observation
managed_owner._STARTUP_PROOF=proof
raise SystemExit(managed_owner.main())
