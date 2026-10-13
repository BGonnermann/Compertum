"""Independent original-source reconstruction of synthetic prediction evidence.

No call to the producer's feature, label, fitting, serving or score functions.
This evidence has no owner authority and cannot select or approve a strategy.
"""
from dataclasses import dataclass,asdict
from datetime import datetime,time,timezone
from decimal import Decimal as D,DecimalException
from importlib.metadata import version
import hashlib,json,math
import numpy as np
from .audit import _precision,ABS,REL,_number
from .data.encoding import canonical
from .data.errors import DataError
from .data.calendar import session_times,utc_time,NY
from .simulation.market import load_market,WATCHLIST
from .modeling.registry import FEATURES,VARIANTS,variant

MAX_BYTES=16*1024**2

@dataclass(frozen=True)
class PredictionAudit:
    content:bytes
    sha256:str


def _check(ok,code='AUDIT_PREDICTION_MISMATCH'):
    if not ok:raise DataError(code)


def _hash(value):return hashlib.sha256(canonical(value)).hexdigest()


def _numeric(value):
    _check(type(value) in (float,int,str,D),'AUDIT_INPUT_INVALID')
    result=D(str(value));_check(result.is_finite() and abs(result)<=D('1e32'),'AUDIT_INPUT_INVALID')
    return result


def _near(actual,expected):
    a=_numeric(actual);b=_numeric(expected);_check(abs(a-b)<=ABS+REL*abs(b))


def _exact(actual,expected):_check(canonical(actual)==canonical(expected))


def _compare(actual,expected):
    if type(expected) is dict:
        _check(type(actual) is dict and set(actual)==set(expected))
        for key in expected:_compare(actual[key],expected[key])
    elif type(expected) in (list,tuple):
        _check(type(actual) in (list,tuple) and len(actual)==len(expected))
        for a,b in zip(actual,expected):_compare(a,b)
    elif type(expected) is float:
        _check(type(actual) in (float,int));_near(actual,expected)
    elif type(expected) is D:
        _check(type(actual) is str);_near(actual,expected)
    else:_exact(actual,expected)


def _dates(start,end):
    _check(type(start) is str and type(end) is str and '2016-01-01'<=start<=end<'2024-01-01','AUDIT_INPUT_INVALID')
    session_times(start);session_times(end);dates=[start]
    while dates[-1]!=end:
        _check(len(dates)<1024,'AUDIT_INPUT_BOUND');dates.append(session_times(dates[-1]).next_date)
    return dates


def _advance(day,h):
    for _ in range(h):day=session_times(day).next_date
    return day


def _cutoff(year):
    _check(type(year) is int and year in (2021,2022,2023),'AUDIT_INPUT_INVALID')
    # Walk the original exchange calendar independently of the fit implementation.
    day=f'{year-1}-12-15'
    while session_times(day).next_date[:4]!=str(year):day=session_times(day).next_date
    first=session_times(day).next_date
    return datetime.combine(datetime.fromisoformat(first).date(),time(7),NY).astimezone(timezone.utc)


