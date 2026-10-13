"""Bounded synthetic campaign reporting; never a financial shortlist authority."""
from dataclasses import asdict,dataclass
from decimal import Decimal as D,DecimalException
import hashlib,json,re
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.data.calendar import session_times,utc_time
from compertum.simulation.market import WATCHLIST
from compertum.simulation.metrics import metrics
from compertum.simulation.prediction import error_metrics,rank_correlation
from compertum.simulation.policy import fixed_decimal,number
from .registry import VARIANTS,variant,annual_cutoff,FEATURES
from .candidate import CandidateResult,_dates
from .ridge import RidgeArtifact,predict

YEARS=(2021,2022,2023)

@dataclass(frozen=True)
class FailedFold:
    candidate_id:str
    year:int
    reason:str

@dataclass(frozen=True)
class CampaignScorecard:
    content:bytes
    sha256:str


def _require(condition):
    if not condition:raise DataError('INVALID_SCORECARD_EVIDENCE')


def _decimal(value,positive=False):
    _require(type(value) is str);v=D(value)
    _require(v.is_finite() and abs(v)<=D('1e32') and (not positive or v>0))
    return v


def _read(result):
    _require(type(result) is CandidateResult and type(result.content) is bytes and len(result.content)<=16*1024**2)
    _require(hashlib.sha256(result.content).hexdigest()==result.sha256)
    v=json.loads(result.content);_require(canonical(v)==result.content)
    _require(v['schema']=='synthetic-candidate-fold-v1' and v['status']=='SYNTHETIC_ENGINEERING' and v['financial_accepted'] is False and v['full_M2'] is False)
    c=variant(v['candidate']['candidate_id']);_require(canonical(v['candidate'])==canonical(asdict(c)))
    _require(canonical(v['registered_family'])==canonical([asdict(c) for c in VARIANTS]))
    year=v['year'];_require(type(year) is int and year in YEARS)
    dates=_dates(v['start'],v['end']);_dates(v['training_start'],v['training_end'])
    _require(v['start'][:4]==v['end'][:4]==str(year) and '2016-01-01'<=v['training_start']<=v['training_end']<annual_cutoff(year).date().isoformat()<=v['start'])
    _require(type(v['market_sha256']) is str and re.fullmatch('[0-9a-f]{64}',v['market_sha256']) is not None)
    _require(v['coverage_status']=='DIAGNOSTIC_PARTIAL_DEVELOPMENT_FOLD')
    _require(set(v['replays'])=={'10','20'})
    for cost,replay in v['replays'].items():
        _require(replay['candidate_id']==c.candidate_id and type(replay['horizon']) is int and replay['horizon']==c.horizon and type(replay['cost_bps']) is int and replay['cost_bps']==int(cost))
        _require(replay['policy']=='registered-candidate-synthetic-v1' and replay['financial_accepted'] is False and replay['financial_status']=='SYNTHETIC_UNVERIFIED')
        _require((replay['start'],replay['end'],replay['market_sha256'],replay['model_sha256'])==(v['start'],v['end'],v['market_sha256'],v['model_sha256']))
        portfolios=replay['portfolios'];_require(set(portfolios)=={'strategy','spy60','spy100','equal60','zero'})
        benchmark=[D(10000)]+[_decimal(r['nav'],True) for r in portfolios['spy60']['days']]
        for p in portfolios.values():
            _require([r['session'] for r in p['days']]==dates)
            calculated=metrics([D(10000)]+[_decimal(r['nav'],True) for r in p['days']],benchmark)
            _require(canonical(calculated)==canonical(p['metrics']))
            checkpoints=p['checkpoints'];_require(type(checkpoints) is list and all(type(i) is int and 0<=i<len(dates) for i in checkpoints) and checkpoints==sorted(set(checkpoints)))
            _require(type(p['completed_intervals']) is int and p['completed_intervals']>=0)
            _require(all(_decimal(t['turnover'])>=0 for t in p['trades']))
    report=v['prediction_report'];asof=utc_time(report['scoring_as_of']);rows=report['rows'];omissions=report['omissions']
    _require(type(rows) is list and type(omissions) is list)
    identities=[(r['session'],r['symbol']) for r in rows+omissions]
    _require(len(identities)==len(set(identities)) and set(identities)=={(day,s) for day in dates for s in WATCHLIST})
    coverage=report['coverage'];_require(all(type(n) is int for n in coverage.values()))
    _require(coverage['candidate_rows']==len(dates)*12 and coverage['scored_rows']==len(rows) and coverage['omitted_rows']==len(omissions))
    _require(0<=coverage['scored_rows']<=coverage['eligible_rows']<=coverage['feature_eligible_rows']<=coverage['candidate_rows'])
    for row in rows:
        i=dates.index(row['session']);t=session_times(row['session'])
        _require(i+c.horizon<len(dates) and row['decision_at']==t.decision.isoformat() and row['entry_at']==t.entry.isoformat() and row['exit_at']==session_times(dates[i+c.horizon]).entry.isoformat())
        _require(t.decision<=asof and session_times(session_times(dates[i+c.horizon]).next_date).decision<=utc_time(row['label_available_at'])<=asof)
        _require(_decimal(row['signed_error'])==_decimal(row['prediction'])-_decimal(row['target']))
    target=[_decimal(r['target']) for r in rows]
    actual=error_metrics([_decimal(r['prediction']) for r in rows],target);momentum=error_metrics([_decimal(r['momentum_prediction']) for r in rows],target)
    _require(canonical(actual)==canonical(report['metrics']) and canonical(momentum)==canonical(report['momentum_metrics']))
    daily=[]
    for day in dates:
        selected=[r for r in rows if r['session']==day]
        corr=rank_correlation([D(r['prediction']) for r in selected],[D(r['target']) for r in selected])
        daily.append({'session':day,'observations':len(selected),'spearman':corr,'status':'NO_SCORED_ROWS' if not selected else 'DEFINED' if corr is not None else 'UNDEFINED_CONSTANT_OR_TOO_FEW_ROWS'})
    _require(canonical(daily)==canonical(report['daily_rank_correlation']))
    improvement=actual['mse_improvement']
    ml='NOT_APPLICABLE' if c.kind=='momentum' else 'UNDEFINED' if improvement is None else 'PASS' if D(improvement)>=D('.01') else 'FAIL'
    _require(report['ml_contribution_gate']==ml)
    if c.kind=='momentum':
        _require(v['model'] is None and v['model_sha256'] is None and v['fit_manifest'] is None)
        _require(all(D(r['prediction'])==D(r['momentum_prediction']) for r in rows))
    else:
        model_raw=canonical(v['model']);_require(hashlib.sha256(model_raw).hexdigest()==v['model_sha256'])
        _require(v['model']['candidate_id']==c.candidate_id and v['model']['fit_cutoff']==annual_cutoff(year).isoformat())
        _require(hashlib.sha256(canonical(v['fit_manifest'])).hexdigest()==v['fit_manifest_sha256']==v['model']['fit_manifest_sha256'])
        model=RidgeArtifact(model_raw,v['model_sha256'])
        served=predict(model,[r['features'] for r in rows] or [[0.0]*len(FEATURES)],feature_names=FEATURES)
        _require(all(abs(a-float(r['prediction']))<=1e-12+1e-12*abs(a) for a,r in zip(served,rows)))
    return v


