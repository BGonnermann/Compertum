import pytest
from test_ai_manual import bridge  # noqa: F401
from test_engine_bench import candidate_cycle
from compertum.ai.engine import bench,compare
from compertum.ai.engine.ledger import EngineLedger
from compertum.runtime.errors import RuntimeRefused


def write_run(ledger,run_id,markets,reference,saved_report):
    labels=[m['label'] for m in markets]
    ledger.record_run_phase(run_id,'START',{'purpose':'bench','markets':labels})
    cycles=[]
    for index,market in enumerate(markets,1):
        positions=bench.reference_positions(market['train_rows'],market['validation_rows'],market['kind'],market['window'],market.get('regimes')) if reference and market['kind'] else [0]*len(market['validation_rows'])
        record=candidate_cycle(market,positions,status='REJECTED')
        stored={**record,'run_id':run_id,'purpose':'bench','market_sha256':compare.market_sha256(market),'faults':[]}
        stored.pop('market');ledger.record_cycle(f'cycle-{run_id[-2:]}-{index:04d}',index,'END',stored)
        cycles.append(record)
    report=bench.report(cycles,markets,cycles_per_market=1)
    ledger.record_run_phase(run_id,'END',{'reason':'CYCLE_LIMIT','requests':10,'elapsed_seconds':20.0,**({'report':report} if saved_report else {})})


def test_saved_and_legacy_reports_support_an_equal_market_comparison(bridge):
    b,_=bridge;ledger=EngineLedger(b.store);markets=bench.set_markets('bench-1')
    write_run(ledger,'run-20261027-00000001',markets,False,True)
    write_run(ledger,'run-20261027-00000002',markets,True,False)
    left=compare.run_summary(b.store.conn,'run-20261027-00000001');right=compare.run_summary(b.store.conn,'run-20261027-00000002')
    assert left['report']['patterns_found']==0 and right['report']['patterns_found']==3
    result=compare.compare_summaries(left,right)
    assert result['delta']['patterns_found']==3 and result['delta']['false_discoveries']==0
    assert result['mean_level_delta']=='3.60' and len(result['markets'])==5
    assert result['markets'][0]['right_levels']==[10] and 'does not establish' in result['warning']


def test_incompatible_and_unknown_runs_are_refused(bridge,tmp_path):
    b,_=bridge;ledger=EngineLedger(b.store);markets=bench.set_markets('bench-1')
    write_run(ledger,'run-20261027-00000001',markets,False,True)
    write_run(ledger,'run-20261027-00000002',markets,True,True)
    left=compare.run_summary(b.store.conn,'run-20261027-00000001');right=compare.run_summary(b.store.conn,'run-20261027-00000002')
    right['report']=dict(right['report'],cycles_per_market=2)
    with pytest.raises(RuntimeRefused,match='^ENGINE_COMPARISON_INCOMPATIBLE$'): compare.compare_summaries(left,right)
    with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_UNKNOWN$'): compare.run_rows(b.store.conn,'run-20261027-ffffffff')
    with pytest.raises(RuntimeRefused,match='^ENGINE_STORE_UNAVAILABLE$'):
        compare.compare(tmp_path/'missing.sqlite','run-20261027-00000001','run-20261027-00000002')


def test_legacy_reconstruction_covers_bench_2(bridge):
    b,_=bridge;ledger=EngineLedger(b.store);markets=bench.set_markets('bench-2')
    write_run(ledger,'run-20261027-00000002',markets,True,False)
    summary=compare.run_summary(b.store.conn,'run-20261027-00000002')
    assert summary['report']['patterns_found']==3 and summary['report']['unknown_markets']==[]


def test_compare_command_output_and_refusal(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(compare,'compare',lambda *args:{'comparison':'fixture'})
    assert compare.main(['--project',str(tmp_path),'run-20261027-00000001','run-20261027-00000002'])==0
    assert 'fixture' in capsys.readouterr().out
    monkeypatch.undo()
    assert compare.main(['--project',str(tmp_path),'run-20261027-00000001','run-20261027-00000002'])==2
    assert 'ENGINE_STORE_UNAVAILABLE' in capsys.readouterr().out
