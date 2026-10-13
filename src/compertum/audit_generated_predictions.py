"""Independent fixed-recipe fit and prediction reconstruction; no producer calls."""
from decimal import Decimal as D
import math
from compertum.data.calendar import session_times,utc_time
from compertum.data.errors import DataError
from compertum.simulation.market import WATCHLIST
from compertum.modeling.registry import FEATURES
from compertum.audit_predictions import (_check,_hash,_exact,_compare,_near,_advance,_numeric,
    _fit_equations,_numeric_report,reconstruct_errors,_ranks_by_day,_ml_gate)


def training(source,c,metadata,year,value,runtime):
    annual=metadata['annual'][str(year)];cutoff=utc_time(annual['cutoff'])
    dates=[d for d in metadata['sessions'] if annual['training_start']<=d<=annual['training_end']]
    rows=[];omissions=[];provenance=[]
    for day in dates:
        t=session_times(day);end=_advance(day,c.horizon);pending=[];bad=[]
        for symbol in WATCHLIST:
            identity=dict(symbol=symbol,decision_at=t.decision.isoformat())
            if symbol not in source.market.symbols:
                omissions.append(dict(identity,reasons=['MISSING_SYMBOL']));continue
            try:
                features=source.features(symbol,day)
                if not features['raw_eligible']:raise DataError('INELIGIBLE_RAW_PRICE_OR_VOLUME')
                label=source.label(symbol,day,end,c.horizon)
            except DataError as error:
                bad.append(error.code);omissions.append(dict(identity,reasons=[error.code,'SAME_DATE_LABEL_PURGE']));continue
            available=label['available'].isoformat();revision='label-'+label['sha256']
            row=dict(identity,feature_session=features['feature_session'],entry_at=t.entry.isoformat(),label_end_at=session_times(end).entry.isoformat(),simulated_feature_available_at=features['available'].isoformat(),simulated_label_available_at=available,simulated_revision_available_at=available,label_revision_id=revision,features=features['values'],target=float(label['target']))
            evidence=dict(identity,feature_sha256=features['input_sha256'],label_sha256=label['sha256'],entry_revision_id=label['entry_revision'],exit_revision_id=label['exit_revision'],split_action_ids=label['split_actions'],selected_label_revision_id=revision,label_available_at=available)
            pending.append((row,evidence))
        if bad:
            omissions.extend(dict(symbol=r['symbol'],decision_at=r['decision_at'],reasons=sorted(set(bad)|{'SAME_DATE_LABEL_PURGE'})) for r,_ in pending)
        else:
            rows.extend(r for r,_ in pending);provenance.extend(p for _,p in pending)
    order=lambda r:(r['decision_at'],r['symbol'])
    rows.sort(key=order);omissions.sort(key=order);provenance.sort(key=order)
    _check(0<len(rows)<=32768 and len(rows)+len(omissions)==12*len(dates))
    _check(set(value)==set('candidate_id year horizon training_start training_end training_sessions rows omissions provenance manifest model model_sha256'.split()))
    for key,expected in dict(candidate_id=c.candidate_id,year=year,horizon=c.horizon,training_start=annual['training_start'],training_end=annual['training_end'],training_sessions=len(dates),omissions=omissions,provenance=provenance).items():_exact(value[key],expected)
    _compare(value['rows'],rows)
    # Hash recorded bytes after independent source comparison, including exact timing.
    actual=value['rows'];row_hash=_hash(actual);reasons={};evaluation=session_times(cutoff.date().isoformat()).entry
    for row in actual:
        why=reasons.setdefault(row['decision_at'],set())
        if utc_time(row['decision_at'])>=cutoff:why.add('NOT_BEFORE_SCORING')
        if utc_time(row['simulated_feature_available_at'])>utc_time(row['decision_at']):why.add('FEATURE_AFTER_DECISION')
        if utc_time(row['label_end_at'])>=evaluation:why.add('EVALUATION_OVERLAP')
        for field in ('simulated_feature_available_at','simulated_label_available_at','simulated_revision_available_at'):
            if utc_time(row[field])>cutoff:why.add(field.upper()+'_AFTER_CUTOFF')
    included=[];excluded=[];selected=[]
    for index,row in enumerate(actual):
        reference=dict(index=index,symbol=row['symbol'],decision_at=row['decision_at'],row_sha256=_hash(row),label_revision_id=row['label_revision_id'],revision_available_at=row['simulated_revision_available_at'])
        why=reasons[row['decision_at']]
        if why:excluded.append(dict(reference,reasons=sorted(why|{'SAME_DATE_PURGE'})))
        else:included.append(reference);selected.append(rows[index])
    manifest=dict(schema='generated-fit-manifest-v1',year=year,horizon=c.horizon,cutoff=cutoff.isoformat(),feature_order=FEATURES,rows_sha256=row_hash,included=included,excluded=excluded)
    _exact(value['manifest'],manifest)
    solved=_fit_equations([r['features'] for r in selected],[r['target'] for r in selected],c.alpha)
    versions=dict(runtime['distributions'])
    expected=dict(schema='generated-ridge-v1',candidate_id=c.candidate_id,horizon=c.horizon,recipe_sha256=metadata['recipe_sha256'],market_sha256=source.market.sha256,financial_accepted=False,feature_order=FEATURES,rows_sha256=row_hash,manifest_sha256=_hash(manifest),fit_cutoff=cutoff.isoformat(),observations=len(selected),scaler=dict(mean=solved['mean'],scale=solved['scale']),ridge=dict(coef=solved['coef'],intercept=solved['intercept']),resolved={'scaler':{'copy':True,'with_mean':True,'with_std':True},'ridge':{'alpha':c.alpha,'fit_intercept':True,'copy_X':True,'max_iter':None,'tol':1e-4,'solver':'svd','positive':False,'random_state':None},'row_weights':'EQUAL','dtype':'float64'},versions={name:versions[name] for name in ('numpy','scipy','scikit-learn')})
    _exact(value['model_sha256'],_hash(value['model']))
    _exact(value['model']['resolved'],expected['resolved'])
    _compare(value['model'],expected)
    _check(all(_numeric(x)>0 for x in value['model']['scaler']['scale']))
    return dict(assembled_rows=len(rows),included_rows=len(selected),excluded_rows=len(excluded),omitted_rows=len(omissions),cutoff=cutoff.isoformat(),model_sha256=value['model_sha256'],independent_equations_sha256=_hash(solved)),solved,expected


