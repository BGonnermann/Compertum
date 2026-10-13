"""Pure synthetic qualification arithmetic; no data reader or promotion authority."""
from dataclasses import dataclass
from decimal import Decimal as D, DecimalException
import base64
import hashlib
import json
import re
import numpy as np
from compertum.data.calendar import session_times
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.market import WATCHLIST
from compertum.simulation.metrics import metrics
from compertum.simulation.prediction import error_metrics
from compertum.simulation.policy import fixed_decimal, number
from .registry import variant

DRAWS=10000
BLOCK=21
SEED=1731
FAMILY=12
MAX_SESSIONS=1024

@dataclass(frozen=True)
class BootstrapResult:
    content: bytes
    sha256: str

@dataclass(frozen=True)
class HoldingInterval:
    symbol: str
    entry: int
    exit: int

@dataclass(frozen=True)
class EvaluationSegment:
    start: int
    end: int
    anchor: int | None

@dataclass(frozen=True)
class PredictionRow:
    session: str
    symbol: str
    prediction: D
    momentum: D
    target: D

@dataclass(frozen=True)
class QualificationInput:
    protocol_sha256: str
    candidate_id: str
    mode: str
    sessions: tuple
    navs: tuple
    benchmark: tuple
    stress_navs: tuple
    stress_benchmark: tuple
    segments: tuple
    checkpoints: tuple
    intervals: tuple
    predictions: tuple=()

@dataclass(frozen=True)
class QualificationResult:
    content: bytes
    sha256: str


def _require(condition):
    if not condition: raise DataError('INVALID_QUALIFICATION_INPUT')


def _numbers(values, *, nav=False):
    _require(type(values) is tuple and len(values)<=MAX_SESSIONS+1)
    for x in values:
        _require(type(x) is D and x.is_finite())
        _require(x.copy_abs()<=D('1e32') and (x==0 or x.copy_abs()>=D('1e-64')))
        if nav: _require(x>0)


def _draw_means(excess, starts):
    """Bound temporary arrays to 64 draws, not 10000 expanded paths."""
    n=len(excess);offset=np.arange(BLOCK,dtype=np.int64)
    means=np.empty(DRAWS,dtype=np.float64)
    for i in range(0,DRAWS,64):
        indices=((starts[i:i+64,:,None]+offset)%n).reshape(-1,starts.shape[1]*BLOCK)[:,:n]
        means[i:i+64]=excess[indices].mean(axis=1,dtype=np.float64)
    return means


@fixed_decimal
def bootstrap_excess(strategy, benchmark):
    """Paired circular bootstrap with losslessly encoded sampled indices."""
    _numbers(strategy);_numbers(benchmark)
    _require(1<=len(strategy)==len(benchmark)<=MAX_SESSIONS)
    _require(all(x>D(-1) for x in (*strategy,*benchmark)))
    n=len(strategy);blocks=(n+BLOCK-1)//BLOCK
    excess=np.asarray([float(a-b) for a,b in zip(strategy,benchmark)],dtype=np.float64)
    starts=np.random.Generator(np.random.PCG64(SEED)).integers(0,n,size=(DRAWS,blocks),dtype=np.int64)
    means=_draw_means(excess,starts)
    _require(bool(np.isfinite(means).all()))
    lower=float(np.quantile(means,.05/FAMILY,method='linear'))
    packed=starts.astype('<u2').tobytes(order='C')
    inputs={'strategy':[number(x) for x in strategy],'benchmark':[number(x) for x in benchmark]}
    value={'schema':'paired-circular-bootstrap-v1','input_sha256':hashlib.sha256(canonical(inputs)).hexdigest(),
        'observations':n,'draws':DRAWS,'block_sessions':BLOCK,'family_size':FAMILY,'seed':SEED,
        'numpy_version':np.__version__,'rng':'numpy.random.Generator(PCG64)',
        'integer_call':'integers(0,n,size=(10000,ceil(n/21)),dtype=int64)',
        'indices':{'encoding':'block-starts-u16le-row-major-v1','shape':[DRAWS,blocks],
            'expansion':'(start+offset)%n; offset=0..20; concatenate blocks; truncate each draw to n',
            'sha256':hashlib.sha256(packed).hexdigest(),'base64':base64.b64encode(packed).decode('ascii')},
        'draw_means_hex':[float(x).hex() for x in means],
        'quantile':{'q':.05/FAMILY,'method':'linear'},'lower_daily':repr(lower),
        'lower_annual':repr(252*lower),'positive_bound':lower>0,
        'coverage':'APPROXIMATE_NOT_GUARANTEED'}
    raw=canonical(value);_require(len(raw)<=2*1024**2)
    return BootstrapResult(raw,hashlib.sha256(raw).hexdigest())


