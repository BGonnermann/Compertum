"""Candidate measures, part 1 (docs/CANDIDATE_MEASURES_DESIGN.md). Expected values come from short series worked by hand or by plain loops."""
import copy
import hashlib
import math
from pathlib import Path
import statistics
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ai_manual import bridge  # noqa: E402,F401  (fixture)
from compertum.events import canonical  # noqa: E402
from compertum.ai.engine import library_multi as lm,measures,panel  # noqa: E402
from compertum.ai.engine.ledger import EngineLedger  # noqa: E402
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


def test_book_measures():
    """Correlation, the gain of the equal-weight mix and the residual Sharpe ratio agree with plain formulas; a member of another length is left out."""
    b1=[math.sin(i*0.9)*0.01 for i in range(60)];b2=[math.cos(i*1.3)*0.01+0.0005 for i in range(60)]
    c=[0.5*x+math.sin(i*2.1)*0.004+0.0003 for i,x in enumerate(b1)]
    members=[{'id':'m1','kind':'engine','sha256':'a','series':b1},{'id':'m2','kind':'engine','sha256':'b','series':b2},{'id':'m3','kind':'engine','sha256':'c','series':b1[:30]}]
    out=measures.book_measures(c,members)
    corr=[statistics.correlation(c,b1),statistics.correlation(c,b2)]
    assert out['status']=='MEASURED' and [m['id'] for m in out['members']]==['m1','m2'] and out['length_mismatch']==['m3']
    assert [m['correlation'] for m in out['members']]==pytest.approx(corr) and out['max_correlation']==pytest.approx(max(corr)) and out['mean_correlation']==pytest.approx(sum(corr)/2)
    mix=[(x+y)/2 for x,y in zip(b1,b2)];both=[(x+y+z)/3 for x,y,z in zip(b1,b2,c)]
    assert out['book_sharpe']==pytest.approx(measures.active_sharpe(mix)) and out['combined_sharpe_gain']==pytest.approx(measures.active_sharpe(both)-measures.active_sharpe(mix))
    one=measures.book_measures(c,members[:1]);beta=statistics.covariance(c,b1)/statistics.variance(b1)
    assert one['residual_sharpe']==pytest.approx(measures.active_sharpe([x-beta*y for x,y in zip(c,b1)]))
    assert measures.book_measures(c,members[2:])=={'status':'BOOK_EMPTY','members':[],'length_mismatch':['m3']}


def engine_member(ledger,root,cid,series,market):
    cycle=cid.rsplit(':',1)[0]
    record={'status':'MEASURED','market_sha256':market,'series':measures.save_series(root,cid,series)}
    ledger.record_step(cycle,5,'validator','score',{'phase':'SCORED','candidate_id':cid,'measures':record})
    ledger.record_queue_event(cid,'ELIGIBLE',{'route':{'kind':'engine'},'score_sha256':'x'})


def test_book_members(bridge):
    """The book holds only candidates that passed stage 1 on the same market; a changed series file is skipped with its reason."""
    b,root=bridge;ledger=EngineLedger(b.store);s=[0.001*i for i in range(20)]
    engine_member(ledger,root,'cycle-0001-aaaaaaaa:h1',s,'m'*64)
    engine_member(ledger,root,'cycle-0002-bbbbbbbb:h1',s,'n'*64)
    engine_member(ledger,root,'cycle-0003-cccccccc:h1',s,'m'*64)
    ledger.record_queue_event('cycle-0004-dddddddd:h1','DENIED',{'reasons':['x']})
    (root/measures.SERIES_DIR/'cycle-0003-cccccccc_h1.json.gz').write_bytes(b'changed')
    members,skipped=measures.book_members(ledger,root,'m'*64)
    assert [m['id'] for m in members]==['cycle-0001-aaaaaaaa:h1'] and members[0]['series']==pytest.approx(s) and members[0]['kind']=='engine'
    assert skipped==[{'id':'cycle-0003-cccccccc:h1','reason':'ENGINE_MEASURES_CHANGED'}]


def library_member(ledger,p,family='xs_momentum',sha=None):
    knobs=lm.FAMILIES[family][1][0];members=sorted(p['closes']);u=lm.prepare(p,members);s=lm.score(u,lm.weights(u,family,knobs),p['train'],u['n'])
    cid=f'library-multi-20261102-0000000a:french49:{family}'
    ledger.record_queue_event(cid,'ELIGIBLE',{'route':{'kind':'library-multi','universe':'french49','family':family,'knobs':knobs,'members':len(members)},
                                              'score_sha256':sha or hashlib.sha256(canonical(s)).hexdigest()})
    return cid,lm.run_navs(u,lm.weights(u,family,knobs),p['train'],u['n'],None)[4]


def test_library_book(bridge):
    """A library rule joins the book on its own panel universe, rebuilt from its family and settings and stored once; a changed score is refused."""
    b,root=bridge;ledger=EngineLedger(b.store);p=synthetic();market=panel.PanelMarket(p)
    cid,expected=library_member(ledger,p)
    assert measures.book_members(ledger,root,'m'*64)==([],[])
    members,skipped=measures.book_members(ledger,root,'m'*64,market)
    assert skipped==[] and [m['id'] for m in members]==[cid] and members[0]['kind']=='library-multi' and members[0]['series']==pytest.approx(expected)
    stored=list((root/measures.SERIES_DIR).iterdir());assert len(stored)==1 and stored[0].name.startswith('library_library-multi')
    again,_=measures.book_members(ledger,root,'m'*64,market);assert again[0]['sha256']==members[0]['sha256']
    library_member(ledger,p,'ew_trend',sha='0'*64)
    _,skipped=measures.book_members(ledger,root,'m'*64,market)
    assert skipped==[{'id':'library-multi-20261102-0000000a:french49:ew_trend','reason':'ENGINE_BOOK_CHANGED'}]


def test_candidate_book(bridge):
    """A panel candidate gets its book record and the two numbers that the roles see; a broken ledger gives book UNDEFINED and keeps the rest."""
    b,root=bridge;ledger=EngineLedger(b.store);p=synthetic();market=panel.PanelMarket(p);aliases=market.aliases;start=p['train'];n=len(p['dates'])
    library_member(ledger,p)
    targets={t:{s:1/len(p['eligible'][t]) for s in p['eligible'][t][:3]} for t in range(n)}
    text=rows_for(p,aliases,targets,range(start-1,n));score=market.score(text)
    record=measures.candidate_measures(project_root=root,candidate_id='panel-1',signals=text,score=score,market=market,ledger=ledger,market_sha256='m'*64)
    book=record['book'];assert record['status']=='MEASURED' and record['market_sha256']=='m'*64 and book['status']=='MEASURED' and len(book['members'])==1
    assert measures.book_view(record)=={'max_correlation':round(book['max_correlation'],2),'combined_sharpe_gain':round(book['combined_sharpe_gain'],2)}
    class Broken:
        def queue_events(self): raise RuntimeError('store gone')
    other=measures.candidate_measures(project_root=root,candidate_id='panel-2',signals=text,score=score,market=market,ledger=Broken(),market_sha256='m'*64)
    assert other['status']=='MEASURED' and other['book']=={'status':'UNDEFINED','reason':'RuntimeError: store gone'} and measures.book_view(other) is None
