"""One registered annual synthetic strategy unit, with unchanged ledger rules."""
from dataclasses import asdict,dataclass
from decimal import Decimal as D
import hashlib,json
from compertum.data.calendar import session_times,utc_time
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.market import Market,load_market,WATCHLIST
from compertum.simulation.engine import _replay_market
from compertum.simulation.prediction import _label,error_metrics,rank_correlation
from compertum.simulation.policy import fixed_decimal,number
from .registry import FEATURES,VARIANTS,variant,annual_cutoff
from .checkpoints import prepare_fit_checkpoint,read_fit_checkpoint
from .features import feature_vector
from .ridge import predict

@dataclass(frozen=True)
class CandidateResult:
    content:bytes
    sha256:str


class _CandidateMarket(Market):
    def __init__(self,market,candidate,model):
        super().__init__(market.symbols,market.sectors,market.rows,market.actions,market.sha256)
        self.candidate=candidate;self.model=model;self.cache={}

    def features(self,symbol,day,horizon):
        if horizon!=self.candidate.horizon:raise DataError('CANDIDATE_HORIZON_MISMATCH')
        key=(symbol,day)
        if key not in self.cache:
            value,reason=super().features(symbol,day,horizon)
            if reason is None:
                value=dict(value,momentum_prediction=value['prediction'],features=None,feature_sha256=None)
                if self.model is not None:
                    try:
                        vector=self._vector(symbol,day)
                        if not vector.raw_eligible:raise DataError('INELIGIBLE_RAW_PRICE_OR_VOLUME')
                        prediction=self._prediction(vector.values)
                        value.update(prediction=D(str(prediction)),features=vector.values,feature_sha256=vector.input_sha256)
                    except DataError as exc:value=None;reason=exc.code
            self.cache[key]=(value,reason)
        return self.cache[key]

    def _vector(self,symbol,day):return feature_vector(self,symbol,day)

    def _prediction(self,values):return predict(self.model,[values],feature_names=FEATURES)[0]

    def replay_metadata(self):
        return {'policy':'registered-candidate-synthetic-v1','candidate_id':self.candidate.candidate_id,'model_sha256':self.model.sha256 if self.model else None,'financial_accepted':False,'fit_activation':'SYNTHETIC_FIT_AUDIT_READY_ASSUMPTION'}


def _dates(start,end):
    session_times(start);session_times(end)
    if start>end:raise DataError('INVALID_SEGMENT')
    dates=[start]
    while dates[-1]!=end:
        if len(dates)>=1024:raise DataError('INPUT_BOUND')
        dates.append(session_times(dates[-1]).next_date)
    return dates


def _predictions(market,dates,as_of):
    h=market.candidate.horizon;rows=[];omissions=[];daily=[];feature_eligible=0;eligible=0
    for i,day in enumerate(dates):
        t=session_times(day);day_rows=[]
        for symbol in WATCHLIST:
            reason=None
            if symbol not in market.symbols:reason='MISSING_SYMBOL'
            elif t.decision>as_of:reason='DECISION_UNAVAILABLE'
            else:
                features,reason=market.features(symbol,day,h)
                if reason is None:
                    feature_eligible+=1
                    if i+h>=len(dates):reason='HORIZON_BOUNDARY'
                    else:
                        eligible+=1;exit_day=dates[i+h];label,reason=_label(market,symbol,day,exit_day)
                        if reason is None and label['available']>as_of:reason='LABEL_UNAVAILABLE'
            if reason:
                omissions.append({'session':day,'symbol':symbol,'reason':reason});continue
            prediction=features['prediction'];target=label['target']
            row={'session':day,'symbol':symbol,'decision_at':t.decision.isoformat(),'entry_at':t.entry.isoformat(),'exit_at':session_times(exit_day).entry.isoformat(),'label_available_at':label['available'].isoformat(),'entry_revision':label['entry_revision'],'exit_revision':label['exit_revision'],'split_actions':label['split_actions'],'prediction':number(prediction),'momentum_prediction':number(features['momentum_prediction']),'target':number(target),'signed_error':number(prediction-target),'features':features['features'],'feature_sha256':features['feature_sha256']}
            rows.append(row);day_rows.append(row)
        correlation=rank_correlation([D(r['prediction']) for r in day_rows],[D(r['target']) for r in day_rows])
        daily.append({'session':day,'observations':len(day_rows),'spearman':correlation,'status':'NO_SCORED_ROWS' if not day_rows else 'DEFINED' if correlation is not None else 'UNDEFINED_CONSTANT_OR_TOO_FEW_ROWS'})
    targets=[D(r['target']) for r in rows]
    actual=error_metrics([D(r['prediction']) for r in rows],targets)
    momentum=error_metrics([D(r['momentum_prediction']) for r in rows],targets)
    improvement=actual['mse_improvement']
    ml=('NOT_APPLICABLE' if market.model is None else 'UNDEFINED' if improvement is None else 'PASS' if D(improvement)>=D('.01') else 'FAIL')
    assert len(rows)+len(omissions)==len(dates)*12
    return {'coverage':{'candidate_rows':len(dates)*12,'feature_eligible_rows':feature_eligible,'eligible_rows':eligible,'scored_rows':len(rows),'omitted_rows':len(omissions)},'scoring_as_of':as_of.isoformat(),'metrics':actual,'momentum_metrics':momentum,'ml_contribution_gate':ml,'daily_rank_correlation':daily,'rows':rows,'omissions':omissions}


