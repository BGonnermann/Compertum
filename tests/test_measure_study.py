"""The candidate measures study (part 3): hand-checked statistics, the sample-size label, the vault join, and a read-only ledger."""
import hashlib
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import measure_study as ms  # noqa: E402
from test_ai_manual import bridge  # noqa: E402,F401  (fixture)
from compertum.ai.engine.ledger import EngineLedger  # noqa: E402
from compertum.ai.engine.measures import save_series  # noqa: E402

MARKET='a'*64


def test_spearman_ranks():
    assert list(ms.ranks(ms.np.array([1.0,2.0,2.0,3.0])))==[1.0,2.5,2.5,4.0]
    assert ms.spearman([1,2,3,4],[1,3,2,4])==pytest.approx(1-6*2/(4*15))
    assert ms.spearman([1,1,1],[1,2,3]) is None


def test_combined():
    """A target that the measures explain exactly gives R squared 1; too few rows give None."""
    x=[[i,(i*7)%5] for i in range(20)];y=[2*a-3*b+1 for a,b in x]
    assert ms.combined(x,y)==pytest.approx(1.0)
    assert ms.combined(x[:8],y[:8]) is None and ms.combined([[1]]*20,[0.0]*20) is None


def measured(i,late,root):
    early={'active_sharpe':0.1*i,'tail_ratio':1.0+0.01*i,'hit_rate':0.5,'block_sharpes':{'min':0.0,'spread':1.0,'positive':2},'lag_drop':0.0,
           'cost_2x_active_sharpe':0.05*i,'autocorrelation':0.0,'newey_west_t':0.2*i}
    return {'status':'MEASURED','market_sha256':MARKET,'early':early,'full':early,'late_active_sharpe':late,'exposure':0.5,'turnover_per_year':10.0,
            'engineer_runs':1+i%3,'code_bytes':100+i,'concentration':None,'series':save_series(root,f'cycle-{i:04d}-aaaaaaaa:h1',[0.001,-0.001]*8)}


def ledger_with(b,root,count):
    ledger=EngineLedger(b.store)
    for i in range(count):
        cycle=f'cycle-{i:04d}-aaaaaaaa'
        ledger.record_step(cycle,3,'validator','score',{'phase':'SCORED','candidate_id':f'{cycle}:h1','measures':measured(i,0.1*i+(0.02 if i%2 else -0.02),root)})
        ledger.record_cycle(cycle,i+1,'END',{'purpose':'practice' if i%4 else 'bench','market_sha256':MARKET})
    ledger.record_step('cycle-9999-bbbbbbbb',3,'validator','score',{'phase':'SCORED','candidate_id':'cycle-9999-bbbbbbbb:h1','measures':{'status':'UNDEFINED','reason':'x'}})
    ledger.record_queue_event('cycle-0002-aaaaaaaa:h1','VAULT_EVALUATED',{'status':'SCORED','result':{'deflation_inputs':{'sharpe_per_period':'0.0630'}}})
    return ledger


def test_small_sample(bridge,tmp_path):
    """Below 30 candidates every result is labeled too small to use; the vault result joins its candidate; the store is not changed."""
    b,root=bridge;ledger_with(b,root,6);store,_=ms.run_tests.engine_store(root);before=hashlib.sha256(store.read_bytes()).hexdigest()
    out=tmp_path/'study.md';assert ms.main(['--out',str(out)],root=root)==0
    text=out.read_text(encoding='utf-8');result=ms.run(root)
    assert result['candidates']==6 and result['purposes']=={'bench':2,'practice':4} and result['series_problems']==[]
    assert result['proxy']['all']['label']==ms.SMALL and all(r['label']==ms.SMALL for r in result['proxy']['all']['table'])
    assert result['vault_results']==1 and result['vault']['n']==1
    assert 'Sample: 6 candidates (too small to use).' in text and 'Joined with measured candidates: 1.' in text and 'opened no vault' in text
    assert hashlib.sha256(store.read_bytes()).hexdigest()==before


def test_usable_sample(bridge):
    """With 32 candidates the proxy table is usable; a measure that ranks the late result exactly has Spearman 1, and a changed series file is named."""
    b,root=bridge;ledger_with(b,root,32)
    (root/'state'/'engine'/'series'/'cycle-0005-aaaaaaaa_h1.json.gz').write_bytes(b'changed')
    result=ms.run(root);part=result['proxy']['all'];rows={r['measure']:r for r in part['table']}
    assert part['n']==32 and part['label']=='usable' and rows['early.active_sharpe']['spearman']==pytest.approx(1.0)
    low,high=rows['early.active_sharpe']['interval'];assert low<=1.0<=high+1e-9 and rows['exposure']['spearman'] is None and rows['exposure']['overlap']
    assert part['combined']['r_squared'] is not None and result['series_problems']==['cycle-0005-aaaaaaaa:h1']
    assert set(result['proxy'])=={'all',MARKET}


def test_empty_store(tmp_path):
    result=ms.run(tmp_path)
    assert result['candidates']==0 and result['vault']['n']==0 and 'No measured candidate has a vault result yet.' in ms.report_text(result)