class SourceEvidence:
    """Bounded, task-local cache over already validated original raw rows."""
    def __init__(self,market):self.market=market;self._rows={};self._features={}

    def history(self,symbol,day):
        key=(symbol,day)
        if key not in self._rows:
            rows=[];date=session_times(day).previous_date
            for _ in range(252):
                row=self.market.rows.get((symbol,date,'daily'))
                if row is None:raise DataError('FEATURE_COVERAGE')
                if any(utc_time(row[f])>session_times(day).decision for f in ('simulated_available_at','simulated_revision_available_at')):raise DataError('FEATURE_UNAVAILABLE')
                rows.append(row);date=session_times(date).previous_date
            self._rows[key]=rows
        return self._rows[key]

    def _adjusted(self,symbol,day):
        rows=self.history(symbol,day);actions=[a for a in self.market.actions if a['symbol']==symbol and a['kind']=='SPLIT' and rows[-1]['session_date']<a['effective_session']<=rows[0]['session_date']]
        if any(utc_time(a['simulated_known_at'])>session_times(day).decision for a in actions):raise DataError('ACTION_UNAVAILABLE')
        prices=[];volumes=[]
        for r in rows:
            factor=math.prod((D(a['factor']) for a in actions if r['session_date']<a['effective_session']),start=D(1))
            prices.append(float(D(r['close'])/factor));volumes.append(float(D(r['volume'])*factor))
        if any(not math.isfinite(x) for x in prices+volumes):raise DataError('NONFINITE_FEATURE')
        available=max([utc_time(r[f]) for r in rows for f in ('simulated_available_at','simulated_revision_available_at')]+[utc_time(a['simulated_known_at']) for a in actions])
        return prices,volumes,rows,actions,available

    def features(self,symbol,day):
        key=(symbol,day)
        if key in self._features:return self._features[key]
        if symbol not in WATCHLIST or symbol not in self.market.symbols:raise DataError('INVALID_FEATURE_MARKET')
        asset=self._adjusted(symbol,day);spy=self._adjusted('SPY',day)
        p,v,rows,actions,available=asset;sp,sv,srows,sactions,savailable=spy
        means=[math.fsum(p[:h])/h for h in (20,63)]+[math.fsum(v[:20])/20]
        if any(x<=0 for x in p+sp+means):raise DataError('NONPOSITIVE_DENOMINATOR')
        def statistics(prices):
            values=[prices[0]/prices[h]-1 for h in (1,5,21,63)]
            returns=[prices[i]/prices[i+1]-1 for i in range(63)]
            for n in (20,63):
                mean=math.fsum(returns[:n])/n
                values.append(math.sqrt(252*math.fsum((x-mean)**2 for x in returns[:n])/(n-1)))
            return values
        values=statistics(p)+[p[0]/means[0]-1,p[0]/means[1]-1,v[0]/means[2]]+statistics(sp)
        if any(not math.isfinite(x) for x in values):raise DataError('NONFINITE_FEATURE')
        volume=sum(D(r['close'])*D(r['volume']) for r in rows[:20])/20
        digest=_hash({'schema':'fixed-features-v1','symbol':symbol,'decision_at':session_times(day).decision.isoformat(),'feature_order':FEATURES,'asset_rows':rows,'spy_rows':srows,'asset_splits':actions,'spy_splits':sactions})
        result={'values':values,'feature_session':session_times(day).previous_date,'available':max(available,savailable),'input_sha256':digest,'raw_eligible':D(rows[0]['close'])>=5 and volume>=1000000}
        self._features[key]=result;return result

    def baseline(self,symbol,day,h):
        rows=self.history(symbol,day)
        if any(a['symbol']==symbol and a['effective_session']<=day and utc_time(a['simulated_known_at'])>session_times(day).decision for a in self.market.actions):raise DataError('ACTION_UNAVAILABLE')
        price=D(rows[0]['close']);volume=sum(D(r['close'])*D(r['volume']) for r in rows[:20])/20
        if price<5 or volume<1000000:raise DataError('INELIGIBLE_PRICE_OR_VOLUME')
        factor=math.prod((D(a['factor']) for a in self.market.actions if a['symbol']==symbol and a['kind']=='SPLIT' and rows[21]['session_date']<a['effective_session']<=rows[0]['session_date']),start=D(1))
        return D(h)*(price*factor/D(rows[21]['close'])-1)/21

    def label(self,symbol,day,exit_day,h):
        entry=self.market.rows.get((symbol,day,'entry'));exit=self.market.rows.get((symbol,exit_day,'entry'))
        if entry is None or exit is None:raise DataError('LABEL_REFERENCE_MISSING')
        splits=[a for a in self.market.actions if a['symbol']==symbol and a['kind']=='SPLIT' and day<a['effective_session']<=exit_day]
        factor=math.prod((D(a['factor']) for a in splits),start=D(1))
        available=max([session_times(session_times(exit_day).next_date).decision]+[utc_time(r[f]) for r in (entry,exit) for f in ('simulated_available_at','simulated_revision_available_at')]+[utc_time(a['simulated_known_at']) for a in splits])
        digest=_hash({'entry':entry,'exit':exit,'splits':splits,'horizon':h})
        return {'target':D(exit['open'])*factor/D(entry['open'])-1,'available':available,'entry_revision':entry['revision_id'],'exit_revision':exit['revision_id'],'split_actions':[a['action_id'] for a in splits],'sha256':digest}


