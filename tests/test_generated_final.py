"""Whole generated batch, exact ledger arithmetic and fixed worker-plan inputs."""
import hashlib,json
from decimal import Decimal as D
from uuid import UUID,uuid4,uuid5
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import fixed_definition
from compertum.final_recipe import recipe,recipe_hash
from compertum.modeling.generated_final import evaluate_generated_final


def plan(selected=('ridge-h01-a001','ridge-h05-a010','ridge-h21-a100')):
    eid=str(uuid4())
    return dict(schema='synthetic-final-plan-v1',project_id='a'*64,seal_id=str(uuid4()),evaluation_id=eid,
        checkpoint_id=str(uuid5(UUID(eid),'synthetic-final-initial-v1')),
        inputs=dict(input_sha256=recipe_hash(),protocol_sha256='b'*64,shortlist_sha256='c'*64),
        shortlist_ticket_sha256='d'*64,selected=list(selected),recipe=recipe(),runtime=dict(package_sha256='e'*64,lock_sha256='f'*64,python='3.14.7',distributions=[['numpy','2.4.3']]),
        yearly_fits=fixed_definition()['fits'],
        budget=dict(attempts=2,wall_seconds=120,cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*1024**2),
        checkpoint=dict(schema='synthetic-final-checkpoint-v1',position='BEFORE_BATCH',price_reads=0),
        financial_accepted=False,full_M3=False)


def run(value):
    raw=canonical(value)
    return evaluate_generated_final(raw,expected_sha256=hashlib.sha256(raw).hexdigest())


@pytest.fixture(scope='module')
def batch():
    from types import SimpleNamespace
    from unittest.mock import patch
    from compertum.modeling import generated_final as module
    from compertum.modeling.generated_tables import read_final
    original=module.pack_final;captured=[]
    def record(value):
        captured.append(canonical(value));return original(value)
    with patch.object(module,'pack_final',record):result=run(plan())
    expanded=canonical(read_final(result.content,expected_sha256=result.sha256))
    assert expanded==captured[0]
    return SimpleNamespace(content=expanded,sha256=hashlib.sha256(expanded).hexdigest(),packed=result.content)


def test_complete_three_ridge_batch_is_bounded_and_preserves_all_evidence(batch):
    value=json.loads(batch.content)
    assert len(batch.packed)<=16*1024**2 and hashlib.sha256(batch.content).hexdigest()==batch.sha256
    assert value['status']=='SYNTHETIC_ENGINEERING' and not value['financial_accepted'] and not value['full_M3']
    assert value['authority']=='NO_OWNER_ADMISSION_FROM_PURE_COMPUTATION'
    assert len(value['fits'])==6 and len(value['candidates'])==3
    for candidate in value['candidates']:
        assert len(candidate['folds'])==2
        q=candidate['qualification'];assert q['numeric_gates']['complete_window'] and q['numeric_gates']['daily_observations']
        assert q['paper_eligible'] is False and q['strategy_accepted'] is False
        assert q['bootstrap']['draws']==10000 and q['bootstrap']['family_size']==12
        assert q['inputs']['sessions']==value['market']['scoring_sessions']
        assert q['inputs']['segments'][1]['start']==len(candidate['folds'][0]['predictions']['daily_rank_correlation'])
        for fold in candidate['folds']:
            assert set(fold['replays'])=={'10','20'}
            predictions=fold['predictions'];days=predictions['daily_rank_correlation']
            assert predictions['coverage']['candidate_rows']==12*len(days)
            assert sum(r['reason']=='MISSING_SYMBOL' for r in predictions['omissions'])==9*len(days)
            for cost,replay in fold['replays'].items():
                assert set(replay['portfolios'])=={'strategy','spy60','spy100','equal60','zero'}
                assert replay['portfolios']['strategy']['completed_intervals']==len(fold['checks'][cost]['policy']['holding_intervals'])
                assert fold['checks'][cost]['recorded_fill_accounting']=='VERIFIED_PASS'


def test_qualification_compounds_yearly_returns_without_reset_jump(batch):
    for item in json.loads(batch.content)['candidates']:
        inputs=item['qualification']['inputs']
        for cost,name,key in [('10','strategy','navs'),('10','spy60','benchmark'),('20','strategy','stress_navs'),('20','spy60','stress_benchmark')]:
            expected=[D(10000)];independent_returns=[]
            for fold in item['folds']:
                previous=D(10000)
                for row in fold['replays'][cost]['portfolios'][name]['days']:
                    nav=D(row['nav']);independent_returns.append(nav/previous-1);previous=nav
            actual=list(map(D,inputs[key]))
            assert len(actual)==len(independent_returns)+1
            for i,ret in enumerate(independent_returns):assert abs(actual[i+1]/actual[i]-1-ret)<D('1e-24')


@pytest.mark.parametrize('change',['selected','recipe','budget','checkpoint','inputs','extra'])
def test_changed_or_unbounded_plan_refuses_before_generation(change,monkeypatch):
    import compertum.modeling.generated_final as module
    def forbidden(*args,**kwargs):raise AssertionError('generated before plan check')
    monkeypatch.setattr(module,'generate_market',forbidden)
    value=plan()
    if change=='selected':value['selected']=['ridge-h01-a001','ridge-h01-a010']
    elif change=='recipe':value['recipe']['last_score']='2026-01-02'
    elif change=='budget':value['budget']['wall_seconds']=121
    elif change=='checkpoint':value['checkpoint']['price_reads']=1
    elif change=='inputs':value['inputs']['input_sha256']='e'*64
    else:value['path']='external'
    with pytest.raises(DataError):run(value)


