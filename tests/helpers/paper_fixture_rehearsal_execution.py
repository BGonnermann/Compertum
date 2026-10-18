"""Native test owner. Only the optional market clock can use simulated time."""
from compertum.runtime.startup import require_entrypoint_startup
proof=require_entrypoint_startup()
import hashlib,json,os,sys,traceback
from pathlib import Path
root=Path(json.loads(sys.argv[2])['root']).resolve();master=Path(__file__).parents[2]
assert root==master/'.cache/test-runs/native-economic-fresh-20261017-01/native-shared'
sys.path.insert(0,str(master/'tests'))
fixture=json.loads((root/'loopback-fixture.json').read_text());assert fixture['kind']=='controlled-native-rehearsal'
plan_path=Path(fixture['plan_path']);assert plan_path.parent==master/'artifacts/m5/risk-dispatch-20261017-01'
raw=plan_path.read_bytes();assert hashlib.sha256(raw).hexdigest()==fixture['plan_sha256'];plan=json.loads(raw)
clock=None
if plan.get('market_clock') is not None:
 from helpers.fixture_market_clock import clock_for_plan
 clock_path=Path(fixture['market_clock_path']).resolve()
 assert clock_path==plan_path.with_name(plan_path.stem+'-clock.json')
 clock_raw=clock_path.read_bytes();assert len(clock_raw)<=4096
 assert hashlib.sha256(clock_raw).hexdigest()==fixture['market_clock_sha256']
 clock=clock_for_plan(plan,json.loads(clock_raw),plan_sha256=fixture['plan_sha256'])
def failed(kind,value,frames):
 target=plan_path.parent/f'rehearsal-child-failure-{os.getpid()}.json'
 with target.open('x') as out:json.dump(dict(error_type=kind.__name__,values_recorded=False,
  frames=[dict(file=f.filename,line=f.lineno,function=f.name) for f in traceback.extract_tb(frames)]),out)
sys.excepthook=failed
from compertum.runtime import managed_owner,paper_read_owner,paper_activity_owner,paper_preflight,paper_market_owner,paper_presence
from compertum.runtime.fixture_source_binding import start_fixture_get
from compertum.runtime.paper_activity_owner import _ActivityProducer
from compertum.runtime.paper_market_collection import _MarketCollection
from compertum.runtime.paper_market_fresh import _MarketFresh
from compertum.runtime.service_budget import queue_for
from helpers.fixture_rehearsal_owner import RehearsalOwner
original_init=paper_read_owner.PaperReadOwner.__init__;original_close=paper_read_owner.PaperReadOwner.close
def initialize(self,*args,**kwargs):
 original_init(self,*args,**kwargs);self._rehearsal=RehearsalOwner(self,plan)
def close(self):
 if hasattr(self,'_rehearsal'):self._rehearsal.close()
 original_close(self)
paper_read_owner.PaperReadOwner.__init__=initialize;paper_read_owner.PaperReadOwner.close=close
original_read=paper_read_owner.PaperReadOwner.handle
def read(self,packet):
 result=original_read(self,packet)
 if packet['command']['operation']=='status':result=dict(result,fixture_queue=queue_for(self.lease).status())
 return result
paper_read_owner.PaperReadOwner.handle=read
paper_read_owner._start_get=lambda lease,request,protected,timeout,**kw:start_fixture_get(lease,request,fixture['port'],timeout,**kw)
paper_activity_owner._new_producer=lambda *a,**kw:_ActivityProducer(*a,**kw,_test_port=fixture['port'])
paper_market_owner._MarketCollection=lambda *a,**kw:_MarketCollection(*a,**kw,_test_port=fixture['port'])
paper_market_owner._MarketFresh=lambda *a,**kw:_MarketFresh(*a,**kw,_test_port=fixture['port'])
original_origin=paper_preflight.native_read_provenance
# The immutable opening is invented. This test-only marker grants no actual access.
paper_preflight.native_read_provenance=lambda *a:dict(original_origin(*a),origin='PAPER_TLS')
original_handle=paper_presence._PresenceOwner.handle
def handle(self,packet):return self.parent._rehearsal.handle(packet,original_handle(self,packet))
paper_presence._PresenceOwner.handle=handle
managed_owner._STARTUP_PROOF=proof
if clock is None:raise SystemExit(managed_owner.main())
from helpers.fixture_market_clock import owner_market_clock
with owner_market_clock(clock):raise SystemExit(managed_owner.main())
