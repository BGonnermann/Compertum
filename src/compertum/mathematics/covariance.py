"""Section 11 covariance gates, with forecasting separate from inversion."""
from dataclasses import dataclass
import numpy as np


class CovarianceRefused(ValueError):
    """Input or numerical evidence cannot establish the required capability."""


def _array(value):
    try:
        masked=np.ma.asarray(value)
        if np.ma.getmaskarray(masked).any():
            raise CovarianceRefused('MASKED_MISSING_INPUT')
        raw=np.asarray(masked)
        if raw.dtype.kind not in 'fiu': raise CovarianceRefused('NON_REAL_NUMERIC_INPUT')
        result=raw.astype(np.float64,copy=True)
        if not np.isfinite(result).all(): raise CovarianceRefused('NONFINITE_INPUT')
        return result
    except (TypeError,ValueError,OverflowError) as exc:
        if isinstance(exc,CovarianceRefused): raise
        raise CovarianceRefused('INVALID_ARRAY') from exc


def _rows(array): return tuple(tuple(float(v) for v in row) for row in array)


def _checked_matrix(value):
    a=_array(value)
    if a.ndim!=2 or not 1<=a.shape[0]<=12 or a.shape[0]!=a.shape[1]:
        raise CovarianceRefused('FINITE_SQUARE_MATRIX_REQUIRED')
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            norm=float(np.linalg.norm(a,2)); asymmetry=float(np.linalg.norm(a-a.T,2))
            if not np.isfinite([norm,asymmetry]).all(): raise CovarianceRefused('NONFINITE_NORM')
            tolerance=1e-10*max(1.,norm)
            if asymmetry>tolerance: raise CovarianceRefused('ASYMMETRIC_MATRIX')
            b=(a+a.T)/2
            eigenvalues=np.linalg.eigvalsh(b)
            if not np.isfinite(eigenvalues).all():raise CovarianceRefused('NONFINITE_EIGENVALUES')
            if eigenvalues[0]<-tolerance:raise CovarianceRefused('INDEFINITE_MATRIX')
    except (FloatingPointError,np.linalg.LinAlgError) as exc:
        raise CovarianceRefused('NUMERICAL_MATRIX_FAILURE') from exc
    return a,b,eigenvalues,norm,tolerance


@dataclass(frozen=True)
class CovarianceAssessment:
    raw_matrix:tuple
    matrix:tuple
    eigenvalues:tuple
    norm:float
    tolerance:float
    raw_quadratic:float
    quadratic_tolerance:float
    forecast:float
    adjustment:float
    condition_number:float
    inversion_status:str
    inversion_reason:str|None
    inverse:tuple|None


def assess_covariance(matrix,weights):
    """Accept PSD quadratic forecasts; compute an inverse only behind its gates."""
    a,b,eigenvalues,norm,tolerance=_checked_matrix(matrix)
    w=_array(weights)
    if w.ndim!=1 or len(w)!=len(b):raise CovarianceRefused('WEIGHT_DIMENSION')
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            raw=float(w@b@w);eps=float(tolerance*(w@w))
        if not np.isfinite([raw,eps]).all():raise CovarianceRefused('NONFINITE_QUADRATIC')
        if raw<-eps:raise CovarianceRefused('NEGATIVE_QUADRATIC')
    except FloatingPointError as exc:raise CovarianceRefused('NUMERICAL_QUADRATIC_FAILURE') from exc
    forecast=max(0.,raw)
    # Infinite condition is an expected singular capability refusal, not a bad forecast.
    condition=float('inf')
    singular_values=np.abs(eigenvalues)
    if singular_values.min()>0:
        with np.errstate(over='ignore'):condition=float(singular_values.max()/singular_values.min())
    inverse=None;reason='EIGENVALUE_OR_CONDITION_GATE'
    if eigenvalues[0]>tolerance and condition<=1e8:
        try:
            with np.errstate(over='raise',invalid='raise',divide='raise'):candidate=np.linalg.inv(b)
            if np.isfinite(candidate).all():inverse=_rows(candidate);reason=None
            else:reason='NONFINITE_INVERSE'
        except (FloatingPointError,np.linalg.LinAlgError):reason='INVERSE_SOLVER_FAILURE'
    return CovarianceAssessment(_rows(a),_rows(b),tuple(float(v) for v in eigenvalues),norm,tolerance,
        raw,eps,forecast,forecast-raw,condition,'INVERSION_ACCEPTED' if inverse is not None else 'INVERSION_REJECTED',reason,inverse)


def shrink_covariance(matrix,delta):
    """Apply only the three registered deltas; never repair invalid covariance."""
    if type(delta) not in (int,float) or delta not in (0,.25,1):raise CovarianceRefused('UNREGISTERED_DELTA')
    _,b,_,_,_=_checked_matrix(matrix)
    with np.errstate(over='raise',invalid='raise'):
        result=(1-delta)*b+delta*np.diag(np.diag(b))
    _checked_matrix(result)
    return _rows(result)


@dataclass(frozen=True)
class SampleCovariance:
    mean:tuple
    matrix:tuple
    observations:int
    assets:int
    rank:int
    interval_ids:tuple


def sample_covariance(returns,interval_ids):
    """Pure complete-case estimator, n=2..252, p=1..12, ddof=1.

    Aligned identifiers are required but do not prove time availability. Campaign
    callers must separately prove horizons, cutoffs and at least 12 blocks.
    """
    x=_array(returns)
    if x.ndim!=2 or not 2<=x.shape[0]<=252 or not 1<=x.shape[1]<=12:
        raise CovarianceRefused('SAMPLE_DIMENSION')
    n,p=x.shape
    try:
        if len(interval_ids)!=n:raise CovarianceRefused('INTERVAL_ALIGNMENT')
        labels=[]
        for row in interval_ids:
            if len(row)!=p or any(type(v) is not str or not 1<=len(v)<=128 for v in row) or any(v!=row[0] for v in row):
                raise CovarianceRefused('INTERVAL_ALIGNMENT')
            labels.append(row[0])
        if len(set(labels))!=n:raise CovarianceRefused('DUPLICATE_INTERVAL')
    except TypeError as exc:raise CovarianceRefused('INTERVAL_ALIGNMENT') from exc
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            # Subtract a representable origin before averaging to retain small
            # differences on a large common offset; never clamp the resulting rank.
            shifted=x-x[0];offset_mean=shifted.mean(axis=0)
            mean=x[0]+offset_mean;centered=shifted-offset_mean
            matrix=centered.T@centered/(n-1)
            if not np.isfinite(mean).all():raise CovarianceRefused('NONFINITE_MEAN')
            rank=int(np.linalg.matrix_rank(centered))
    except (FloatingPointError,np.linalg.LinAlgError) as exc:raise CovarianceRefused('NUMERICAL_SAMPLE_FAILURE') from exc
    _checked_matrix(matrix)
    return SampleCovariance(tuple(float(v) for v in mean),_rows(matrix),n,p,rank,tuple(labels))