def _input(value):
    _require(type(value) is QualificationInput)
    _require(type(value.protocol_sha256) is str and re.fullmatch('[0-9a-f]{64}',value.protocol_sha256) is not None)
    candidate=variant(value.candidate_id)
    _require(value.mode in ('HISTORICAL','FORWARD'))
    dates=value.sessions;n=len(dates)
    _require(type(dates) is tuple and 1<=n<=MAX_SESSIONS)
    for day in dates: session_times(day)
    _require(all(session_times(a).next_date==b for a,b in zip(dates,dates[1:])))
    if value.mode=='HISTORICAL': _require(all('2024-01-01'<=d<='2025-12-31' for d in dates))
    else: _require(n==252)
    for seq in (value.navs,value.benchmark,value.stress_navs,value.stress_benchmark):
        _numbers(seq,nav=True);_require(len(seq)==n+1 and seq[0]==D(10000))
    points=value.checkpoints
    _require(type(points) is tuple and all(type(i) is int and 0<=i<n for i in points))
    _require(list(points)==sorted(set(points)))
    segments=value.segments
    _require(type(segments) is tuple and 1<=len(segments)<=2 and all(type(s) is EvaluationSegment for s in segments))
    expected_boundaries=[0]+([i for i in range(1,n) if dates[i][:4]!=dates[i-1][:4]] if value.mode=='HISTORICAL' else [])+[n]
    _require(len(segments)==len(expected_boundaries)-1)
    expected_points=[]
    for segment,a,b in zip(segments,expected_boundaries,expected_boundaries[1:]):
        _require(type(segment.start) is int and type(segment.end) is int and (segment.start,segment.end)==(a,b-1))
        _require(segment.anchor is None or type(segment.anchor) is int and a<=segment.anchor<b)
        if segment.anchor is not None:expected_points.extend(range(segment.anchor,b,candidate.horizon))
    _require(tuple(expected_points)==points)
    intervals=value.intervals
    _require(type(intervals) is tuple and len(intervals)<=12*MAX_SESSIONS)
    _require(all(type(i) is HoldingInterval for i in intervals))
    identities=[]
    for interval in intervals:
        _require(interval.symbol in WATCHLIST and type(interval.entry) is int and type(interval.exit) is int)
        _require(0<=interval.entry<interval.exit<n and interval.exit-interval.entry==candidate.horizon)
        _require(interval.entry in points and interval.exit in points)
        _require(any(s.start<=interval.entry<interval.exit<=s.end for s in segments))
        identities.append((interval.symbol,interval.entry,interval.exit))
    _require(len(identities)==len(set(identities)))
    _require(all(sum(i.entry==entry for i in intervals)<=3 for entry in {i.entry for i in intervals}))
    rows=value.predictions
    _require(type(rows) is tuple and len(rows)<=12*n and all(type(r) is PredictionRow for r in rows))
    keys=[]
    for row in rows:
        _require(row.session in dates and row.symbol in WATCHLIST)
        _numbers((row.prediction,row.momentum,row.target))
        _require(row.target>D(-1))
        if candidate.kind=='momentum':_require(row.prediction==row.momentum)
        keys.append((row.session,row.symbol))
    _require(len(keys)==len(set(keys)) and keys==sorted(keys))
    return candidate


