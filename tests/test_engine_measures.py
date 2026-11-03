"""Candidate measures, part 1 (docs/CANDIDATE_MEASURES_DESIGN.md). Expected values come from short series worked by hand or by plain loops."""
import copy
import math
from pathlib import Path
import statistics
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from compertum.ai.engine import measures,panel  # noqa: E402
from compertum.ai.engine.market import score_signals,split_market,synthetic_market  # noqa: E402
from test_engine_panel import SYMBOLS,rows_for,synthetic  # noqa: E402


def test_series_numbers():
    a=[0.01,-0.01,0.02,0.0]
    assert measures.active_sharpe(a)==pytest.approx(statistics.mean(a)/statistics.stdev(a)*math.sqrt(252))
    assert measures.active_sharpe([0.01,0.01,0.01]) is None and measures.active_sharpe([0.01]) is None
    ramp=[x/1000 for x in range(-50,51)]
    assert measures.tail_ratio(ramp)==pytest.approx(1.0) and measures.tail_ratio([0.0]*10+[0.01]) is None
    assert measures.lag_autocorr([1.0,-1.0]*10)==pytest.approx(-1.0) and measures.lag_autocorr([0.0]*5) is None
    blocks=measures.block_sharpes([0.01,0.02]*4+[-0.01,-0.02]*4)
    assert blocks['positive']==2 and blocks['min']<0<blocks['spread'] and len(blocks['values'])==4


def test_newey_west():
    """The Newey-West t-statistic agrees with a plain loop; with no dependence it is close to the ordinary t-statistic."""
    a=[math.sin(i*1.7)*0.01+0.001 for i in range(100)];n=len(a);m=sum(a)/n;d=[x-m for x in a];lags=4
    var=sum(x*x for x in d)/n+sum(2*(1-k/(lags+1))*sum(d[i]*d[i-k] for i in range(k,n))/n for k in range(1,lags+1))
    assert measures.newey_west(a)==pytest.approx(m/math.sqrt(var/n))
    assert measures.newey_west([0.01,0.01,0.01]) is None


def test_concentration():
    w=[{'a':0.5,'b':0.5},{},{'a':1.0},{'a':0.25,'b':0.25}]
    assert measures.concentration(w)=={'effective_assets':pytest.approx((2+1+2)/3),'max_weight':1.0}
    assert measures.concentration([{},{}]) is None


def test_single_paths():
    """The active return of session t+1 is the position at t times the return, cash at the rate, minus the cost of a change, minus the return."""
    rows=[{'session':'s1','return':'0','rate':'0.0001'},{'session':'s2','return':'0.02','rate':'0.0001'},{'session':'s3','return':'-0.01','rate':'0.0001'}]
    text='session,position\ns1,1\ns2,0\ns3,0\n'
    paths=measures.single_paths(text,rows);cost=float(measures.cost_at('s1'))
    assert paths['base']==pytest.approx([0.02-cost-0.02,0.0001-cost-(-0.01)])
    assert paths['cost_2x']==pytest.approx([-2*cost,0.0101-2*cost]) and paths['lagged']==pytest.approx([0.0001-0.02,-cost])


@pytest.fixture
def single():
    rows=synthetic_market(3,400,planted={'kind':'momentum','window':5,'strength':0.004});_,validation=split_market(rows)
    text='session,position\n'+''.join(f"{r['session']},{i%2}\n" for i,r in enumerate(validation))
    return validation,text