def predictions(source,c,dates,asof,report,solved,recorded_model):
    rows=[];omissions=[];feature_count=eligible=0
    for index,day in enumerate(dates):
        t=session_times(day)
        for symbol in WATCHLIST:
            try:
                if symbol not in source.market.symbols:raise DataError('MISSING_SYMBOL')
                if t.decision>asof:raise DataError('DECISION_UNAVAILABLE')
                momentum=source.baseline(symbol,day,c.horizon);features=None
                if c.kind=='ridge':
                    features=source.features(symbol,day)
                    if not features['raw_eligible']:raise DataError('INELIGIBLE_RAW_PRICE_OR_VOLUME')
                feature_count+=1
                if index+c.horizon>=len(dates):raise DataError('HORIZON_BOUNDARY')
                eligible+=1;end=dates[index+c.horizon];label=source.label(symbol,day,end,c.horizon)
                if label['available']>asof:raise DataError('LABEL_UNAVAILABLE')
            except DataError as error:
                omissions.append(dict(session=day,symbol=symbol,reason=error.code));continue
            prediction=momentum
            if features:prediction=D(str(math.fsum((x-mean)/scale*coef for x,mean,scale,coef in zip(features['values'],solved['mean'],solved['scale'],solved['coef']))+solved['intercept']))
            target=label['target']
            rows.append(dict(session=day,symbol=symbol,decision_at=t.decision.isoformat(),entry_at=t.entry.isoformat(),exit_at=session_times(end).entry.isoformat(),label_available_at=label['available'].isoformat(),entry_revision=label['entry_revision'],exit_revision=label['exit_revision'],split_actions=label['split_actions'],prediction=prediction,momentum_prediction=momentum,target=target,signed_error=prediction-target,features=features['values'] if features else None,feature_sha256=features['input_sha256'] if features else None))
    _check(set(report)==set('coverage scoring_as_of metrics momentum_metrics ml_contribution_gate daily_rank_correlation rows omissions'.split()))
    coverage=dict(candidate_rows=len(dates)*12,feature_eligible_rows=feature_count,eligible_rows=eligible,scored_rows=len(rows),omitted_rows=len(omissions))
    _exact(report['coverage'],coverage);_exact(report['scoring_as_of'],asof.isoformat());_exact(report['omissions'],omissions);_compare(report['rows'],rows)
    for row in report['rows']:
        _near(row['signed_error'],_numeric(row['prediction'])-_numeric(row['target']))
        if c.kind=='momentum':_check(_numeric(row['prediction'])==_numeric(row['momentum_prediction']))
        else:
            m=recorded_model
            served=math.fsum((x-mean)/scale*coef for x,mean,scale,coef in zip(row['features'],m['scaler']['mean'],m['scaler']['scale'],m['ridge']['coef']))+m['ridge']['intercept']
            _near(row['prediction'],served)
    for checked in (rows,report['rows']):
        errors=reconstruct_errors([r['prediction'] for r in checked],[r['target'] for r in checked])
        _numeric_report(report['metrics'],errors)
        _numeric_report(report['momentum_metrics'],reconstruct_errors([r['momentum_prediction'] for r in checked],[r['target'] for r in checked]))
        _compare(report['daily_rank_correlation'],_ranks_by_day(checked,dates))
        _exact(report['ml_contribution_gate'],_ml_gate(c,errors))
    return rows,dict(coverage=coverage,prediction_metrics=report['metrics'],momentum_metrics=report['momentum_metrics'],ml_contribution_gate=report['ml_contribution_gate'])