def test_legacy_recipe_nonempty_plan_refuses_before_generation(monkeypatch):
    import compertum.modeling.generated_final as module
    def forbidden(*args,**kwargs):raise AssertionError('legacy recipe generated')
    monkeypatch.setattr(module,'generate_market',forbidden)
    value=plan();value['recipe']=recipe(version=1);value['inputs']['input_sha256']=recipe_hash(version=1)
    with pytest.raises(DataError):run(value)


@pytest.mark.parametrize('change',['runtime','nil_seal','nil_evaluation'])
def test_impossible_owner_plan_rejected_before_prices(change,monkeypatch):
    import compertum.modeling.generated_final as module
    def forbidden(*args,**kwargs):raise AssertionError('generated before plan check')
    monkeypatch.setattr(module,'generate_market',forbidden)
    value=plan()
    if change=='runtime':value['runtime']={}
    elif change=='nil_seal':value['seal_id']=str(UUID(int=0))
    else:
        value['evaluation_id']=str(UUID(int=0))
        value['checkpoint_id']=str(uuid5(UUID(int=0),'synthetic-final-initial-v1'))
    with pytest.raises(DataError):run(value)


def test_generated_recorded_nav_returns_cannot_exceed_daily_tolerance():
    from test_policy_audit import fixture,SECTORS
    from compertum.simulation.engine import replay
    from compertum.simulation.market import load_market
    from compertum.audit_predictions import SourceEvidence
    from compertum.data.calendar import session_times
    from compertum.modeling.generated_final import _check_replay
    chunks,start,end,_=fixture(scored=8);base=load_market(chunks,SECTORS)
    value=json.loads(replay(chunks,SECTORS,start,end,5).content)
    value['policy']='registered-candidate-synthetic-v1'
    value['portfolios']['strategy']=value['portfolios'].pop('momentum')
    days=[start]
    while days[-1]!=end:days.append(session_times(days[-1]).next_date)
    rows=value['portfolios']['zero']['days'];rows[0]['nav']='10000.00009';rows[1]['nav']='9999.99991'
    with pytest.raises(DataError,match='AUDIT_'):_check_replay(base,days,value,None,SourceEvidence(base))


@pytest.mark.parametrize('fault',['duplicate_column','wrong_column','short_row','long_row','extra','row_type','count','budget'])
def test_record_tables_reject_malformed_shapes_and_bounds(fault):
    from compertum.modeling.generated_tables import _table,_records
    table=_table([dict(symbol='AAPL',entry=0,exit=1)],'intervals');budget=[0,0]
    if fault=='duplicate_column':table['columns'][1]=table['columns'][0]
    elif fault=='wrong_column':table['columns'][1]='unknown'
    elif fault=='short_row':table['rows'][0].pop()
    elif fault=='long_row':table['rows'][0].append(None)
    elif fault=='extra':table['extra']=[]
    elif fault=='row_type':table['rows'][0]='not a row'
    elif fault=='count':table['rows']*=12289
    else:budget=[200000,0]
    with pytest.raises(DataError):_records(table,'intervals',budget)


def test_packed_evidence_rejects_rehashed_changed_values(batch):
    from compertum.modeling.generated_tables import read_final
    value=json.loads(batch.packed)
    value['fits'][0]['rows']['rows'][0][0]='changed'
    raw=canonical(value)
    with pytest.raises(DataError):read_final(raw,expected_sha256=hashlib.sha256(raw).hexdigest())


def test_table_columns_are_immutable_and_empty_lists_roundtrip():
    from compertum.modeling.generated_tables import _table,_records
    table=_table([],'intervals');table['columns'][0]='changed'
    fresh=_table([],'intervals')
    assert _records(fresh,'intervals',[0,0])==[]


def test_record_table_expansion_has_separate_memory_bound():
    from compertum.modeling.generated_tables import _table,_records,MAX_EXPANDED
    table=_table([dict(symbol='AAPL',entry=0,exit=1)],'intervals')
    with pytest.raises(DataError):_records(table,'intervals',[0,MAX_EXPANDED])


def test_packer_cannot_emit_more_records_than_reader_accepts():
    from copy import deepcopy
    from compertum.modeling.generated_tables import pack_final
    book={key:[] for key in ('trades','observations','days','signals','omissions')}
    fold=dict(predictions=dict(rows=[],omissions=[],daily_rank_correlation=[]),
        replays={cost:dict(portfolios={name:deepcopy(book) for name in ('strategy','spy60','spy100','equal60','zero')}) for cost in ('10','20')},
        checks={cost:dict(policy=dict(holding_intervals=[])) for cost in ('10','20')})
    value=dict(schema='generated-final-batch-v1',fits=[],candidates=[dict(folds=[deepcopy(fold),deepcopy(fold)],qualification=dict(inputs=dict(predictions=[],intervals=[])))])
    tables=[b for f in value['candidates'][0]['folds'] for r in f['replays'].values() for b in r['portfolios'].values()]
    for target in tables[:17]:target['omissions']=[dict(session=None,symbol=None,reason=None)]*12288
    assert len(canonical(value))<32*1024**2
    with pytest.raises(DataError):pack_final(value)
