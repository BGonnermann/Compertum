import hashlib,json
from dataclasses import replace
from decimal import Decimal as D
from functools import lru_cache
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.modeling.candidate import CandidateResult,evaluate_candidate
from compertum.modeling.scorecards import build_scorecard,FailedFold,_rank_key
from helpers.model_campaign_fixture import campaign_fixture,SECTORS

@lru_cache(maxsize=4)
def result(year=2021,candidate='momentum-h01'):
    c,ts,te,s,e,a=campaign_fixture(year)
    return evaluate_candidate(c,SECTORS,ts,te,s,e,candidate,scoring_as_of=a)

def mutate(value,edit):
    v=json.loads(value.content);edit(v);raw=canonical(v)
    return CandidateResult(raw,hashlib.sha256(raw).hexdigest())

def test_all_registered_slots_exist_before_evidence():
    v=json.loads(build_scorecard([]).content)
    assert len(v['candidates'])==12 and len(v['search_history'])==36
    assert v['counts']=={'completed':0,'failed':0,'pending':36}
    assert v['shortlist']==[] and v['financial_accepted'] is False

def test_terminal_failure_is_retained_and_not_a_missing_success():
    v=json.loads(build_scorecard([],failures=[FailedFold('ridge-h21-a100',2022,'INPUT_BOUND')]).content)
    assert v['counts']=={'completed':0,'failed':1,'pending':35}
    row=next(c for c in v['candidates'] if c['candidate_id']=='ridge-h21-a100')
    assert row['state']=='FAILED' and row['failed_folds'][0]['reason']=='INPUT_BOUND'

def test_concat_returns_does_not_create_annual_nav_reset_jump():
    results=[result(y) for y in [2021,2022,2023]];report=json.loads(build_scorecard(results).content)
    row=next(c for c in report['candidates'] if c['candidate_id']=='momentum-h01');returns=[];bench=[];pred=[];targets=[]
    for r in results:
        v=json.loads(r.content);p=v['replays']['10']['portfolios'];previous=D(10000);previous_b=previous
        for a,b in zip(p['strategy']['days'],p['spy60']['days']):
            returns.append(D(a['nav'])/previous-1);bench.append(D(b['nav'])/previous_b-1);previous=D(a['nav']);previous_b=D(b['nav'])
        pred.extend(D(x['prediction']) for x in v['prediction_report']['rows']);targets.extend(D(x['target']) for x in v['prediction_report']['rows'])
    expected=252*sum(a-b for a,b in zip(returns,bench))/len(returns)
    assert abs(D(row['trading']['10']['metrics']['annual_mean_excess'])-expected)<D('1e-24')
    assert row['state']=='COMPLETE_DIAGNOSTIC' and row['trading']['10']['observations']==93
    assert abs(D(row['prediction']['metrics']['mse'])-sum((a-b)**2 for a,b in zip(pred,targets))/len(pred))<D('1e-24')
    assert row['prediction']['coverage']['candidate_rows']==93*12
    assert report['diagnostic_rankings']['1']==['momentum-h01'] and report['shortlist']==[]
    assert build_scorecard(tuple(reversed(results))).content==build_scorecard(results).content

@pytest.mark.parametrize('edit',[
    lambda v:v.update(year=True),
    lambda v:v.update(financial_accepted=True),
    lambda v:v['prediction_report']['coverage'].update(candidate_rows=93),
    lambda v:v['prediction_report']['metrics'].update(mse='0'),
    lambda v:v['replays']['10']['portfolios']['strategy']['metrics'].update(annual_mean_excess='0'),
    lambda v:v['replays']['20'].update(cost_bps=10),
    lambda v:v['prediction_report']['rows'][0].update(symbol='FAKE'),
])
def test_semantic_corruption_rejected_even_with_new_hash(edit):
    with pytest.raises(DataError):build_scorecard([mutate(result(),edit)])

def test_hash_duplicate_conflicting_and_year_source_inputs_rejected():
    a=result()
    with pytest.raises(DataError):build_scorecard([replace(a,content=a.content+b' ')])
    with pytest.raises(DataError):build_scorecard([a,a])
    with pytest.raises(DataError):build_scorecard([a],failures=[FailedFold('momentum-h01',2021,'FAILED')])
    b=result(2021,'ridge-h01-a001')
    with pytest.raises(DataError):build_scorecard([a,mutate(b,lambda v:v.update(market_sha256='0'*64))])

def test_tie_rule_is_return_then_turnover_then_momentum_then_id():
    def row(id,excess='0.1',turnover='1'):
        return {'candidate_id':id,'trading':{'10':{'metrics':{'annual_mean_excess':excess},'total_turnover':turnover}}}
    rows=[row('ridge-h01-a010'),row('ridge-h01-a001'),row('momentum-h01'),row('ridge-h01-a100',turnover='.5'),row('ridge-h05-a001',excess='.2')]
    assert [r['candidate_id'] for r in sorted(rows,key=_rank_key)]==['ridge-h05-a001','ridge-h01-a100','momentum-h01','ridge-h01-a001','ridge-h01-a010']

def test_rehashed_momentum_report_cannot_contradict_its_baseline():
    from compertum.simulation.prediction import error_metrics
    from compertum.simulation.policy import number
    def edit(v):
        report=v['prediction_report']
        for row in report['rows']:
            row['prediction']=number(D(row['prediction'])+D('.01'))
            row['signed_error']=number(D(row['prediction'])-D(row['target']))
        report['metrics']=error_metrics([D(r['prediction']) for r in report['rows']],[D(r['target']) for r in report['rows']])
    with pytest.raises(DataError):build_scorecard([mutate(result(),edit)])
