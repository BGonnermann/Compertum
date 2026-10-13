"""Independent accounting/policy over a small invented fixed-price fixture."""
from copy import deepcopy
from functools import lru_cache
import json
import pytest
from compertum.audit_generated_final import _replay
from compertum.audit_predictions import SourceEvidence
from compertum.data.errors import DataError
from compertum.modeling.registry import variant
from compertum.modeling.generated_final import _GeneratedCandidate
from compertum.modeling.generated_fits import _Vectors
from compertum.simulation.engine import _replay_market
from compertum.simulation.market import load_market
from helpers.simulation_fixture import fixture,SECTORS


@lru_cache(maxsize=1)
def accounting_case():
 chunks,start,end,all_dates=fixture(scored=8);market=load_market(chunks,SECTORS);c=variant('momentum-h01');author=_GeneratedCandidate(market,c,None,_Vectors(market))
 replay=json.loads(_replay_market(author,start,end,1,cost_bps=10).content);replay['portfolios']['strategy']=replay['portfolios'].pop('momentum')
 dates=[d for d in all_dates if start<=d<=end]
 return market,c,dates,dict(start=start,end=end),replay


def check(replay):
 market,c,dates,annual,_=accounting_case()
 return _replay(SourceEvidence(market),c,dates,annual,replay,None,None,None,10)


def test_fixed_price_accounting_reconstruction_and_exact_trade_policy():
 _,_,dates,_,replay=accounting_case();navs,recorded,checks=check(replay)
 assert checks['recorded_fill_accounting']=='VERIFIED_PASS'
 assert navs==recorded and all(len(v)==len(dates)+1 for v in navs.values())
 assert checks['portfolios']['zero']['ending_nav']=='10000'
 assert checks['policy']['first_eligible_index']==0
 assert checks['portfolios']['strategy']['trades']>0


@pytest.mark.parametrize('fault',['cash','nav','return','quantity','fee','signal','checkpoint','horizon','cost','market','sector','authority','extra_book'])
def test_balanced_or_rehashed_claim_does_not_replace_original_accounting(fault):
 replay=deepcopy(accounting_case()[-1]);book=replay['portfolios']['strategy']
 if fault=='cash':book['days'][0]['cash']='999999'
 elif fault=='nav':book['days'][0]['nav']='999999'
 elif fault=='return':book['metrics']['returns'][0]='0.9'
 elif fault=='quantity':book['trades'][0]['quantity']+=1
 elif fault=='fee':book['trades'][0]['fee']='1'
 elif fault=='signal':book['signals'][0]['predictions']['AAPL']='0.9'
 elif fault=='checkpoint':book['checkpoints'].pop()
 elif fault=='horizon':replay['horizon']=5
 elif fault=='cost':replay['cost_bps']=20
 elif fault=='market':replay['market_sha256']='0'*64
 elif fault=='sector':replay['sectors']['AAPL']='invented'
 elif fault=='authority':replay['financial_accepted']=True
 else:book['verified']=True
 with pytest.raises(DataError):check(replay)