@_precision
def reconstruct_errors(predictions,targets):
    _check(type(predictions) in (list,tuple) and type(targets) in (list,tuple) and len(predictions)==len(targets)<=12288,'AUDIT_INPUT_INVALID')
    p=list(map(_numeric,predictions));t=list(map(_numeric,targets));n=len(p)
    if not n:return dict(observations=0,mse=None,mae=None,mean_signed_error=None,zero_mse=None,zero_mae=None,zero_mean_signed_error=None,mse_improvement=None,status='NO_SCORED_ROWS')
    error=[a-b for a,b in zip(p,t)];squares=sum(x*x for x in error)/n;zero=sum(x*x for x in t)/n
    return dict(observations=n,mse=_number(squares),mae=_number(sum(abs(x) for x in error)/n),mean_signed_error=_number(sum(error)/n),zero_mse=_number(zero),zero_mae=_number(sum(abs(x) for x in t)/n),zero_mean_signed_error=_number(-sum(t)/n),mse_improvement=_number(1-squares/zero) if zero else None,status='DEFINED' if zero else 'ZERO_BASELINE_MSE')


@_precision
def reconstruct_rank(predictions,targets):
    _check(type(predictions) in (list,tuple) and type(targets) in (list,tuple) and len(predictions)==len(targets)<=12,'AUDIT_INPUT_INVALID')
    p=list(map(_numeric,predictions));t=list(map(_numeric,targets));n=len(p)
    if n<2:return None
    def centered(values):
        return [D(sum(x<v for x in values))+D(sum(x==v for x in values)+1)/2-D(n+1)/2 for v in values]
    a=centered(p);b=centered(t);den=(sum(x*x for x in a)*sum(x*x for x in b)).sqrt()
    return _number(sum(x*y for x,y in zip(a,b))/den) if den else None


def _numeric_report(actual,expected):
    _check(type(actual) is dict and set(actual)==set(expected))
    for k,v in expected.items():
        if type(v) is str and k not in ('status',):
            _check(type(actual[k]) is str);_near(actual[k],v)
        else:_exact(actual[k],v)


def _fit_equations(features,targets,alpha):
    _check(type(features) in (list,tuple) and 2<=len(features)<=32768 and len(targets)==len(features),'AUDIT_INPUT_BOUND')
    _check(type(alpha) is int and alpha in (1,10,100),'AUDIT_INPUT_INVALID')
    width=len(features[0]);_check(1<=width<=15 and all(len(row)==width for row in features))
    x=np.array([[float(_numeric(v)) for v in row] for row in features],dtype=np.float64);y=np.array([float(_numeric(v)) for v in targets],dtype=np.float64)
    n=len(x);means=np.array([math.fsum(x[:,j])/n for j in range(width)]);variances=np.array([math.fsum((x[:,j]-means[j])**2)/n for j in range(width)])
    eps=np.finfo(np.float64).eps;constant=variances<=n*eps*variances+(n*means*eps)**2
    scales=np.sqrt(variances);scales[constant]=1
    z=(x-means)/scales;zm=np.array([math.fsum(z[:,j])/n for j in range(width)]);ym=math.fsum(y)/n
    centered=z-zm;coef=np.linalg.solve(centered.T@centered+alpha*np.eye(width),centered.T@(y-ym));intercept=ym-float(zm@coef)
    _check(all(np.isfinite(a).all() for a in (means,scales,coef,np.array([intercept]))),'AUDIT_NUMERICAL_FAILURE')
    return {'mean':means.tolist(),'scale':scales.tolist(),'coef':coef.tolist(),'intercept':intercept}


