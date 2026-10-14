"""Test-only managed owner: invented loopback market data and explicit fixture clocks."""
from compertum.runtime.startup import require_entrypoint_startup
proof=require_entrypoint_startup()
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import json,sys,time
from compertum.runtime import managed_owner,paper_read_owner,paper_market_owner
from compertum.runtime.paper_market_collection import _MarketCollection
from compertum.runtime.paper_market_fresh import _MarketFresh
from compertum.runtime.service_budget import _install_loopback_queue

public=json.loads(sys.argv[2]);root=Path(public['root']).resolve()
assert '.cache' in root.parts and 'test-runs' in root.parts and public['role']=='execution'
fixture=json.loads((root/'market-loopback-fixture.json').read_text())
assert set(fixture)=={'port','kind'} and fixture['kind']=='invented-native-market-test' and type(fixture['port']) is int
base=datetime.fromisoformat('2023-11-24T14:00:00+00:00').timestamp();started=time.monotonic();offset=0

def elapsed():
 return time.monotonic()-started+offset+(31 if (root/'advance-market-age.fixture').exists() else 0)
def now():return datetime.fromtimestamp(base+elapsed(),timezone.utc).isoformat()

original_init=paper_read_owner.PaperReadOwner.__init__
def initialize(self,store,reserve,health):
 clock=SimpleNamespace(ns=0);_install_loopback_queue(store.lease,lambda:clock.ns);clock.ns=60*10**9
 original_init(self,store,reserve,health)
paper_read_owner.PaperReadOwner.__init__=initialize
paper_market_owner.time=SimpleNamespace(time=lambda:base+elapsed(),monotonic=elapsed)
paper_market_owner._MarketCollection=lambda *a,**kw:_MarketCollection(*a,**kw,_test_port=fixture['port'],_test_clock=now,_test_monotonic=elapsed)
paper_market_owner._MarketFresh=lambda *a,**kw:_MarketFresh(*a,**kw,_test_port=fixture['port'],_test_clock=now,_test_monotonic=elapsed)
original_handle=paper_read_owner.PaperReadOwner.market_handle
def handle(self,packet):
 global offset
 command=packet.get('command',{})
 if command.get('operation')=='prepare' and command.get('mode')=='FRESH':offset=2100
 return original_handle(self,packet)
paper_read_owner.PaperReadOwner.market_handle=handle
managed_owner._STARTUP_PROOF=proof
raise SystemExit(managed_owner.main())
