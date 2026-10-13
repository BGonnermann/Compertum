"""Synthetic baseline prediction errors, separate from trading performance."""
from dataclasses import dataclass
from decimal import Decimal as D
import hashlib

from compertum.data.calendar import session_times,utc_time
from compertum.data.errors import DataError
from compertum.data.snapshot import canonical
from .market import load_market
from .policy import fixed_decimal,number

MAX_ROWS=12288


def _pairs(predictions,targets):
    if not isinstance(predictions,(tuple,list)) or not isinstance(targets,(tuple,list)) or len(predictions)!=len(targets) or len(predictions)>MAX_ROWS:
        raise DataError('INVALID_PREDICTION_ROWS')
    if any(not isinstance(x,D) or not x.is_finite() or x.copy_abs()>D('1e32') or 0<x.copy_abs()<D('1e-64') for x in [*predictions,*targets]):
        raise DataError('INVALID_PREDICTION_NUMBER')


@fixed_decimal
def error_metrics(predictions,targets):
    _pairs(predictions,targets);n=len(predictions)
    if not n:
        return {'observations':0,'mse':None,'mae':None,'mean_signed_error':None,'zero_mse':None,
            'zero_mae':None,'zero_mean_signed_error':None,'mse_improvement':None,'status':'NO_SCORED_ROWS'}
    errors=[p-t for p,t in zip(predictions,targets)]
    mse=sum(e*e for e in errors)/n;zero=sum(t*t for t in targets)/n
    return {'observations':n,'mse':number(mse),'mae':number(sum(map(abs,errors))/n),
        'mean_signed_error':number(sum(errors)/n),'zero_mse':number(zero),'zero_mae':number(sum(map(abs,targets))/n),
        'zero_mean_signed_error':number(-sum(targets)/n),
        'mse_improvement':number(1-mse/zero) if zero else None,
        'status':'DEFINED' if zero else 'ZERO_BASELINE_MSE'}


@fixed_decimal
def rank_correlation(predictions,targets):
    _pairs(predictions,targets)
    if len(predictions)<2:return None
    def ranks(values):
        result=[D(0)]*len(values);order=sorted(range(len(values)),key=values.__getitem__);start=0
        while start<len(order):
            end=start+1
            while end<len(order) and values[order[end]]==values[order[start]]:end+=1
            rank=D(start+1+end)/2
            for index in order[start:end]:result[index]=rank
            start=end
        return result
    a=ranks(predictions);b=ranks(targets);mean=D(len(a)+1)/2
    numerator=sum((x-mean)*(y-mean) for x,y in zip(a,b))
    denominator=(sum((x-mean)**2 for x in a)*sum((y-mean)**2 for y in b)).sqrt()
    return number(numerator/denominator) if denominator else None


@dataclass(frozen=True)
class PredictionReport:
    content:bytes
    sha256:str


def _label(market,symbol,entry_day,exit_day):
    entry=market.rows.get((symbol,entry_day,'entry'));exit=market.rows.get((symbol,exit_day,'entry'))
    if entry is None or exit is None:return None,'LABEL_REFERENCE_MISSING'
    available=max(session_times(session_times(exit_day).next_date).decision,
        *(utc_time(row[field]) for row in (entry,exit) for field in ('simulated_available_at','simulated_revision_available_at')))
    factor=D(1);actions=[]
    for action in market.actions:
        if action['symbol']==symbol and action['kind']=='SPLIT' and entry_day<action['effective_session']<=exit_day:
            factor*=D(action['factor']);available=max(available,utc_time(action['simulated_known_at']));actions.append(action['action_id'])
    return {'target':D(exit['open'])*factor/D(entry['open'])-1,'available':available,
        'entry_revision':entry['revision_id'],'exit_revision':exit['revision_id'],'split_actions':actions},None


@fixed_decimal
def score_predictions(chunks,sectors,start,end,horizon,*,scoring_as_of):
    """Score eligible daily decisions only after their complete labels are available."""
    if type(horizon) is not int or horizon not in (1,5,21):raise DataError('INVALID_PROTOCOL')
    session_times(start);session_times(end);as_of=utc_time(scoring_as_of)
    if end<start:raise DataError('INVALID_SEGMENT')
    dates=[start]
    while dates[-1]!=end:
        if len(dates)>=1024:raise DataError('INPUT_BOUND')
        dates.append(session_times(dates[-1]).next_date)
    market=load_market(chunks,sectors);symbols=[s for s in market.symbols if s!='SPY']
    rows=[];omissions=[];daily=[];eligible=0;feature_eligible=0
    for index,day in enumerate(dates):
        predictions=[];targets=[];times=session_times(day)
        for symbol in symbols:
            reason=None
            if times.decision>as_of:reason='DECISION_UNAVAILABLE'
            else:
                features,reason=market.features(symbol,day,horizon)
                if reason is None:
                    feature_eligible+=1
                    if index+horizon>=len(dates):reason='HORIZON_BOUNDARY'
                    else:
                        eligible+=1
                        exit_day=dates[index+horizon];label,reason=_label(market,symbol,day,exit_day)
                        if reason is None and label['available']>as_of:reason='LABEL_UNAVAILABLE'
            if reason:
                omissions.append({'session':day,'symbol':symbol,'reason':reason});continue
            prediction=features['prediction'];target=label['target'];predictions.append(prediction);targets.append(target)
            rows.append({'session':day,'symbol':symbol,'decision_at':times.decision.isoformat(),'entry_at':times.entry.isoformat(),
                'exit_at':session_times(exit_day).entry.isoformat(),'label_available_at':label['available'].isoformat(),
                'entry_revision':label['entry_revision'],'exit_revision':label['exit_revision'],'split_actions':label['split_actions'],
                'prediction':number(prediction),'target':number(target),'signed_error':number(prediction-target)})
        correlation=rank_correlation(predictions,targets)
        daily.append({'session':day,'observations':len(predictions),'spearman':correlation,
            'status':'NO_SCORED_ROWS' if not predictions else 'DEFINED' if correlation is not None else 'UNDEFINED_CONSTANT_OR_TOO_FEW_ROWS'})
    value={'schema_version':'1','method':'daily-momentum-price-label-v1','financial_status':'SYNTHETIC_UNVERIFIED',
        'market_sha256':market.sha256,'horizon':horizon,'start':start,'end':end,'scoring_as_of':as_of.isoformat(),
        'coverage':{'candidate_rows':len(dates)*len(symbols),'feature_eligible_rows':feature_eligible,'eligible_rows':eligible,'scored_rows':len(rows),'omitted_rows':len(omissions)},
        'metrics':error_metrics([D(r['prediction']) for r in rows],[D(r['target']) for r in rows]),
        'daily_rank_correlation':daily,'rows':rows,'omissions':omissions,
        'assumptions':['SYNTHETIC_ONLY','SIMULATED_AVAILABILITY','PRICE_RETURN_EXCLUDES_DIVIDENDS',
            'DAILY_ELIGIBLE_ROWS_NOT_TRADE_COUNT','NO_TRAINING_OR_STRATEGY_ACCEPTANCE']}
    content=canonical(value)
    if len(content)>16*1024*1024:raise DataError('OUTPUT_BOUND')
    return PredictionReport(content,hashlib.sha256(content).hexdigest())
