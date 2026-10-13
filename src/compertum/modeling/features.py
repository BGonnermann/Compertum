"""Fixed causal daily features from already validated raw market snapshots."""
from dataclasses import dataclass
from decimal import Decimal as D,DecimalException
import hashlib
import numpy as np
from compertum.data.calendar import session_times,utc_time
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.market import Market,WATCHLIST
from compertum.simulation.policy import fixed_decimal
from .registry import FEATURES

@dataclass(frozen=True)
class FeatureVector:
    names:tuple
    values:tuple
    feature_session:str
    decision_at:str
    available_at:str
    availability_basis:str
    input_sha256:str
    raw_close:float
    raw_mean_dollar_volume_20:float
    raw_eligible:bool
    financial_accepted:bool=False


def _number(value,*,zero=False):
    if type(value) is not str:raise DataError('INVALID_FEATURE_NUMBER')
    try:number=D(value)
    except DecimalException:raise DataError('INVALID_FEATURE_NUMBER') from None
    if not number.is_finite() or number<0 or (not zero and number==0):raise DataError('INVALID_FEATURE_NUMBER')
    return number


def _history(market,symbol,day):
    t=session_times(day);date=t.previous_date;rows=[];availability=[]
    for _ in range(252):
        row=market.rows.get((symbol,date,'daily'))
        if row is None:raise DataError('FEATURE_COVERAGE')
        at=max(utc_time(row['simulated_available_at']),utc_time(row['simulated_revision_available_at']))
        if at>t.decision:raise DataError('FEATURE_UNAVAILABLE')
        rows.append(row);availability.append(at);date=session_times(date).previous_date
    applied=[]
    for action in market.actions:
        if action['symbol']==symbol and action['kind']=='SPLIT' and rows[-1]['session_date']<action['effective_session']<=rows[0]['session_date']:
            known=utc_time(action['simulated_known_at'])
            if known>t.decision:raise DataError('ACTION_UNAVAILABLE')
            _number(action['factor']);applied.append(action);availability.append(known)
    adjusted_prices=[];adjusted_volumes=[];raw_prices=[];raw_volumes=[]
    for row in rows:
        price=_number(row['close']);volume=_number(row['volume'],zero=True);factor=D(1)
        for action in applied:
            if row['session_date']<action['effective_session']:factor*=_number(action['factor'])
        adjusted_prices.append(float(price/factor));adjusted_volumes.append(float(volume*factor))
        raw_prices.append(price);raw_volumes.append(volume)
    return np.array(adjusted_prices,dtype=np.float64),np.array(adjusted_volumes,dtype=np.float64),rows,applied,max(availability),raw_prices,raw_volumes


def _price_features(prices):
    returns=prices[:-1]/prices[1:]-1
    return [float(prices[0]/prices[h]-1) for h in (1,5,21,63)]+[float(np.std(returns[:h],ddof=1)*np.sqrt(252)) for h in (20,63)]


@fixed_decimal
def feature_vector(market,symbol,day):
    """Engineering vector only. Caller owns snapshot and financial qualification."""
    if not isinstance(market,Market) or symbol not in WATCHLIST or symbol not in market.symbols:raise DataError('INVALID_FEATURE_MARKET')
    t=session_times(day)
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise',under='ignore'):
            asset=_history(market,symbol,day);spy=_history(market,'SPY',day)
            prices,volumes,rows,actions,available,raw_prices,raw_volumes=asset
            spy_prices,spy_volumes,spy_rows,spy_actions,spy_available,_,_=spy
            if not all(np.isfinite(a).all() for a in (prices,volumes,spy_prices,spy_volumes)):raise DataError('NONFINITE_FEATURE')
            denominators=[float(prices[:h].mean()) for h in (20,63)]+[float(volumes[:20].mean())]
            if any(v<=0 for v in denominators) or np.any(prices<=0) or np.any(spy_prices<=0):raise DataError('NONPOSITIVE_DENOMINATOR')
            values=_price_features(prices)+[float(prices[0]/v-1) for v in denominators[:2]]+[float(volumes[0]/denominators[2])]+_price_features(spy_prices)
            if len(values)!=len(FEATURES) or not np.isfinite(values).all():raise DataError('NONFINITE_FEATURE')
        dollar_volume=sum(p*v for p,v in zip(raw_prices[:20],raw_volumes[:20]))/20
        digest=hashlib.sha256(canonical({'schema':'fixed-features-v1','symbol':symbol,'decision_at':t.decision.isoformat(),'feature_order':FEATURES,'asset_rows':rows,'spy_rows':spy_rows,'asset_splits':actions,'spy_splits':spy_actions})).hexdigest()
        return FeatureVector(FEATURES,tuple(values),t.previous_date,t.decision.isoformat(),max(available,spy_available).isoformat(),'SIMULATED_AVAILABILITY',digest,float(raw_prices[0]),float(dollar_volume),raw_prices[0]>=5 and dollar_volume>=1000000)
    except (DecimalException,FloatingPointError,OverflowError) as exc:raise DataError('NUMERICAL_FEATURE_FAILURE') from exc
