"""Real Windows handle cleanup. Source identity and HTTP replies are simulated."""
import ctypes as c
from dataclasses import asdict
from types import SimpleNamespace
import pytest
from test_paper_read_owner import owner,pair,connect,prepare,approve,start,command
from compertum.runtime.errors import RuntimeRefused

def attach(o,monkeypatch):
 from compertum.runtime import fixture_source_binding as binding
 identity=asdict(o.e.lease.identity);producer='11111111-1111-4111-8111-111111111111';genesis='a'*64
 ledger=dict(account_alias='fixture',asset_id='12345678-1234-4234-8234-123456789099',symbol='MSFT',opening_cash='1000')
 monkeypatch.setattr(binding,'native_source_peer',lambda *a:dict(identity=identity))
 monkeypatch.setattr(binding,'source_file',lambda *a:(dict(producer_id=producer,genesis_sha256=genesis,ledger=ledger),[1,'0'*32]))
 origin=dict(ledger,initial_cash='1000',economic_producer_id=producer,economic_genesis_sha256=genesis)
 monkeypatch.setattr(binding,'order_source_file',lambda *a:(dict(origin=origin),[1,'1'*32]))
 value=binding._SourceStart(o.e.lease,o.calls[0].request,49100,_factory=binding._FACTORY)
 o.calls[0]._fixture_source_start=value
 return value,value.pin.get()

def open_handle(value,raw):
 flags=c.c_uint32();return bool(value.api.GetHandleInformation(raw,c.byref(flags)))

@pytest.mark.parametrize('terminal',['cancel','timeout','malformed','owner-close','cleanup-refusal'])
def test_terminal_read_closes_its_actual_process_pin(owner,monkeypatch,terminal):
 o=owner;p=prepare(o);approve(o,p);start(o,p);o.a.tick()
 value,raw=attach(o,monkeypatch);assert open_handle(value,raw)
 if terminal=='cancel':assert command(o,'cancel',packet_id=p['packet_id'])['state']=='CANCELED'
 elif terminal=='owner-close':o.a.close()
 elif terminal=='cleanup-refusal':
  def failed():raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')
  o.calls[0].close=failed
  with pytest.raises(RuntimeRefused):o.a.close()
 else:
  if terminal=='timeout':
   def failed():raise RuntimeRefused('PIPE_DEADLINE_EXCEEDED')
   o.calls[0].poll=failed
  else:o.calls[0].poll=lambda:SimpleNamespace(status_code=200,body=b'not json')
  o.a.tick()
  assert command(o,'status',packet_id=p['packet_id'])['state']=='ABORTED'
 assert value.closed and not open_handle(value,raw)
 assert value not in o.a._guard.resources

def test_success_keeps_the_pin_through_provenance_then_closes_it(owner,monkeypatch):
 from compertum.runtime import paper_preflight
 o=owner;p=prepare(o);approve(o,p);start(o,p);o.a.tick()
 value,raw=attach(o,monkeypatch);observed=[]
 def provenance(transport,result,lease,request):
  assert transport.native_closed and not value.closed and open_handle(value,raw)
  observed.append(True)
  return dict(request_sha256=request.sha256,raw_sha256=__import__('hashlib').sha256(result.body).hexdigest(),origin='UNVERIFIED_TRANSPORT')
 monkeypatch.setattr(paper_preflight,'native_read_provenance',provenance)
 o.a.tick()
 assert observed==[True] and value.closed and not open_handle(value,raw)