def test_candidate_measures(tmp_path,single):
    """A scored candidate gets every measure and a series file with a matching hash; the score is not changed; a second write is refused."""
    validation,text=single;score=score_signals(text,validation);before=copy.deepcopy(score)
    runs=[{'purpose':'engineer','job_folder':'j1','status':'FAILED'},{'purpose':'engineer','job_folder':'j2','status':'COMPLETED','signals':text,'files':{'main.py':'print(1)\n'}},
          {'purpose':'engineer','job_folder':None,'status':'REFUSED_ENGINE_RUN_LIMIT'}]
    record=measures.candidate_measures(project_root=tmp_path,candidate_id='cycle-0001-abc:h1',signals=text,score=score,validation_rows=validation,runs=runs)
    assert score==before and record['status']=='MEASURED' and record['engineer_runs']==2 and record['code_bytes']==9
    full=record['full'];n=len(validation)-1
    assert full['sessions']==n and record['early']['sessions']==int(n*2/3) and record['series']['sessions']==n
    assert set(full)=={'sessions','active_sharpe','tail_ratio','hit_rate','block_sharpes','lag_drop','cost_2x_active_sharpe','autocorrelation','newey_west_t'}
    assert full['cost_2x_active_sharpe']<full['active_sharpe'] and record['exposure']==pytest.approx(score['positions_held']/len(validation))
    assert record['concentration'] is None and record['series']['path']=='state/engine/series/cycle-0001-abc_h1.json.gz'
    series=measures.load_series(tmp_path,record['series'])
    assert series==pytest.approx(measures.single_paths(text,validation)['base'])
    assert measures.candidate_measures(project_root=tmp_path,candidate_id='cycle-0001-abc:h1',signals=text,score=score,validation_rows=validation)=={'status':'UNDEFINED','reason':'ENGINE_MEASURES_DUPLICATE'}
    (tmp_path/record['series']['path']).write_bytes(b'changed')
    with pytest.raises(measures.RuntimeRefused,match='^ENGINE_MEASURES_CHANGED$'): measures.load_series(tmp_path,record['series'])


def test_measures_undefined(tmp_path,single):
    """Bad signals, a short series and an unexpected error give UNDEFINED with the reason, never an exception."""
    validation,text=single;score=score_signals(text,validation)
    assert measures.candidate_measures(project_root=tmp_path,candidate_id='c1',signals='nonsense',score=score,validation_rows=validation)['status']=='UNDEFINED'
    short=validation[:6];short_text='session,position\n'+''.join(f"{r['session']},1\n" for r in short)
    assert measures.candidate_measures(project_root=tmp_path,candidate_id='c2',signals=short_text,score={'sessions':6,'positions_held':6,'position_changes':1},
                                       validation_rows=short)=={'status':'UNDEFINED','reason':'ENGINE_MEASURES_SHORT'}
    broken=measures.candidate_measures(project_root=tmp_path,candidate_id='c3',signals=text,score={},validation_rows=validation)
    assert broken['status']=='UNDEFINED' and broken['reason'].startswith('KeyError')
    assert not (tmp_path/'state').exists() or not any((tmp_path/'state'/'engine'/'series').iterdir())


def test_panel_measures(tmp_path):
    """A panel candidate is measured on the library's own active returns, with concentration, and its score stays the same."""
    p=synthetic();market=panel.PanelMarket(p);aliases=market.aliases;start=p['train'];n=len(p['dates'])
    live=lambda t: [s for s in SYMBOLS if p['closes'][s][t] is not None]
    targets={t:({s:1/len(live(t)) for s in live(t)} if t%10 else {live(t)[0]:0.6}) for t in range(n)}
    text=rows_for(p,aliases,targets,range(start-1,n))
    score=market.score(text);before=copy.deepcopy(score)
    record=measures.candidate_measures(project_root=tmp_path,candidate_id='panel-1',signals=text,score=score,market=market)
    assert record['status']=='MEASURED' and score==before
    chosen=panel.parse_weights(text,p,aliases)
    expected=measures.library_multi.run_navs(measures.library_multi.prepare(p,sorted(p['closes'])),chosen,start,n,None)[4]
    assert measures.load_series(tmp_path,record['series'])==pytest.approx(expected)
    assert record['concentration']['max_weight']==pytest.approx(0.6) and 1<record['concentration']['effective_assets']<len(SYMBOLS)
    assert record['turnover_per_year']==pytest.approx(float(score['turnover_per_year'])) and record['full']['sessions']==n-start-1
