"""Closed generated recipe/market contracts; no real data or owner admission."""
import hashlib,json
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.final_recipe import recipe,recipe_for_pin,recipe_hash
from compertum.modeling.generated_market import generate_market


def test_versioned_recipe_preserves_legacy_journal_bytes():
    legacy=recipe(version=1)
    assert hashlib.sha256(canonical(legacy)).hexdigest()=='c5f6bfe9627fbd08d8968203c349d8ccb6ae410ca38eebe3cee92f0f6edaf9ad'
    assert recipe_for_pin(recipe_hash(version=1))==legacy
    current=recipe()
    assert current['schema']=='builtin-generated-final-recipe-v2'
    assert current['source']=='BUILTIN_GENERATED_ONLY'
    assert current['first_score']=='2024-01-02' and current['last_score']=='2025-12-31'
    assert current['initial_training_start']=='2023-10-26'
    assert current['coverage']=='PARTIAL_FIXTURE_UNQUALIFIED'
    assert current['symbols']==['AAPL','MSFT','JPM','SPY']
    assert current['denominator_stocks']==12
    current['symbols'].append('NVDA')
    assert len(recipe()['symbols'])==4


@pytest.mark.parametrize('change',['year','symbol','seed','calendar','rows','path','extra'])
def test_modified_recipe_has_no_generation_path(change):
    v=recipe()
    if change=='year':v['last_score']='2026-12-31'
    elif change=='symbol':v['symbols']=['NVDA','SPY']
    elif change=='seed':v['seed']=1730
    elif change=='calendar':v['calendar']['version']='changed'
    else:v[change]='untrusted'
    raw=canonical(v)
    with pytest.raises(DataError):generate_market(raw,expected_sha256=hashlib.sha256(raw).hexdigest())


@pytest.fixture(scope='module')
def generated():
    raw=canonical(recipe())
    return generate_market(raw,expected_sha256=recipe_hash())


def test_generated_market_is_bounded_continuous_and_exact(generated):
    from decimal import Decimal
    from compertum.data.calendar import session_times
    market,meta=generated
    assert 1<=len(meta['chunk_sha256'])<=64 and meta['input_bytes']<=16*1024**2
    days=meta['sessions'];scored=meta['scoring_sessions']
    assert days[0]=='2022-10-25' and days[-1]=='2025-12-31'
    assert scored[0]=='2024-01-02' and scored[-1]=='2025-12-31' and len(scored)>=400
    assert len(days)<1024
    assert all(session_times(a).next_date==b for a,b in zip(days,days[1:]))
    assert not any(day>='2026-01-01' for _,day,_ in market.rows)
    assert tuple(market.symbols)==('AAPL','JPM','MSFT','SPY')
    day='2024-01-02';index=days.index(day)
    assert market.reference('AAPL',day,'entry')==Decimal(80)+Decimal(index)/20
    assert market.reference('SPY',day,'close')==Decimal(80)+Decimal(index)*4/20
    assert meta['training_start']=='2023-10-26'
    assert meta['annual']['2024']['training_end']=='2023-12-29'
    assert meta['annual']['2025']['training_end']=='2024-12-31'
    assert all(v['training_start']==meta['training_start'] for v in meta['annual'].values())
    assert len(meta['symbols'])==4 and meta['financial_accepted'] is False
    last=days[-1]
    assert market.reference('AAPL',last,'close')==Decimal(80)+Decimal(len(days)-1)/20
    assert market.rows[('AAPL',last,'daily')]['session_date']==last
    assert len(market.rows)==4*(3*len(days)-1)
    with pytest.raises(DataError,match='MISSING_REFERENCE'):market.reference('AAPL','2026-01-02','entry')
    assert market.sha256==meta['market_sha256']


def test_generated_market_reproduces_every_row_and_identity(generated):
    market,meta=generated
    again,again_meta=generate_market(canonical(recipe()),expected_sha256=recipe_hash())
    assert market==again and meta==again_meta


def test_public_development_cutoffs_remain_closed():
    from compertum.modeling.registry import annual_cutoff
    for year in (2024,2025,2026):
        with pytest.raises(DataError,match='DEVELOPMENT_YEAR_REQUIRED'):annual_cutoff(year)


def test_legacy_partial_recipe_has_no_nonempty_generation_path():
    raw=canonical(recipe(version=1))
    with pytest.raises(DataError,match='GENERATED_RECIPE_UNSUPPORTED'):generate_market(raw,expected_sha256=recipe_hash(version=1))



def test_generated_prices_ignore_ambient_decimal_context(generated):
    from decimal import localcontext,ROUND_DOWN
    with localcontext() as context:
        context.prec=3;context.rounding=ROUND_DOWN
        actual=generate_market(canonical(recipe()),expected_sha256=recipe_hash())
    assert actual==generated


def test_terminal_rows_have_exact_policy_times_and_generic_snapshot_stays_strict(generated):
    from datetime import timedelta
    from compertum.data.calendar import session_times,utc_time
    from compertum.data.snapshot import validate_snapshot
    market,meta=generated;day='2025-12-31';t=session_times(day)
    rows=[market.rows[(symbol,day,ref)] for symbol in recipe()['symbols'] for ref in ('daily','close')]
    assert len(rows)==8
    assert {(r['asset_id'],r['session_date'],r['reference'],r['adjustment']) for r in rows}=={(s,day,ref,'raw') for s in recipe()['symbols'] for ref in ('daily','close')}
    for row in rows:
        expected=session_times(t.next_date).decision if row['reference']=='daily' else t.close+timedelta(minutes=15)
        assert utc_time(row['simulated_available_at'])==utc_time(row['simulated_revision_available_at'])==expected
    assert hashlib.sha256(canonical(rows)).hexdigest()==meta['terminal_sha256']
    bars=[dict(market.rows[('AAPL',day,ref)]) for ref in ('daily','close')]
    bars.append(dict(bars[0],adjustment='split'))
    source=dict(provider='synthetic',feed='iex',vintage='generated-final-v2',availability_basis='SIMULATED_AVAILABILITY',aggregation='PROVIDER_DAILY')
    raw=canonical(dict(schema_version='1',source=source,assets=[dict(asset_id='AAPL',symbol='AAPL')],feature_sessions=[day],bars=bars,actions=[]))
    with pytest.raises(DataError,match='MISSING_ROW'):validate_snapshot(raw)
