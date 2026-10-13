"""Frozen, bounded synthetic campaign inputs and dependency-ordered work units."""
from dataclasses import asdict,dataclass
import hashlib,json,re
from compertum.data.calendar import session_times,utc_time
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.data.snapshot import validate_snapshot
from compertum.simulation.market import load_market,WATCHLIST
from .registry import VARIANTS,FEATURES,annual_cutoff,variant
from compertum.campaign_contract import YEARS,SEEDS,Unit,UNITS,_schedule
from .ridge import _estimators

MIB=1024**2
@dataclass(frozen=True)
class FoldInput:
    chunks:tuple
    sectors:dict
    training_start:str
    training_end:str
    start:str
    end:str
    scoring_as_of:str

@dataclass(frozen=True)
class CampaignInput:
    content:bytes
    sha256:str

def _identity(value):
    if not isinstance(value,dict) or set(value)!={'package_sha256','lock_sha256','python','distributions'}:raise DataError('RUN_ENVIRONMENT')
    if any(not isinstance(value[k],str) or re.fullmatch('[0-9a-f]{64}',value[k]) is None for k in ['package_sha256','lock_sha256']):raise DataError('RUN_ENVIRONMENT')
    if value['python']!='3.14.7':raise DataError('RUN_ENVIRONMENT')
    versions=value['distributions']
    if not isinstance(versions,(list,tuple)) or not 1<=len(versions)<=256:raise DataError('RUN_ENVIRONMENT')
    for pair in versions:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2 or any(not isinstance(x,str) or re.fullmatch('[A-Za-z0-9_.+!-]{1,96}',x) is None for x in pair):raise DataError('RUN_ENVIRONMENT')
    return json.loads(canonical(value))


def _dates(start,end):
    session_times(start);session_times(end)
    if start>end:raise DataError('INVALID_SEGMENT')
    current=start
    for _ in range(1024):
        if current==end:return
        current=session_times(current).next_date
    raise DataError('INPUT_BOUND')


def _fold(fold,year):
    if not isinstance(fold,FoldInput):raise DataError('CAMPAIGN_INPUT_INVALID')
    ts,te,start,end=fold.training_start,fold.training_end,fold.start,fold.end
    _dates(ts,te);_dates(start,end)
    cutoff=annual_cutoff(year).date().isoformat()
    if start[:4]!=str(year) or end[:4]!=str(year) or not '2016-01-01'<=ts<=te<cutoff<=start:raise DataError('INVALID_ANNUAL_FOLD')
    asof=utc_time(fold.scoring_as_of).isoformat()
    market=load_market(fold.chunks,fold.sectors)
    snapshots=[json.loads(c.content) for c in sorted(fold.chunks,key=lambda c:c.sha256)]
    dates={b['session_date'] for s in snapshots for b in s['bars']}
    dates.update(d for s in snapshots for d in s['feature_sessions'])
    if any(not '2016-01-01'<=day<'2024-01-01' for day in dates):raise DataError('DEVELOPMENT_PRICES_ONLY')
    _dates(min(dates),max(dates))
    return dict(year=year,training_start=ts,training_end=te,start=start,end=end,scoring_as_of=asof,
        snapshots=snapshots,sectors=fold.sectors,market_sha256=market.sha256)


def build_campaign(folds,*,identity,maximum_bytes=128*MIB):
    """Register every variant and annual dependency before fitting any model.

    Caller supplies its captured runtime identity; read/compute compare it to the
    current trusted runtime. This is not the adopted real-data protocol-v1 seal.
    """
    if not isinstance(folds,(tuple,list)) or len(folds)!=3:raise DataError('CAMPAIGN_INPUT_INVALID')
    if type(maximum_bytes) is not int or not 1<=maximum_bytes<=128*MIB:raise DataError('RUN_BUDGET')
    identity=_identity(identity);values=[_fold(f,y) for f,y in zip(folds,YEARS)]
    pins=[{'year':v['year'],'sha256':hashlib.sha256(canonical(v)).hexdigest()} for v in values]
    resolved=[]
    for a in (1,10,100):
        scaler,ridge=_estimators(a)
        resolved.append({'scaler':scaler.get_params(),'ridge':ridge.get_params(),'dtype':'float64','row_weights':'EQUAL'})
    definition={'features':FEATURES,'universe':WATCHLIST,'registered_family':[asdict(v) for v in VARIANTS],
        'cost_bps':[10,20],'seeds':SEEDS,'rng_state':'NO_RANDOM_DRAWS_SVD_DETERMINISTIC',
        'resolved_models':resolved,'identity':identity,'fold_pins':pins,
        'policy':'SYNTHETIC_PARTIAL_DEVELOPMENT_FOLDS','fit_activation':'SYNTHETIC_FIT_AUDIT_READY_ASSUMPTION'}
    trials=[{'candidate_id':v.candidate_id,'sha256':hashlib.sha256(canonical({'candidate':asdict(v),'definition':definition})).hexdigest()} for v in VARIANTS]
    value=dict(schema='synthetic-campaign-v1',input_kind='synthetic-campaign',financial_accepted=False,full_M2=False,
        **definition,folds=values,trials=trials,units=[asdict(u) for u in UNITS],maximum_bytes=maximum_bytes)
    raw=canonical(value)
    if len(raw)>20*MIB:raise DataError('INPUT_BOUND')
    if len(raw)>maximum_bytes:raise DataError('RUN_BUDGET')
    return CampaignInput(raw,hashlib.sha256(raw).hexdigest())


