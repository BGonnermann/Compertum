"""Closed generated annual fits; no external rows or financial admission."""
from dataclasses import dataclass
import hashlib,json
from importlib.metadata import version
import numpy as np
from compertum.data.calendar import session_times,utc_time
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.market import WATCHLIST
from compertum.simulation.policy import fixed_decimal
from compertum.simulation.prediction import _label
from .generated_market import generate_market
from .features import feature_vector
from .registry import FEATURES,variant
from .ridge import _partition_rows,_estimators,_numbers


@dataclass(frozen=True)
class GeneratedFits:
    content:bytes
    sha256:str


from compertum.final_plan import selection as _selection


class _Vectors:
    def __init__(self,market):self.market=market;self.cache={}
    def get(self,symbol,day):
        key=(symbol,day)
        if key not in self.cache:self.cache[key]=feature_vector(self.market,symbol,day)
        return self.cache[key]


def _rows(market,metadata,year,horizon,vectors):
    fold=metadata['annual'][str(year)]
    dates=[d for d in metadata['sessions'] if fold['training_start']<=d<=fold['training_end']]
    rows=[];omissions=[];provenance=[]
    for day in dates:
        t=session_times(day);end=day
        for _ in range(horizon):end=session_times(end).next_date
        pending=[];bad=[]
        for symbol in WATCHLIST:
            identity=dict(symbol=symbol,decision_at=t.decision.isoformat())
            if symbol not in market.symbols:
                omissions.append(dict(identity,reasons=['MISSING_SYMBOL']));continue
            try:
                f=vectors.get(symbol,day)
                if not f.raw_eligible:raise DataError('INELIGIBLE_RAW_PRICE_OR_VOLUME')
                label,reason=_label(market,symbol,day,end)
                if reason:raise DataError(reason)
            except DataError as exc:
                bad.append(exc.code);omissions.append(dict(identity,reasons=[exc.code,'SAME_DATE_LABEL_PURGE']));continue
            entry=market.rows[(symbol,day,'entry')];exit_row=market.rows[(symbol,end,'entry')]
            digest=hashlib.sha256(canonical(dict(entry=entry,exit=exit_row,splits=[],horizon=horizon))).hexdigest()
            revision='label-'+digest;available=label['available'].isoformat()
            row=dict(identity,feature_session=f.feature_session,entry_at=t.entry.isoformat(),
                label_end_at=session_times(end).entry.isoformat(),simulated_feature_available_at=f.available_at,
                simulated_label_available_at=available,simulated_revision_available_at=available,
                label_revision_id=revision,features=f.values,target=float(label['target']))
            source=dict(identity,feature_sha256=f.input_sha256,label_sha256=digest,
                entry_revision_id=label['entry_revision'],exit_revision_id=label['exit_revision'],
                split_action_ids=[],selected_label_revision_id=revision,label_available_at=available)
            pending.append((row,source))
        if bad:
            for row,_ in pending:omissions.append(dict(symbol=row['symbol'],decision_at=row['decision_at'],reasons=sorted(set(bad)|{'SAME_DATE_LABEL_PURGE'})))
        else:
            rows.extend(row for row,_ in pending);provenance.extend(source for _,source in pending)
    rows.sort(key=lambda r:(r['decision_at'],r['symbol']))
    provenance.sort(key=lambda r:(r['decision_at'],r['symbol']))
    omissions.sort(key=lambda r:(r['decision_at'],r['symbol']))
    if len(rows)+len(omissions)!=12*len(dates):raise DataError('COVERAGE_ACCOUNTING')
    return rows,omissions,provenance,len(dates)


def _fit(market,metadata,year,candidate,vectors):
    fold=metadata['annual'][str(year)];cutoff=utc_time(fold['cutoff'])
    rows,omissions,provenance,count=_rows(market,metadata,year,candidate.horizon,vectors)
    included,excluded=_partition_rows(rows,cutoff)
    bundle_sha=hashlib.sha256(canonical(rows)).hexdigest()
    manifest=dict(schema='generated-fit-manifest-v1',year=year,horizon=candidate.horizon,
        cutoff=cutoff.isoformat(),feature_order=FEATURES,rows_sha256=bundle_sha,included=included,excluded=excluded)
    selected=[rows[r['index']] for r in included]
    if len(selected)<2:raise DataError('INSUFFICIENT_FIT_ROWS')
    x=_numbers([r['features'] for r in selected],(len(selected),len(FEATURES)))
    y=_numbers([r['target'] for r in selected],(len(selected),))
    scaler,model=_estimators(candidate.alpha)
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            z=scaler.fit_transform(x);model.fit(z,y)
            if not all(np.isfinite(a).all() for a in (scaler.mean_,scaler.scale_,model.coef_,[model.intercept_])):raise DataError('NONFINITE_FIT')
    except (ValueError,FloatingPointError,np.linalg.LinAlgError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('NUMERICAL_FIT_FAILURE') from exc
    fitted=dict(schema='generated-ridge-v1',candidate_id=candidate.candidate_id,horizon=candidate.horizon,
        recipe_sha256=metadata['recipe_sha256'],market_sha256=market.sha256,financial_accepted=False,
        feature_order=FEATURES,rows_sha256=bundle_sha,manifest_sha256=hashlib.sha256(canonical(manifest)).hexdigest(),
        fit_cutoff=cutoff.isoformat(),observations=len(selected),
        scaler=dict(mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist()),
        ridge=dict(coef=model.coef_.tolist(),intercept=float(model.intercept_)),
        resolved=dict(scaler=scaler.get_params(),ridge=model.get_params(),row_weights='EQUAL',dtype='float64'),
        versions={name:version(name) for name in ('numpy','scipy','scikit-learn')})
    result=dict(candidate_id=candidate.candidate_id,year=year,horizon=candidate.horizon,
        training_start=fold['training_start'],training_end=fold['training_end'],training_sessions=count,
        rows=rows,omissions=omissions,provenance=provenance,manifest=manifest,model=fitted,
        model_sha256=hashlib.sha256(canonical(fitted)).hexdigest())
    return result


@fixed_decimal
def prepare_generated_fits(raw,*,expected_sha256,candidate_ids):
    """Pure engineering report; shortlist and owner admission remain separate."""
    candidates=_selection(candidate_ids)
    market,metadata=generate_market(raw,expected_sha256=expected_sha256);vectors=_Vectors(market)
    fits=[_fit(market,metadata,year,c,vectors) for year in (2024,2025) for c in candidates if c.kind=='ridge']
    value=dict(schema='generated-final-fits-v1',recipe_sha256=expected_sha256,market=metadata,
        selected=[c.candidate_id for c in candidates],fits=fits,financial_accepted=False,full_M3=False)
    content=canonical(value)
    if len(content)>16*1024**2:raise DataError('OUTPUT_BOUND')
    return GeneratedFits(content,hashlib.sha256(content).hexdigest())
