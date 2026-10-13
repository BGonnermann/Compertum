"""Pure synthetic annual fit/serve contract; not a campaign or approved release."""
from dataclasses import dataclass,asdict
import hashlib,json,re
from importlib.metadata import version
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from compertum.data.calendar import NY,session_times,utc_time
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.market import WATCHLIST
from .registry import FEATURES,VARIANTS,variant,annual_cutoff

MAX_ROWS=32768
ROW_FIELDS=set('symbol feature_session decision_at entry_at label_end_at simulated_feature_available_at simulated_label_available_at simulated_revision_available_at label_revision_id features target'.split())
BUNDLE_FIELDS={'schema','input_kind','availability_basis','feature_order','horizon','rows'}
MODEL_FIELDS={'schema','status','financial_accepted','candidate_id','horizon','feature_order','bundle_sha256','fit_manifest_sha256','fit_cutoff','observations','scaler','ridge','resolved','versions'}

@dataclass(frozen=True)
class FitRows:
    content:bytes
    sha256:str

@dataclass(frozen=True)
class FitManifest:
    content:bytes
    sha256:str

@dataclass(frozen=True)
class RidgeArtifact:
    content:bytes
    sha256:str


def _wrap(cls,value):
    raw=canonical(value)
    return cls(raw,hashlib.sha256(raw).hexdigest())