def _rank_key(row):
    p=row['trading']['10'];candidate=variant(row['candidate_id'])
    return (-D(p['metrics']['annual_mean_excess']),D(p['total_turnover']),candidate.kind!='momentum',candidate.candidate_id)


def _trading(folds,cost):
    nav=[D(10000)];bench=[D(10000)];turnover=D(0);checkpoints=intervals=0;annual=[]
    for fold in folds:
        p=fold['replays'][cost]['portfolios'];strategy=p['strategy'];benchmark=p['spy60']
        prior=prior_b=D(10000)
        for a,b in zip(strategy['days'],benchmark['days']):
            n=D(a['nav']);nb=D(b['nav']);nav.append(nav[-1]*(n/prior));bench.append(bench[-1]*(nb/prior_b));prior=n;prior_b=nb
        turnover+=sum(D(t['turnover']) for t in strategy['trades']);checkpoints+=len(strategy['checkpoints']);intervals+=strategy['completed_intervals']
        annual.append({'year':fold['year'],'annual_mean_excess':strategy['metrics']['annual_mean_excess']})
    return {'method':'CONCATENATED_FOLD_DAILY_RETURNS','observations':len(nav)-1,'metrics':metrics(nav,bench),'total_turnover':number(turnover),'rebalance_checkpoints':checkpoints,'completed_intervals':intervals,'fold_excess':annual}


