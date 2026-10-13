"""Test-only native managed execution entry point; fixed loopback replacement."""
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
managed_owner._STARTUP_PROOF=proof
raise SystemExit(managed_owner.main())
