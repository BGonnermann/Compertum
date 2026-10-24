"""Deflated Sharpe ratio (Bailey and López de Prado, 2014) with the total trial count across all campaigns.

Section 19: the Validator raises the bar as the total number of tried ideas grows. This module is deterministic code.
The engine never changes it. Stage E4.

Terms. SR is the per-period Sharpe ratio of a candidate (mean return over sample standard deviation, not annualized).
T is the number of returns. The expected maximum Sharpe ratio SR0 of N trials with Sharpe variance V is
SR0 = sqrt(V) * ((1 - g) * Z(1 - 1/N) + g * Z(1 - 1/(N e))), with Z the standard normal quantile and g the
Euler-Mascheroni constant. The deflated Sharpe ratio is the probabilistic Sharpe ratio against SR0:
DSR = Phi((SR - SR0) * sqrt(T - 1) / sqrt(1 - skew * SR + (kurtosis - 1) / 4 * SR^2)).
A candidate passes the deflation gate when DSR >= DSR_MIN. The minimum is fixed here; only the owner changes it.

The trial variance V is the sample variance of the per-period Sharpe ratios of all recorded trials, never below the
null sampling variance of one estimate, (1 + SR^2 / 2) / (T - 1) (Lo, 2002). So the bar never drops to zero when few
trials are recorded or all recorded trials scored the same.
"""
from decimal import Decimal,localcontext
import math
from compertum.runtime.errors import RuntimeRefused

GAMMA=0.5772156649015329  # Euler-Mascheroni constant
DSR_MIN=Decimal('0.95')
BASE_FAMILY=12  # the fixed section 10 family size; the engine's total trial count can only raise it
MIN_OBSERVATIONS=4
MAX_TRIALS=10**9
PLACES=Decimal('1e-8')
RULE='pass: deflated Sharpe ratio (probabilistic Sharpe ratio against the expected maximum Sharpe ratio of all trials) >= 0.95'


def _fixed(value):
    return format(value.quantize(PLACES),'f')


def _text(value):
    return None if value is None else _fixed(Decimal(repr(float(value))))


def _number(value):
    try: number=Decimal(value) if isinstance(value,str) else value
    except ArithmeticError: raise RuntimeRefused('ENGINE_DEFLATION_DENIED') from None
    if not isinstance(number,Decimal) or not number.is_finite(): raise RuntimeRefused('ENGINE_DEFLATION_DENIED')
    return number


def normal_cdf(z):
    return 0.5*math.erfc(-z/math.sqrt(2))


def normal_quantile(p):
    """Inverse of normal_cdf by bisection. Deterministic; exact to the float limit."""
    if not isinstance(p,float) or not 0<p<1: raise RuntimeRefused('ENGINE_DEFLATION_DENIED')
    low,high=-40.0,40.0
    for _ in range(200):
        mid=(low+high)/2
        if normal_cdf(mid)<p: low=mid
        else: high=mid
    return (low+high)/2


def moments(returns):
    """Per-period Sharpe ratio, skewness and kurtosis of a return series (strings or Decimals). At least 4 returns."""
    if not isinstance(returns,(list,tuple)) or len(returns)<MIN_OBSERVATIONS: raise RuntimeRefused('ENGINE_DEFLATION_DENIED')
    values=[_number(x) for x in returns]
    with localcontext() as ctx:
        ctx.prec=28
        zero=Decimal(0);n=len(values);mean=sum(values,zero)/n;deviations=[v-mean for v in values]
        squares=sum((d*d for d in deviations),zero);m2=squares/n
        if m2==0: return {'observations':n,'sharpe_per_period':None,'sharpe_status':'UNDEFINED','skewness':None,'kurtosis':None}
        sharpe=mean/(squares/(n-1)).sqrt()
        skewness=(sum((d**3 for d in deviations),zero)/n)/(m2**Decimal('1.5'));kurtosis=(sum((d**4 for d in deviations),zero)/n)/(m2*m2)
        return {'observations':n,'sharpe_per_period':_fixed(sharpe),'sharpe_status':'DEFINED','skewness':_fixed(skewness),'kurtosis':_fixed(kurtosis)}