@fixed_decimal
def build_scorecard(results,*,failures=()):
    """Report trusted synthetic engine artifacts; hash binding is not authentication."""
    try:
        _require(isinstance(results,(list,tuple)) and isinstance(failures,(list,tuple)) and len(results)+len(failures)<=36)
        _require(all(type(r) is CandidateResult for r in results) and sum(len(r.content) for r in results)<=128*1024**2)
        values={};digests={};failed={};year_inputs={}
        for result in results:
            v=_read(result);key=(v['candidate']['candidate_id'],v['year']);_require(key not in values)
            signature=(v['market_sha256'],v['training_start'],v['training_end'],v['start'],v['end'],v['prediction_report']['scoring_as_of'])
            _require(year_inputs.setdefault(v['year'],signature)==signature)
            values[key]=v;digests[key]=result.sha256
        for f in failures:
            _require(type(f) is FailedFold and type(f.year) is int and f.year in YEARS)
            variant(f.candidate_id);_require(type(f.reason) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',f.reason) is not None)
            key=(f.candidate_id,f.year);_require(key not in values and key not in failed);failed[key]=f.reason
        history=[];candidates=[]
        for c in VARIANTS:
            folds=[values[(c.candidate_id,y)] for y in YEARS if (c.candidate_id,y) in values]
            missing=[y for y in YEARS if (c.candidate_id,y) not in values and (c.candidate_id,y) not in failed]
            errors=[{'year':y,'reason':failed[(c.candidate_id,y)]} for y in YEARS if (c.candidate_id,y) in failed]
            row={'candidate_id':c.candidate_id,'kind':c.kind,'horizon':c.horizon,'state':'FAILED' if errors else 'COMPLETE_DIAGNOSTIC' if len(folds)==3 else 'PENDING','completed_years':[v['year'] for v in folds],'missing_years':missing,'failed_folds':errors,'trading':None,'prediction':None}
            if folds:
                row['trading']={cost:_trading(folds,cost) for cost in ['10','20']}
                rows=[r for v in folds for r in v['prediction_report']['rows']];targets=[D(r['target']) for r in rows]
                pooled=error_metrics([D(r['prediction']) for r in rows],targets);improvement=pooled['mse_improvement']
                row['prediction']={'metrics':pooled,'momentum_metrics':error_metrics([D(r['momentum_prediction']) for r in rows],targets),'coverage':{k:sum(v['prediction_report']['coverage'][k] for v in folds) for k in folds[0]['prediction_report']['coverage']},'daily_rank_correlation':[r for v in folds for r in v['prediction_report']['daily_rank_correlation']],'ml_contribution_gate':'NOT_APPLICABLE' if c.kind=='momentum' else 'UNDEFINED' if improvement is None else 'PASS' if D(improvement)>=D('.01') else 'FAIL'}
            candidates.append(row)
            for y in YEARS:
                key=(c.candidate_id,y);history.append({'candidate_id':c.candidate_id,'year':y,'state':'COMPLETED' if key in values else 'FAILED' if key in failed else 'PENDING','artifact_sha256':digests.get(key),'failure_reason':failed.get(key)})
        rankings={str(h):[r['candidate_id'] for r in sorted((r for r in candidates if r['horizon']==h and r['state']=='COMPLETE_DIAGNOSTIC'),key=_rank_key)] for h in [1,5,21]}
        value={'schema':'synthetic-campaign-scorecard-v1','financial_accepted':False,'full_M2':False,'registered_family':[asdict(c) for c in VARIANTS],'family_size':12,'counts':{'completed':len(values),'failed':len(failed),'pending':36-len(values)-len(failed)},'search_history':history,'candidates':candidates,'diagnostic_rankings':rankings,'shortlist':[],'selection_status':'UNQUALIFIED_SYNTHETIC_EVIDENCE','trust_basis':'HASH_BOUND_TRUSTED_ENGINE_OUTPUTS_NOT_AUTHENTICATED_ORIGIN'}
        raw=canonical(value);_require(len(raw)<=16*1024**2)
        return CampaignScorecard(raw,hashlib.sha256(raw).hexdigest())
    except (KeyError,ValueError,TypeError,AttributeError,DecimalException,OverflowError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('INVALID_SCORECARD_EVIDENCE') from exc
