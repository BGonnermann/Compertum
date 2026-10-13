"""Small hand-computed fit/purge case; no generated full market or native fixture."""
from copy import deepcopy
from decimal import Decimal as D
from types import SimpleNamespace
import math
import pytest
from compertum.audit_generated_predictions import training
from compertum.audit_predictions import _hash
from compertum.data.calendar import session_times,utc_time
from compertum.data.errors import DataError
from compertum.modeling.registry import FEATURES,variant
from compertum.simulation.market import WATCHLIST

DATES=['2023-12-20','2023-12-21','2023-12-22','2023-12-26','2023-12-27','2023-12-28','2023-12-29']
class HandSource:
 market=SimpleNamespace(symbols=('AAPL','SPY'),sha256='a'*64)
 def features(self,symbol,day):
  t=session_times(day)
  return dict(values=[float(DATES.index(day)+1)]+[0.0]*14,feature_session=t.previous_date,available=t.decision,input_sha256=_hash([symbol,day]),raw_eligible=True)
 def label(self,symbol,day,end,horizon):
  return dict(target=D(DATES.index(day)+1)/100,available=session_times(session_times(end).next_date).decision,sha256=_hash([symbol,day,end,horizon]),entry_revision='entry-'+day,exit_revision='entry-'+end,split_actions=[])


def hand_fit():
 source=HandSource();c=variant('ridge-h01-a001');cutoff='2024-01-02T12:00:00+00:00'
 annual=dict(training_start=DATES[0],training_end=DATES[-1],cutoff=cutoff)
 metadata=dict(sessions=DATES,annual={'2024':annual},recipe_sha256='b'*64)
 rows=[];provenance=[];omissions=[]
 for day in DATES:
  t=session_times(day);end=t.next_date;f=source.features('AAPL',day);label=source.label('AAPL',day,end,1);available=label['available'].isoformat();revision='label-'+label['sha256'];identity=dict(symbol='AAPL',decision_at=t.decision.isoformat())
  rows.append(dict(identity,feature_session=t.previous_date,entry_at=t.entry.isoformat(),label_end_at=session_times(end).entry.isoformat(),simulated_feature_available_at=f['available'].isoformat(),simulated_label_available_at=available,simulated_revision_available_at=available,label_revision_id=revision,features=f['values'],target=float(label['target'])))
  provenance.append(dict(identity,feature_sha256=f['input_sha256'],label_sha256=label['sha256'],entry_revision_id=label['entry_revision'],exit_revision_id=label['exit_revision'],split_action_ids=[],selected_label_revision_id=revision,label_available_at=available))
  omissions.extend(dict(symbol=s,decision_at=t.decision.isoformat(),reasons=['MISSING_SYMBOL']) for s in WATCHLIST if s!='AAPL')
 omissions.sort(key=lambda r:(r['decision_at'],r['symbol']))
 included=[];excluded=[]
 for i,row in enumerate(rows):
  record=dict(index=i,symbol='AAPL',decision_at=row['decision_at'],row_sha256=_hash(row),label_revision_id=row['label_revision_id'],revision_available_at=row['simulated_revision_available_at'])
  if i<5:included.append(record)
  else:
   reasons=['SAME_DATE_PURGE','SIMULATED_LABEL_AVAILABLE_AT_AFTER_CUTOFF','SIMULATED_REVISION_AVAILABLE_AT_AFTER_CUTOFF']
   if i==6:reasons.append('EVALUATION_OVERLAP')
   excluded.append(dict(record,reasons=sorted(reasons)))
 manifest=dict(schema='generated-fit-manifest-v1',year=2024,horizon=1,cutoff=cutoff,feature_order=FEATURES,rows_sha256=_hash(rows),included=included,excluded=excluded)
 versions={'numpy':'test-numpy','scipy':'test-scipy','scikit-learn':'test-sklearn'}
 model=dict(schema='generated-ridge-v1',candidate_id=c.candidate_id,horizon=1,recipe_sha256='b'*64,market_sha256='a'*64,financial_accepted=False,feature_order=FEATURES,rows_sha256=_hash(rows),manifest_sha256=_hash(manifest),fit_cutoff=cutoff,observations=5,scaler=dict(mean=[3.0]+[0.0]*14,scale=[math.sqrt(2)]+[1.0]*14),ridge=dict(coef=[1/(60*math.sqrt(2))]+[0.0]*14,intercept=.03),resolved={'scaler':{'copy':True,'with_mean':True,'with_std':True},'ridge':{'alpha':1,'fit_intercept':True,'copy_X':True,'max_iter':None,'tol':1e-4,'solver':'svd','positive':False,'random_state':None},'row_weights':'EQUAL','dtype':'float64'},versions=versions)
 value=dict(candidate_id=c.candidate_id,year=2024,horizon=1,training_start=DATES[0],training_end=DATES[-1],training_sessions=7,rows=rows,omissions=omissions,provenance=provenance,manifest=manifest,model=model,model_sha256=_hash(model))
 return source,c,metadata,value,dict(distributions=list(versions.items()))


def test_hand_fit_equations_and_two_future_label_dates_are_purged():
 source,c,metadata,value,runtime=hand_fit();report,solved,_=training(source,c,metadata,2024,value,runtime)
 assert report['included_rows']==5 and report['excluded_rows']==2 and report['omitted_rows']==77
 assert solved['mean'][0]==3 and abs(solved['coef'][0]-1/(60*math.sqrt(2)))<1e-14
 assert abs(solved['intercept']-.03)<1e-14


@pytest.mark.parametrize('fault',['feature','target','arrival','source_hash','omission','purge','coefficient','row_hash','version','extra_model','estimator_tolerance'])
def test_rehashed_fit_corruption_cannot_supply_its_own_proof(fault):
 source,c,metadata,value,runtime=hand_fit();v=deepcopy(value)
 if fault=='feature':v['rows'][0]['features'][0]=2.0
 elif fault=='target':v['rows'][0]['target']=.4
 elif fault=='arrival':v['rows'][-1]['simulated_label_available_at']=v['rows'][0]['simulated_label_available_at']
 elif fault=='source_hash':v['provenance'][0]['feature_sha256']='0'*64
 elif fault=='omission':v['omissions'].pop()
 elif fault=='purge':v['manifest']['included'].append(v['manifest']['excluded'].pop())
 elif fault=='coefficient':v['model']['ridge']['coef'][0]=.5
 elif fault=='row_hash':v['model']['rows_sha256']='0'*64
 elif fault=='version':v['model']['versions']['numpy']='different'
 elif fault=='extra_model':v['model']['approval']=True
 else:v['model']['resolved']['ridge']['tol']=.00010000005
 v['model_sha256']=_hash(v['model'])
 with pytest.raises(DataError):training(source,c,metadata,2024,v,runtime)
