"""Invented source replies use the pinned calendar and exact consumed header."""
from datetime import datetime,timezone
import pytest
from compertum.runtime.errors import RuntimeRefused

@pytest.mark.parametrize('stamp,opened,next_open,next_close',[
 ('2026-10-17T18:00:00+00:00',False,'2026-10-19T13:30:00+00:00','2026-10-19T20:00:00+00:00'),
 ('2026-10-19T13:20:00+00:00',False,'2026-10-19T13:30:00+00:00','2026-10-19T20:00:00+00:00'),
 ('2026-10-19T13:36:00+00:00',True,'2026-10-20T13:30:00+00:00','2026-10-19T20:00:00+00:00'),
 ('2026-10-19T20:01:00+00:00',False,'2026-10-20T13:30:00+00:00','2026-10-20T20:00:00+00:00'),
])
def test_clock_reply_uses_exact_pinned_session(stamp,opened,next_open,next_close):
 from helpers.fixture_rehearsal_source import clock_reply
 value,calendar=clock_reply(datetime.fromisoformat(stamp))
 assert value==dict(timestamp=stamp,is_open=opened,next_open=next_open,next_close=next_close)
 assert calendar==([] if stamp.startswith('2026-10-17') else [dict(date='2026-10-19',open='09:30',close='16:00')])

def test_controlled_write_header_requires_exact_client_and_both_heads():
 from helpers.fixture_rehearsal_source import write_header
 client='cmp-'+'c'*40
 assert write_header('synthetic_'+client+'_'+'a'*64+'_'+'b'*64)==(client,('a'*64,'b'*64))

@pytest.mark.parametrize('header',['synthetic','synthetic_cmp-abc_a_b','other_cmp-abc_'+'a'*64+'_'+'b'*64,
 'synthetic_cmp-abc_'+'a'*64+'_'+'b'*64+'_extra','synthetic_cmp-abc_'+'A'*64+'_'+'b'*64])
def test_malformed_controlled_write_header_refuses(header):
 from helpers.fixture_rehearsal_source import write_header
 with pytest.raises(RuntimeRefused):write_header(header)

def test_account_reply_handles_original_decoded_nonempty_position():
 """Pure reply fields with an invented peer. This grants no native authority."""
 from dataclasses import dataclass
 from decimal import Decimal
 from types import SimpleNamespace
 from helpers.fixture_rehearsal_source import OriginalSourceServer
 from test_fixture_order_journal import example,decode
 @dataclass
 class InventedPeer:pid:int=1
 raw,_,_=example();orders=decode(raw);inventory=orders['inventory'];cash=str(Decimal('1000')+Decimal(orders['cash_delta']))
 assert len(inventory['positions'])==1 and 'market_value' not in inventory['positions'][0]
 app=object.__new__(OriginalSourceServer)
 app.project=SimpleNamespace(project_id='0'*64,logon_sid='UNQUALIFIED_TEST_PEER')
 app.supervisor=SimpleNamespace(supervisor=SimpleNamespace(generation=1,identity=InventedPeer()))
 app.economic=SimpleNamespace(snapshot=lambda **kw:dict(producer_id='invented',genesis_sha256='a'*64,ledger={}))
 app.orders=SimpleNamespace(snapshot=lambda:orders,observations=lambda:dict(cash=cash,**inventory))
 account=app.read('/v2/account')
 assert account['cash']==cash and Decimal(account['equity'])==Decimal(cash)+sum(Decimal(p['qty'])*90 for p in inventory['positions'])