def _training(source,c,year,start,end,value):
    rows=[];provenance=[];omissions=[];dates=_dates(start,end)
    for day in dates:
        t=session_times(day);exit=_advance(day,c.horizon);pending=[];bad=[];omitted=[]
        for symbol in WATCHLIST:
            identity={'symbol':symbol,'decision_at':t.decision.isoformat()}
            if symbol not in source.market.symbols:omitted.append(dict(identity,reasons=['MISSING_SYMBOL']));continue
            try:
                features=source.features(symbol,day)
                if not features['raw_eligible']:raise DataError('INELIGIBLE_RAW_PRICE_OR_VOLUME')
            except DataError as exc:omitted.append(dict(identity,reasons=[exc.code]));continue
            try:
                if exit>='2024-01-01':raise DataError('LABEL_OUTSIDE_DEVELOPMENT')
                label=source.label(symbol,day,exit,c.horizon)
            except DataError as exc:bad.append(exc.code);omitted.append(dict(identity,reasons=[exc.code,'SAME_DATE_LABEL_PURGE']));continue
            available=label['available'].isoformat();revision='label-'+label['sha256']
            row=dict(identity,feature_session=features['feature_session'],entry_at=t.entry.isoformat(),label_end_at=session_times(exit).entry.isoformat(),simulated_feature_available_at=features['available'].isoformat(),simulated_label_available_at=available,simulated_revision_available_at=available,label_revision_id=revision,features=features['values'],target=float(label['target']))
            p=dict(identity,feature_sha256=features['input_sha256'],label_sha256=label['sha256'],entry_revision_id=label['entry_revision'],exit_revision_id=label['exit_revision'],split_action_ids=label['split_actions'],selected_label_revision_id=revision,label_available_at=available)
            pending.append((row,p))
        if bad:
            for row,_ in pending:omitted.append({'symbol':row['symbol'],'decision_at':row['decision_at'],'reasons':sorted(set(bad)|{'SAME_DATE_LABEL_PURGE'})})
        else:rows.extend(r for r,_ in pending);provenance.extend(p for _,p in pending)
        omissions.extend(omitted)
    order=lambda r:(r['decision_at'],r['symbol'])
    rows.sort(key=order);provenance.sort(key=order);omissions.sort(key=order)
    _check(0<len(rows)<=32768)
    bundle=value['fit_rows'];expected={'schema':'fit-rows-v1','input_kind':'SYNTHETIC_ENGINEERING','availability_basis':'SIMULATED_AVAILABILITY','feature_order':FEATURES,'horizon':c.horizon,'rows':rows}
    _compare(bundle,expected);digest=_hash(bundle)
    _exact(value['dataset_assembly'],dict(schema='synthetic-dataset-assembly-v1',status='SYNTHETIC_ENGINEERING',financial_accepted=False,full_M2=False,horizon=c.horizon,start=start,end=end,source_market_sha256=source.market.sha256,feature_order=FEATURES,frozen_universe=WATCHLIST,present_universe=[s for s in source.market.symbols if s!='SPY'],expected_rows=len(dates)*12,assembled_rows=len(rows),omissions=omissions,row_provenance=provenance,fit_rows_sha256=digest,availability_basis='SIMULATED_AVAILABILITY'))
    cutoff=_cutoff(year);evaluation=session_times(cutoff.date().isoformat()).entry;reasons={}
    for row in bundle['rows']:
        why=reasons.setdefault(row['decision_at'],set())
        if utc_time(row['decision_at'])>=cutoff:why.add('NOT_BEFORE_SCORING')
        if utc_time(row['simulated_feature_available_at'])>utc_time(row['decision_at']):why.add('FEATURE_AFTER_DECISION')
        if utc_time(row['label_end_at'])>=evaluation:why.add('EVALUATION_OVERLAP')
        for field in ('simulated_feature_available_at','simulated_label_available_at','simulated_revision_available_at'):
            if utc_time(row[field])>cutoff:why.add(field.upper()+'_AFTER_CUTOFF')
    included=[];excluded=[];selected=[]
    for index,row in enumerate(bundle['rows']):
        record=dict(index=index,symbol=row['symbol'],decision_at=row['decision_at'],row_sha256=_hash(row),label_revision_id=row['label_revision_id'],revision_available_at=row['simulated_revision_available_at'])
        why=reasons[row['decision_at']]
        if why:excluded.append(dict(record,reasons=sorted(why|{'SAME_DATE_PURGE'})))
        else:included.append(record);selected.append(rows[index])
    manifest=dict(schema='engineering-fit-manifest-v1',status='SYNTHETIC_ENGINEERING',year=year,horizon=c.horizon,cutoff=cutoff.isoformat(),feature_order=FEATURES,bundle_sha256=digest,registry_sha256=_hash([asdict(v) for v in VARIANTS]),included=included,excluded=excluded)
    _exact(value['fit_manifest'],manifest);_exact(value['fit_manifest_sha256'],_hash(manifest))
    expected_fit=_fit_equations([r['features'] for r in selected],[r['target'] for r in selected],c.alpha)
    m=value['model'];_exact(value['model_sha256'],_hash(m))
    expected_model=dict(schema='ridge-engineering-v1',status='SYNTHETIC_ENGINEERING',financial_accepted=False,candidate_id=c.candidate_id,horizon=c.horizon,feature_order=FEATURES,bundle_sha256=digest,fit_manifest_sha256=_hash(manifest),fit_cutoff=cutoff.isoformat(),observations=len(selected),scaler={'mean':expected_fit['mean'],'scale':expected_fit['scale']},ridge={'coef':expected_fit['coef'],'intercept':expected_fit['intercept']},resolved={'scaler':{'copy':True,'with_mean':True,'with_std':True},'ridge':{'alpha':c.alpha,'fit_intercept':True,'copy_X':True,'max_iter':None,'tol':1e-4,'solver':'svd','positive':False,'random_state':None},'row_weights':'EQUAL','dtype':'float64'},versions={name:version(name) for name in ('numpy','scipy','scikit-learn')})
    _exact(m['resolved'],expected_model['resolved']);_exact(m['versions'],expected_model['versions'])
    _compare(m,expected_model);_check(all(_numeric(x)>0 for x in m['scaler']['scale']))
    return {'assembled_rows':len(rows),'included_rows':len(selected),'excluded_rows':len(excluded),'omitted_rows':len(omissions),'fit_cutoff':cutoff.isoformat(),'model_sha256':value['model_sha256']},expected_fit


