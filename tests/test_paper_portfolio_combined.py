"""Native stores/DPAPI and loopback market; simulated origin, clocks and reserves."""
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_input_context import inputs,confirmed,context
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication
from test_paper_account_binding import invented_paper_origin,call,confirm


def test_borrows_exact_combined_context_and_close_preserves_market(confirmed):
    from compertum.runtime.paper_portfolio_context import _portfolio_context
    o,*_=confirmed;c=context(confirmed);market=o.a._market;r=_portfolio_context(c)
    assert r._context is c and r.diagnostic()['status']=='BLOCKED'
    r.close();assert not c._closed and not market._opened._closed and not market._combined._closed
    assert c.diagnostic()['transport_authorized'] is False
    with pytest.raises(RuntimeRefused):r.diagnostic()


def test_combined_refusal_keeps_borrowed_history(confirmed):
    from compertum.runtime.paper_portfolio_context import _portfolio_context
    o,*_=confirmed;c=context(confirmed);market=o.a._market;r=_portfolio_context(c);p=r._prepare_proof()
    o.clock.utc+=31;o.clock.mono+=31
    with pytest.raises(RuntimeRefused):p._verify()
    assert r._closed and c._closed and not market._opened._closed and not market._combined._closed