def trial_variance(sharpes,candidate):
    """Variance of the recorded trials' per-period Sharpe ratios, floored at the null sampling variance of the candidate's estimate."""
    values=[float(_number(s)) for s in sharpes if s is not None]
    if type(candidate.get('observations')) is not int or candidate['observations']<MIN_OBSERVATIONS: raise RuntimeRefused('ENGINE_DEFLATION_DENIED')
    sample=None
    if len(values)>=2:
        mean=sum(values)/len(values);sample=sum((v-mean)**2 for v in values)/(len(values)-1)
    sr=float(_number(candidate['sharpe_per_period'])) if candidate.get('sharpe_per_period') is not None else 0.0
    floor=(1+sr*sr/2)/(candidate['observations']-1)
    return {'trial_sharpes':len(values),'sample_variance':_text(sample),'floor_variance':_text(floor),'trial_variance':_text(max(sample or 0.0,floor))}


def expected_max_sharpe(trials,variance):
    """SR0 for N trials with Sharpe variance V. One trial has no selection effect: SR0 = 0."""
    if type(trials) is not int or not 1<=trials<=MAX_TRIALS: raise RuntimeRefused('ENGINE_DEFLATION_DENIED')
    v=float(_number(variance))
    if v<0: raise RuntimeRefused('ENGINE_DEFLATION_DENIED')
    if trials==1: return 0.0
    return math.sqrt(v)*((1-GAMMA)*normal_quantile(1-1/trials)+GAMMA*normal_quantile(1-1/(trials*math.e)))


def probabilistic_sharpe(sharpe,benchmark,observations,skewness,kurtosis):
    """Phi of the standardized distance between the estimate and the benchmark. None when the moment term is not positive."""
    if type(observations) is not int or observations<MIN_OBSERVATIONS: raise RuntimeRefused('ENGINE_DEFLATION_DENIED')
    term=1-skewness*sharpe+(kurtosis-1)/4*sharpe*sharpe
    if term<=0: return None
    return normal_cdf((sharpe-benchmark)*math.sqrt(observations-1)/math.sqrt(term))


def family_size(trials):
    """The section 10 confidence-bound family size grows to the total trial count and never falls below the fixed 12."""
    if type(trials) is not int or not 1<=trials<=MAX_TRIALS: raise RuntimeRefused('ENGINE_DEFLATION_DENIED')
    return max(BASE_FAMILY,trials)


def deflated_sharpe(candidate,trials,variance):
    """The deflation record for one candidate: its moments, the trial count, SR0, the DSR and PASS, FAIL or UNDEFINED."""
    sr0=expected_max_sharpe(trials,variance)
    record={'trials':trials,'trial_variance':_fixed(_number(variance)),'expected_max_sharpe':_text(sr0),'observations':candidate['observations'],
            'sharpe_per_period':candidate['sharpe_per_period'],'skewness':candidate['skewness'],'kurtosis':candidate['kurtosis'],
            'minimum':str(DSR_MIN),'section_10_family_size':family_size(trials),'rule':RULE}
    if candidate.get('sharpe_status')!='DEFINED' or candidate['sharpe_per_period'] is None:
        record.update(deflated_sharpe=None,status='UNDEFINED');return record
    p=probabilistic_sharpe(float(_number(candidate['sharpe_per_period'])),sr0,candidate['observations'],
                           float(_number(candidate['skewness'])),float(_number(candidate['kurtosis'])))
    if p is None: record.update(deflated_sharpe=None,status='UNDEFINED');return record
    # The gate compares the unrounded value; the record keeps the 8-place text.
    exact=Decimal(repr(float(p)))
    record.update(deflated_sharpe=_fixed(exact),status='PASS' if exact>=DSR_MIN else 'FAIL');return record