def read_campaign(raw,*,expected_sha256,identity):
    """Validate exactly the fixed contract and independently pinned input bytes."""
    if not isinstance(raw,bytes) or not 0<len(raw)<=20*MIB:raise DataError('INPUT_BOUND')
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise DataError('RUN_ARTIFACT_CORRUPT')
    try:
        value=json.loads(raw)
        if type(value) is not dict:raise DataError('CAMPAIGN_INPUT_INVALID')
        if value.get('schema')=='synthetic-campaign-v2':
            from compertum.clean_pair import detach_environment
            mathematical,_,_,_=detach_environment(raw,expected_sha256=expected_sha256)
            return read_campaign(mathematical,expected_sha256=hashlib.sha256(mathematical).hexdigest(),identity=identity)
        if canonical(value)!=raw or value['identity']!=_identity(identity):raise DataError('RUN_IDENTITY_CHANGED')
        if not isinstance(value['folds'],list) or len(value['folds'])!=3:raise DataError('CAMPAIGN_INPUT_INVALID')
        folds=[]
        for fold in value['folds']:
            if not isinstance(fold['snapshots'],list) or not 1<=len(fold['snapshots'])<=64:raise DataError('INPUT_BOUND')
            chunks=tuple(validate_snapshot(canonical(s)) for s in fold['snapshots'])
            folds.append(FoldInput(chunks,fold['sectors'],fold['training_start'],fold['training_end'],fold['start'],fold['end'],fold['scoring_as_of']))
        expected=build_campaign(folds,identity=identity,maximum_bytes=value['maximum_bytes'])
        if raw!=expected.content:raise DataError('CAMPAIGN_INPUT_INVALID')
        return value
    except (KeyError,TypeError,ValueError,RecursionError,OverflowError):raise DataError('CAMPAIGN_INPUT_INVALID') from None


def compute_campaign_unit(campaign,index,*,identity,fit_checkpoint=None,expected_fit_sha256=None):
    """Pure one-unit execution; ridge evaluations never fall back to cold fitting."""
    if not isinstance(campaign,CampaignInput) or type(index) is not int or not 0<=index<len(UNITS):raise DataError('CAMPAIGN_UNIT_INVALID')
    unit=UNITS[index]
    if unit.fit_unit is None:
        if fit_checkpoint is not None or expected_fit_sha256 is not None:raise DataError('CAMPAIGN_DEPENDENCY_INVALID')
    elif fit_checkpoint is None or expected_fit_sha256 is None:raise DataError('CAMPAIGN_DEPENDENCY_REQUIRED')
    value=read_campaign(campaign.content,expected_sha256=campaign.sha256,identity=identity)
    fold=value['folds'][YEARS.index(unit.year)]
    chunks=tuple(validate_snapshot(canonical(s)) for s in fold['snapshots'])
    args=(chunks,fold['sectors'],fold['training_start'],fold['training_end'])
    if unit.phase=='fit':
        from .checkpoints import prepare_fit_checkpoint,read_fit_checkpoint
        result=prepare_fit_checkpoint(*args,unit.year,unit.candidate_id)
        # Validate the exact produced bytes inside the bounded numerical worker.
        # Publication must never rely on the small coordinator importing a fitter.
        read_fit_checkpoint(result,expected_sha256=result.sha256,market_sha256=fold['market_sha256'],candidate_id=unit.candidate_id,year=unit.year,training_start=fold['training_start'],training_end=fold['training_end'])
        return result
    from .candidate import evaluate_candidate
    return evaluate_candidate(*args,fold['start'],fold['end'],unit.candidate_id,scoring_as_of=fold['scoring_as_of'],
        fit_checkpoint=fit_checkpoint,expected_fit_sha256=expected_fit_sha256)
