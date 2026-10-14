"""Account-only context isolation with real local market fixture resources."""
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_input_context import inputs,history,owner,pair,native_market,publication,context as combined_context


@pytest.mark.parametrize('action',['close','replace','expire'])
def test_account_context_does_not_close_borrowed_market_resources(inputs,action):
    o,p,_,_,_=inputs;combined=combined_context(inputs);held=o.a._market._opened
    args=dict(subject='a'*64,packet_id=p['packet_id']);account=o.a.account_context(**args)
    if action=='close':account.close()
    elif action=='replace':o.a.account_context(**args)
    else:o.clock.utc+=31;o.clock.mono+=31
    with pytest.raises(RuntimeRefused):account.diagnostic()
    assert held.snapshot()['collection']['mode']=='HISTORY'
    assert o.a._input_context is combined and not combined._closed
    if action!='expire':assert combined.diagnostic()['quote_valid']