@fixed_decimal
def evaluate_candidate(chunks,sectors,training_start,training_end,start,end,candidate_id,*,scoring_as_of,fit_checkpoint=None,expected_fit_sha256=None):
    """Pure synthetic diagnostic. A successful unit cannot approve a campaign."""
    candidate=variant(candidate_id);dates=_dates(start,end);_dates(training_start,training_end)
    year=int(start[:4]);cutoff=annual_cutoff(year)
    if start[:4]!=end[:4] or not '2016-01-01'<=training_start<=training_end<cutoff.date().isoformat()<=start:
        raise DataError('INVALID_ANNUAL_FOLD')
    as_of=utc_time(scoring_as_of);base=load_market(chunks,sectors)
    if any(not '2016-01-01'<=day<'2024-01-01' for _,day,_ in base.rows):raise DataError('DEVELOPMENT_PRICES_ONLY')
    assembly=manifest=model=None
    if candidate.kind=='ridge':
        if fit_checkpoint is None:
            if expected_fit_sha256 is not None:raise DataError('FIT_CHECKPOINT_INVALID')
            fit_checkpoint=prepare_fit_checkpoint(chunks,sectors,training_start,training_end,year,candidate_id)
            expected_fit_sha256=fit_checkpoint.sha256
        assembly,manifest,model=read_fit_checkpoint(fit_checkpoint,expected_sha256=expected_fit_sha256,market_sha256=base.sha256,candidate_id=candidate_id,year=year,training_start=training_start,training_end=training_end)
    elif fit_checkpoint is not None or expected_fit_sha256 is not None:raise DataError('FIT_CHECKPOINT_INVALID')
    market=_CandidateMarket(base,candidate,model)
    replays={}
    for cost in [10,20]:
        value=json.loads(_replay_market(market,start,end,candidate.horizon,cost_bps=cost).content)
        value['portfolios']['strategy']=value['portfolios'].pop('momentum');replays[str(cost)]=value
    predictions=_predictions(market,dates,as_of)
    value={'schema':'synthetic-candidate-fold-v1','status':'SYNTHETIC_ENGINEERING','financial_accepted':False,'full_M2':False,'candidate':asdict(candidate),'registered_family':[asdict(v) for v in VARIANTS],'year':year,'training_start':training_start,'training_end':training_end,'start':start,'end':end,'market_sha256':base.sha256,'coverage_status':'DIAGNOSTIC_PARTIAL_DEVELOPMENT_FOLD','fit_activation':'SYNTHETIC_FIT_AUDIT_READY_ASSUMPTION','dataset_assembly':json.loads(assembly.content) if assembly else None,'fit_rows':json.loads(assembly.rows.content) if assembly else None,'fit_manifest':json.loads(manifest.content) if manifest else None,'fit_manifest_sha256':manifest.sha256 if manifest else None,'model':json.loads(model.content) if model else None,'model_sha256':model.sha256 if model else None,'prediction_report':predictions,'replays':replays,'assumptions':['SYNTHETIC_ONLY','SIMULATED_AVAILABILITY','PARTIAL_TRAINING_AND_SCORING_WINDOWS','NO_FINANCIAL_QUALIFICATION','NO_ACTUAL_FIT_ACTIVATION_APPROVAL']}
    content=canonical(value)
    if len(content)>16*1024**2:raise DataError('OUTPUT_BOUND')
    return CandidateResult(content,hashlib.sha256(content).hexdigest())