def _ranks_by_day(rows,dates):
    daily=[]
    for day in dates:
        selected=[r for r in rows if r['session']==day]
        corr=reconstruct_rank([r['prediction'] for r in selected],[r['target'] for r in selected])
        daily.append(dict(session=day,observations=len(selected),spearman=D(corr) if corr is not None else None,status='NO_SCORED_ROWS' if not selected else 'DEFINED' if corr is not None else 'UNDEFINED_CONSTANT_OR_TOO_FEW_ROWS'))
    return daily


def _ml_gate(candidate,errors):
    improvement=errors['mse_improvement']
    return 'NOT_APPLICABLE' if candidate.kind=='momentum' else 'UNDEFINED' if improvement is None else 'PASS' if D(improvement)>=D('.01') else 'FAIL'


@_precision
def audit_candidate_predictions(chunks,sectors,result,*,candidate_id,year,training_start,training_end,start,end,scoring_as_of):
    """Expected fold fields must come from the caller's original campaign bundle."""
    try:
        _check(type(result.content) is bytes and 0<len(result.content)<=MAX_BYTES and hashlib.sha256(result.content).hexdigest()==result.sha256,'AUDIT_INPUT_INVALID')
        v=json.loads(result.content);_check(canonical(v)==result.content,'AUDIT_INPUT_INVALID')
        c=variant(candidate_id);dates=_dates(start,end);_dates(training_start,training_end);cutoff=_cutoff(year);asof=utc_time(scoring_as_of)
        _check(start[:4]==end[:4]==str(year) and training_end<cutoff.date().isoformat()<=start,'AUDIT_INPUT_INVALID')
        market=load_market(chunks,sectors);_check(all('2016-01-01'<=day<'2024-01-01' for _,day,_ in market.rows),'AUDIT_INPUT_INVALID');source=SourceEvidence(market)
        expected=dict(schema='synthetic-candidate-fold-v1',status='SYNTHETIC_ENGINEERING',financial_accepted=False,full_M2=False,candidate=asdict(c),registered_family=[asdict(c) for c in VARIANTS],year=year,training_start=training_start,training_end=training_end,start=start,end=end,market_sha256=market.sha256,coverage_status='DIAGNOSTIC_PARTIAL_DEVELOPMENT_FOLD',fit_activation='SYNTHETIC_FIT_AUDIT_READY_ASSUMPTION',assumptions=['SYNTHETIC_ONLY','SIMULATED_AVAILABILITY','PARTIAL_TRAINING_AND_SCORING_WINDOWS','NO_FINANCIAL_QUALIFICATION','NO_ACTUAL_FIT_ACTIVATION_APPROVAL'])
        _check(set(v)==set(expected)|{'dataset_assembly','fit_rows','fit_manifest','fit_manifest_sha256','model','model_sha256','prediction_report','replays'})
        for key,value in expected.items():_exact(v[key],value)
        if c.kind=='ridge':fit,independent_model=_training(source,c,year,training_start,training_end,v)
        else:
            for key in ('dataset_assembly','fit_rows','fit_manifest','fit_manifest_sha256','model','model_sha256'):_check(v[key] is None)
            fit=independent_model=None
        _check(set(v['replays'])=={'10','20'})
        for cost,replay in v['replays'].items():
            for k,value in dict(candidate_id=candidate_id,horizon=c.horizon,cost_bps=int(cost),start=start,end=end,market_sha256=market.sha256,model_sha256=v['model_sha256'],financial_accepted=False,fit_activation='SYNTHETIC_FIT_AUDIT_READY_ASSUMPTION').items():_exact(replay[k],value)
        rows=[];omissions=[];feature_count=eligible=0
        for index,day in enumerate(dates):
            t=session_times(day)
            for symbol in WATCHLIST:
                try:
                    if symbol not in market.symbols:raise DataError('MISSING_SYMBOL')
                    if t.decision>asof:raise DataError('DECISION_UNAVAILABLE')
                    momentum=source.baseline(symbol,day,c.horizon);features=None
                    if c.kind=='ridge':
                        features=source.features(symbol,day)
                        if not features['raw_eligible']:raise DataError('INELIGIBLE_RAW_PRICE_OR_VOLUME')
                    feature_count+=1
                    if index+c.horizon>=len(dates):raise DataError('HORIZON_BOUNDARY')
                    eligible+=1;exit=dates[index+c.horizon];label=source.label(symbol,day,exit,c.horizon)
                    if label['available']>asof:raise DataError('LABEL_UNAVAILABLE')
                except DataError as exc:omissions.append({'session':day,'symbol':symbol,'reason':exc.code});continue
                prediction=momentum
                if features:
                    model=independent_model;prediction=D(str(math.fsum((x-mean)/scale*coef for x,mean,scale,coef in zip(features['values'],model['mean'],model['scale'],model['coef']))+model['intercept']))
                target=label['target']
                rows.append(dict(session=day,symbol=symbol,decision_at=t.decision.isoformat(),entry_at=t.entry.isoformat(),exit_at=session_times(exit).entry.isoformat(),label_available_at=label['available'].isoformat(),entry_revision=label['entry_revision'],exit_revision=label['exit_revision'],split_actions=label['split_actions'],prediction=prediction,momentum_prediction=momentum,target=target,signed_error=prediction-target,features=features['values'] if features else None,feature_sha256=features['input_sha256'] if features else None))
        report=v['prediction_report'];_check(set(report)=={'coverage','scoring_as_of','metrics','momentum_metrics','ml_contribution_gate','daily_rank_correlation','rows','omissions'})
        coverage=dict(candidate_rows=len(dates)*12,feature_eligible_rows=feature_count,eligible_rows=eligible,scored_rows=len(rows),omitted_rows=len(omissions))
        _exact(report['coverage'],coverage);_exact(report['scoring_as_of'],asof.isoformat());_exact(report['omissions'],omissions);_compare(report['rows'],rows)
        errors=reconstruct_errors([r['prediction'] for r in rows],[r['target'] for r in rows]);momentum_errors=reconstruct_errors([r['momentum_prediction'] for r in rows],[r['target'] for r in rows])
        _numeric_report(report['metrics'],errors);_numeric_report(report['momentum_metrics'],momentum_errors)
        # Reconcile recorded rows as well as the independent source equations.
        for row in report['rows']:
            _near(row['signed_error'],_numeric(row['prediction'])-_numeric(row['target']))
            if c.kind=='momentum':_check(_numeric(row['prediction'])==_numeric(row['momentum_prediction']))
            else:
                model=v['model'];served=math.fsum((x-mean)/scale*coef for x,mean,scale,coef in zip(row['features'],model['scaler']['mean'],model['scaler']['scale'],model['ridge']['coef']))+model['ridge']['intercept']
                _near(row['prediction'],served)
        recorded_errors=reconstruct_errors([r['prediction'] for r in report['rows']],[r['target'] for r in report['rows']])
        _numeric_report(report['metrics'],recorded_errors)
        _numeric_report(report['momentum_metrics'],reconstruct_errors([r['momentum_prediction'] for r in report['rows']],[r['target'] for r in report['rows']]))
        _compare(report['daily_rank_correlation'],_ranks_by_day(rows,dates))
        _compare(report['daily_rank_correlation'],_ranks_by_day(report['rows'],dates))
        _exact(report['ml_contribution_gate'],_ml_gate(c,errors));_exact(report['ml_contribution_gate'],_ml_gate(c,recorded_errors))
        value={'schema':'synthetic-prediction-audit-v1','status':'VERIFIED_PASS','scope':'SYNTHETIC_CAUSAL_PREDICTION_AND_FIT','financial_accepted':False,'full_M3':False,'candidate_sha256':result.sha256,'market_sha256':market.sha256,'expected_fold':dict(candidate_id=candidate_id,year=year,training_start=training_start,training_end=training_end,start=start,end=end,scoring_as_of=scoring_as_of),'coverage':coverage,'fit':fit,'prediction_metrics':errors,'momentum_metrics':momentum_errors,'gates':{k:'UNVERIFIED' for k in ('strategy_trade_selection','checkpoint_intervals','fit_activation','actual_arrival_accuracy','real_data_qualification','independent_native_auditor_identity','clean_locked_rerun','complete_campaign_shortlist')},'tolerances':{'atol':str(ABS),'rtol':str(REL)},'assumptions':['SYNTHETIC_ONLY','SIMULATED_AVAILABILITY','PARTIAL_WINDOWS','PRICE_LABEL_EXCLUDES_DIVIDENDS','HASHES_DO_NOT_AUTHENTICATE_AUTHOR']}
        raw=canonical(value);_check(len(raw)<=MAX_BYTES,'AUDIT_OUTPUT_BOUND');return PredictionAudit(raw,hashlib.sha256(raw).hexdigest())
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,DecimalException,RecursionError,np.linalg.LinAlgError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('AUDIT_INPUT_INVALID') from None
