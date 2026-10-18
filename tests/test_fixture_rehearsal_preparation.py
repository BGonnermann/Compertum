"""Preparation checks with invented peers and bounded in-process operations."""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace

def test_account_embedded_ledger_matches_original_after_observations(tmp_path,monkeypatch):
 from helpers import fixture_rehearsal_source as module
 from helpers.stateful_economic_fixture import ControlledEconomicSource
 from compertum.fixture_source_journal import decode_source_journal
 from test_fixture_economics import example
 current=datetime(2026,10,17,tzinfo=timezone.utc)
 def clock():
  nonlocal current
  from compertum.paper_contracts import utc
  current+=timedelta(milliseconds=1);return utc(current.isoformat())
 @dataclass
 class InventedPeer:pid:int=1
 source=ControlledEconomicSource.create(tmp_path/'original.jsonl',example()['ledger'],clock)
 app=object.__new__(module.OriginalSourceServer);app.economic=source
 app.project=SimpleNamespace(project_id='0'*64,logon_sid='UNQUALIFIED_TEST_PEER')
 app.supervisor=SimpleNamespace(supervisor=SimpleNamespace(generation=1,identity=InventedPeer()))
 app.orders=SimpleNamespace(observations=lambda:dict(source.observations(),positions=[]),
  snapshot=lambda:dict(producer_id='invented',genesis_sha256='a'*64,journal_sha256='b'*64))
 monkeypatch.setattr(module,'stamp',clock)
 try:
  reply=app.read('/v2/account');original=decode_source_journal(source.path.read_bytes())
  assert reply['compertum_fixture_source']['ledger']==original['ledger']
  assert reply['compertum_fixture_source']['ledger']['covered_until']==original['ledger']['covered_until']
 finally:source.close()

def test_close_preparation_retains_one_operation_per_presence_call(monkeypatch):
 from helpers import fixture_rehearsal_owner as module
 calls=[];producer=SimpleNamespace(dispatch=lambda:calls.append('dispatch') or 'WAITING')
 parent=SimpleNamespace(prepare_child=lambda **kw:calls.append('prepare_child') or producer)
 monkeypatch.setattr(module,'accept_fixture_close',lambda *a,**kw:calls.append('accept') or parent)
 hook=object.__new__(module.RehearsalOwner);hook.owner=object();hook.parent=None;hook.producer=None
 step=dict(operation='close',intent_id='root',activity_id='activity',packet_id='packet',fresh_job_id='fresh',capture_id='capture',presence_id='presence')
 state={'status':'NEW'}
 for expected in ('accept','prepare_child','dispatch'):
  before=len(calls);hook._advance(step,'a'*64,state)
  assert calls[before:]==[expected]

def test_native_driver_reserves_cleanup_inside_unchanged_job_limit():
 from windows.test_paper_fixture_dispatch_control import Driver,WORK_SECONDS,CLEANUP_SECONDS,FRAMEWORK_SECONDS
 driver=Driver(None)
 assert WORK_SECONDS+CLEANUP_SECONDS+FRAMEWORK_SECONDS==120
 assert WORK_SECONDS<=88 and CLEANUP_SECONDS>=17 and FRAMEWORK_SECONDS>=15
 assert driver.end==driver.started+WORK_SECONDS
 assert driver.cleanup_end==driver.end+CLEANUP_SECONDS

def test_source_stamp_uses_product_canonical_utc():
 from helpers.fixture_rehearsal_source import stamp
 from compertum.paper_contracts import utc
 value=stamp();assert value==utc(value)