def _read(artifact,cls,maximum):
    if not isinstance(artifact,cls) or type(artifact.content) is not bytes or not 0<len(artifact.content)<=maximum:
        raise DataError('INPUT_BOUND')
    if type(artifact.sha256) is not str or hashlib.sha256(artifact.content).hexdigest()!=artifact.sha256:raise DataError('HASH_MISMATCH')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise DataError('DUPLICATE_KEY')
            result[k]=v
        return result
    try:return json.loads(artifact.content,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(DataError('NONFINITE_INPUT')))
    except (UnicodeError,ValueError,RecursionError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('INVALID_ARTIFACT') from exc


def _numbers(value,shape):
    try:
        masked=np.ma.asarray(value)
        if np.ma.getmaskarray(masked).any() or masked.dtype.kind not in 'fiu':raise DataError('INVALID_MODEL_NUMBER')
        with np.errstate(over='raise',invalid='raise'):a=np.asarray(masked,dtype=np.float64)
        if a.shape!=shape or not np.isfinite(a).all():raise DataError('INVALID_MODEL_NUMBER')
        return a
    except (TypeError,ValueError,OverflowError,FloatingPointError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('INVALID_MODEL_NUMBER') from exc


def _feature_order(names):
    if not isinstance(names,(list,tuple)) or tuple(names)!=FEATURES:raise DataError('FEATURE_ORDER_MISMATCH')


def _validate_row(row,horizon):
    if type(row) is not dict or set(row)!=ROW_FIELDS:raise DataError('INVALID_ROW_FIELDS')
    if type(row['symbol']) is not str or row['symbol'] not in WATCHLIST:raise DataError('INVALID_SYMBOL')
    decision=utc_time(row['decision_at']);day=decision.astimezone(NY).date().isoformat();t=session_times(day)
    if not '2016-01-01'<=day<'2024-01-01':raise DataError('DEVELOPMENT_ROWS_ONLY')
    if decision!=t.decision or utc_time(row['entry_at'])!=t.entry or row['feature_session']!=t.previous_date:raise DataError('INVALID_ROW_TIMING')
    end=day
    for _ in range(horizon):end=session_times(end).next_date
    if end>='2024-01-01':raise DataError('DEVELOPMENT_ROWS_ONLY')
    endtimes=session_times(end)
    if utc_time(row['label_end_at'])!=endtimes.entry:raise DataError('INVALID_ROW_TIMING')
    label=utc_time(row['simulated_label_available_at'])
    if label<session_times(endtimes.next_date).decision:raise DataError('EARLY_LABEL')
    utc_time(row['simulated_feature_available_at']);utc_time(row['simulated_revision_available_at'])
    revision=row['label_revision_id']
    if type(revision) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}',revision) is None:raise DataError('INVALID_REVISION_ID')
    result=dict(row);result['features']=_numbers(row['features'],(len(FEATURES),)).tolist();result['target']=float(_numbers(row['target'],()))
    return result


def freeze_rows(rows,*,horizon,feature_names):
    _feature_order(feature_names)
    if type(horizon) is not int or horizon not in (1,5,21):raise DataError('INVALID_HORIZON')
    if not isinstance(rows,(list,tuple)) or not 1<=len(rows)<=MAX_ROWS:raise DataError('INPUT_BOUND')
    normalized=[_validate_row(row,horizon) for row in rows];normalized.sort(key=lambda r:(r['decision_at'],r['symbol']))
    identities=[(r['symbol'],utc_time(r['decision_at'])) for r in normalized]
    if len(set(identities))!=len(identities):raise DataError('DUPLICATE_ROW')
    result=_wrap(FitRows,dict(schema='fit-rows-v1',input_kind='SYNTHETIC_ENGINEERING',availability_basis='SIMULATED_AVAILABILITY',feature_order=FEATURES,horizon=horizon,rows=normalized))
    if len(result.content)>32*1024**2:raise DataError('INPUT_BOUND')
    return result


def _bundle(bundle):
    value=_read(bundle,FitRows,32*1024**2)
    if type(value) is not dict or set(value)!=BUNDLE_FIELDS or value['schema']!='fit-rows-v1' or value['input_kind']!='SYNTHETIC_ENGINEERING' or value['availability_basis']!='SIMULATED_AVAILABILITY':raise DataError('INVALID_FIT_BUNDLE')
    rebuilt=freeze_rows(value['rows'],horizon=value['horizon'],feature_names=value['feature_order'])
    if rebuilt.content!=bundle.content:raise DataError('NONCANONICAL_FIT_BUNDLE')
    return value


def prepare_fit(bundle,year):
    cutoff=annual_cutoff(year);value=_bundle(bundle)
    included,excluded=_partition_rows(value['rows'],cutoff)
    return _wrap(FitManifest,dict(schema='engineering-fit-manifest-v1',status='SYNTHETIC_ENGINEERING',year=year,horizon=value['horizon'],cutoff=cutoff.isoformat(),feature_order=FEATURES,bundle_sha256=bundle.sha256,registry_sha256=hashlib.sha256(canonical([asdict(v) for v in VARIANTS])).hexdigest(),included=included,excluded=excluded))


def _partition_rows(rows,cutoff):
    """Pure date purge; caller validates provenance and allowed date domain."""
    evaluation=session_times(cutoff.astimezone(NY).date().isoformat()).entry
    groups={};reasons={}
    for index,row in enumerate(rows):
        date=utc_time(row['decision_at']).astimezone(NY).date().isoformat();groups.setdefault(date,[]).append(index)
        why=[]
        if utc_time(row['decision_at'])>=cutoff:why.append('NOT_BEFORE_SCORING')
        if utc_time(row['simulated_feature_available_at'])>utc_time(row['decision_at']):why.append('FEATURE_AFTER_DECISION')
        if utc_time(row['label_end_at'])>=evaluation:why.append('EVALUATION_OVERLAP')
        for field in ['simulated_feature_available_at','simulated_label_available_at','simulated_revision_available_at']:
            if utc_time(row[field])>cutoff:why.append(field.upper()+'_AFTER_CUTOFF')
        reasons.setdefault(date,set()).update(why)
    included=[];excluded=[]
    for day,indices in sorted(groups.items()):
        for index in indices:
            row=rows[index]
            identity={'index':index,'symbol':row['symbol'],'decision_at':row['decision_at'],'row_sha256':hashlib.sha256(canonical(row)).hexdigest(),'label_revision_id':row['label_revision_id'],'revision_available_at':row['simulated_revision_available_at']}
            if reasons[day]:excluded.append(dict(identity,reasons=sorted(reasons[day]|{'SAME_DATE_PURGE'})))
            else:included.append(identity)
    return included,excluded


def _estimators(alpha):
    return StandardScaler(copy=True,with_mean=True,with_std=True),Ridge(alpha=alpha,fit_intercept=True,copy_X=True,max_iter=None,tol=1e-4,solver='svd',positive=False,random_state=None)


def fit_ridge(bundle,manifest,candidate_id):
    candidate=variant(candidate_id);value=_bundle(bundle);m=_read(manifest,FitManifest,16*1024**2)
    if type(m) is not dict or type(m.get('year')) is not int:raise DataError('INVALID_FIT_MANIFEST')
    if prepare_fit(bundle,m['year']).content!=manifest.content:raise DataError('FIT_MANIFEST_MISMATCH')
    if candidate.kind!='ridge' or candidate.horizon!=value['horizon']:raise DataError('VARIANT_MISMATCH')
    selected=[value['rows'][r['index']] for r in m['included']]
    if len(selected)<2:raise DataError('INSUFFICIENT_FIT_ROWS')
    x=_numbers([r['features'] for r in selected],(len(selected),len(FEATURES)));y=_numbers([r['target'] for r in selected],(len(selected),))
    scaler,model=_estimators(candidate.alpha)
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            z=scaler.fit_transform(x);model.fit(z,y)
            arrays=[scaler.mean_,scaler.scale_,model.coef_,[model.intercept_]]
            if not all(np.isfinite(a).all() for a in arrays):raise DataError('NONFINITE_FIT')
    except (ValueError,FloatingPointError,np.linalg.LinAlgError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('NUMERICAL_FIT_FAILURE') from exc
    artifact=_wrap(RidgeArtifact,dict(schema='ridge-engineering-v1',status='SYNTHETIC_ENGINEERING',financial_accepted=False,candidate_id=candidate_id,horizon=candidate.horizon,feature_order=FEATURES,bundle_sha256=bundle.sha256,fit_manifest_sha256=manifest.sha256,fit_cutoff=m['cutoff'],observations=len(selected),scaler={'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist()},ridge={'coef':model.coef_.tolist(),'intercept':float(model.intercept_)},resolved={'scaler':scaler.get_params(),'ridge':model.get_params(),'row_weights':'EQUAL','dtype':'float64'},versions={name:version(name) for name in ['numpy','scipy','scikit-learn']}))
    # The persisted serving path must match this exact fitted pipeline.
    if not np.allclose(predict(artifact,x,feature_names=FEATURES),model.predict(z),rtol=1e-12,atol=1e-12):raise DataError('FIT_SERVE_PARITY')
    return artifact


def predict(artifact,features,*,feature_names):
    _feature_order(feature_names);value=_read(artifact,RidgeArtifact,1024**2)
    if type(value) is not dict or set(value)!=MODEL_FIELDS or value['schema']!='ridge-engineering-v1' or value['status']!='SYNTHETIC_ENGINEERING' or value['financial_accepted'] is not False:raise DataError('INVALID_MODEL_ARTIFACT')
    _feature_order(value['feature_order']);candidate=variant(value['candidate_id'])
    if candidate.kind!='ridge' or type(value['horizon']) is not int or value['horizon']!=candidate.horizon:raise DataError('VARIANT_MISMATCH')
    scaler,model=_estimators(candidate.alpha)
    if value['resolved']!={'scaler':scaler.get_params(),'ridge':model.get_params(),'row_weights':'EQUAL','dtype':'float64'}:raise DataError('MODEL_CONFIGURATION_MISMATCH')
    if value['versions']!={name:version(name) for name in ['numpy','scipy','scikit-learn']}:raise DataError('MODEL_ENVIRONMENT_MISMATCH')
    if type(value['observations']) is not int or not 2<=value['observations']<=MAX_ROWS:raise DataError('INVALID_MODEL_ARTIFACT')
    for field in ['bundle_sha256','fit_manifest_sha256']:
        if type(value[field]) is not str or re.fullmatch('[0-9a-f]{64}',value[field]) is None:raise DataError('INVALID_MODEL_ARTIFACT')
    cutoff=utc_time(value['fit_cutoff'])
    if cutoff!=annual_cutoff(cutoff.year):raise DataError('INVALID_MODEL_ARTIFACT')
    if type(value['scaler']) is not dict or set(value['scaler'])!={'mean','scale'} or type(value['ridge']) is not dict or set(value['ridge'])!={'coef','intercept'}:raise DataError('INVALID_MODEL_ARTIFACT')
    mean=_numbers(value['scaler']['mean'],(len(FEATURES),));scale=_numbers(value['scaler']['scale'],(len(FEATURES),));coef=_numbers(value['ridge']['coef'],(len(FEATURES),));intercept=float(_numbers(value['ridge']['intercept'],()))
    if np.any(scale<=0):raise DataError('INVALID_MODEL_SCALE')
    try:n=len(features)
    except TypeError:raise DataError('INPUT_BOUND') from None
    if not 1<=n<=MAX_ROWS:raise DataError('INPUT_BOUND')
    x=_numbers(features,(n,len(FEATURES)))
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):result=((x-mean)/scale)@coef+intercept
        if not np.isfinite(result).all():raise DataError('NONFINITE_PREDICTION')
    except FloatingPointError as exc:raise DataError('NUMERICAL_PREDICTION_FAILURE') from exc
    return tuple(float(v) for v in result)