@fixed_decimal
def qualify_synthetic(value):
    """Report arithmetic only. A caller cannot assert an audit or paper approval."""
    try:
        c=_input(value);n=len(value.sessions)
        base=metrics(list(value.navs),list(value.benchmark))
        stress=metrics(list(value.stress_navs),list(value.stress_benchmark))
        strategy=tuple(map(D,base['returns']));benchmark=tuple(map(D,base['benchmark_returns']))
        excess=tuple(a-b for a,b in zip(strategy,benchmark))
        mean=sum(strategy)/n
        variance=sum((x-mean)**2 for x in strategy)/(n-1) if n>1 else None
        # Avoid square-root rounding moving the exact inclusive .75 boundary.
        sharpe_pass=variance is not None and variance>0 and mean>=0 and 252*mean*mean>=D('.75')**2*variance
        boot=bootstrap_excess(strategy,benchmark)
        if value.mode=='HISTORICAL':
            groups={str(y):[d for day,d in zip(value.sessions,excess) if day[:4]==str(y)] for y in (2024,2025)}
            complete=value.sessions[0]=='2024-01-02' and value.sessions[-1]=='2025-12-31'
        else:
            groups={'first_126':excess[:126],'second_126':excess[126:]};complete=True
        periods={k:number(sum(v)/len(v)) if v else None for k,v in groups.items()}
        gates={'complete_window':complete,'daily_observations':n>=(400 if value.mode=='HISTORICAL' else 252),
            'scheduled_checkpoints':len(value.checkpoints)>=12,'completed_holding_intervals':len(value.intervals)>=30,
            'annual_mean_excess':D(base['annual_mean_excess'])>=D('.02'),
            'sharpe':sharpe_pass,
            'max_drawdown':D(base['max_drawdown'])<=D('.15'),
            'period_excess':all(x is not None and D(x)>=0 for x in periods.values()),
            'confidence_lower_bound':json.loads(boot.content)['positive_bound'],
            'stress_excess':D(stress['annual_mean_excess'])>=0,
            'stress_drawdown':D(stress['max_drawdown'])<=D('.20')}
        rows=value.predictions;targets=[r.target for r in rows]
        predictive=error_metrics([r.prediction for r in rows],targets)
        momentum=error_metrics([r.momentum for r in rows],targets)
        improvement=predictive['mse_improvement']
        ml='NOT_APPLICABLE' if c.kind=='momentum' else 'UNDEFINED' if improvement is None else 'PASS' if D(improvement)>=D('.01') else 'FAIL'
        inputs={'protocol_sha256':value.protocol_sha256,'candidate_id':value.candidate_id,'mode':value.mode,
            'sessions':list(value.sessions),'costs_bps_per_side':[10,20],'benchmark_policy':'SPY60_CASH40',
            'navs':[number(x) for x in value.navs],'benchmark':[number(x) for x in value.benchmark],
            'stress_navs':[number(x) for x in value.stress_navs],'stress_benchmark':[number(x) for x in value.stress_benchmark],
            'segment_policy':'HISTORICAL_ANNUAL_FORWARD_CONTINUOUS',
            'segments':[{'start':s.start,'end':s.end,'anchor':s.anchor} for s in value.segments],
            'checkpoints':list(value.checkpoints),'intervals':[{'symbol':i.symbol,'entry':i.entry,'exit':i.exit} for i in value.intervals],
            'predictions':[{'session':r.session,'symbol':r.symbol,'prediction':number(r.prediction),'momentum':number(r.momentum),'target':number(r.target)} for r in rows]}
        report={'schema':'synthetic-qualification-v1','status':'SYNTHETIC_ENGINEERING','financial_accepted':False,
            'paper_eligible':False,'strategy_accepted':False,'inputs':inputs,'input_sha256':hashlib.sha256(canonical(inputs)).hexdigest(),
            'metrics':base,'sharpe_gate_method':'variance>0 and mean>=0 and 252*mean^2>=0.75^2*sample_variance; no epsilon','stress_metrics':stress,'period_mean_daily_excess':periods,'numeric_gates':gates,
            'trading_arithmetic_pass':all(gates.values()),'bootstrap':json.loads(boot.content),'bootstrap_sha256':boot.sha256,
            'prediction':predictive,'momentum_prediction':momentum,'ml_contribution_gate':ml,
            'external_gates':{k:'UNVERIFIED' for k in ('data','timing','risk','reproducibility','independent_audit','sealed_window')},
            'trust_basis':'SYNTHETIC_CALLER_NAV_INTERVAL_PREDICTION_ASSERTIONS_REQUIRE_INDEPENDENT_AUDIT'}
        raw=canonical(report);_require(len(raw)<=16*1024**2)
        return QualificationResult(raw,hashlib.sha256(raw).hexdigest())
    except (ValueError,TypeError,KeyError,AttributeError,DecimalException,OverflowError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('INVALID_QUALIFICATION_INPUT') from exc

