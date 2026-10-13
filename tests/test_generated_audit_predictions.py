"""Hand prediction/error and missing-coverage checks without numerical campaigns."""
from copy import deepcopy
from decimal import Decimal as D
import pytest
from compertum.audit_generated_predictions import predictions
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.modeling.registry import variant
from compertum.simulation.market import WATCHLIST
from test_generated_audit_fit import HandSource,DATES


def hand_prediction():
 source=HandSource();source.baseline=lambda symbol,day,h:D('.001')
 dates=DATES[:2];asof=session_times(DATES[2]).decision;t=session_times(dates[0]);end=dates[1];label=source.label('AAPL',dates[0],end,1)
 row=dict(session=dates[0],symbol='AAPL',decision_at=t.decision.isoformat(),entry_at=t.entry.isoformat(),exit_at=session_times(end).entry.isoformat(),label_available_at=label['available'].isoformat(),entry_revision=label['entry_revision'],exit_revision=label['exit_revision'],split_actions=[],prediction='0.001',momentum_prediction='0.001',target='0.01',signed_error='-0.009',features=None,feature_sha256=None)
 omissions=[]
 for i,day in enumerate(dates):
  for symbol in WATCHLIST:
   if symbol!='AAPL':omissions.append(dict(session=day,symbol=symbol,reason='MISSING_SYMBOL'))
   elif i==1:omissions.append(dict(session=day,symbol=symbol,reason='HORIZON_BOUNDARY'))
 errors=dict(observations=1,mse='0.000081',mae='0.009',mean_signed_error='-0.009',zero_mse='0.0001',zero_mae='0.01',zero_mean_signed_error='-0.01',mse_improvement='0.19',status='DEFINED')
 report=dict(coverage=dict(candidate_rows=24,feature_eligible_rows=2,eligible_rows=1,scored_rows=1,omitted_rows=23),scoring_as_of=asof.isoformat(),metrics=errors,momentum_metrics=deepcopy(errors),ml_contribution_gate='NOT_APPLICABLE',daily_rank_correlation=[dict(session=dates[0],observations=1,spearman=None,status='UNDEFINED_CONSTANT_OR_TOO_FEW_ROWS'),dict(session=dates[1],observations=0,spearman=None,status='NO_SCORED_ROWS')],rows=[row],omissions=omissions)
 return source,variant('momentum-h01'),dates,asof,report


def test_hand_error_and_missing_denominator_reconstruct():
 source,c,dates,asof,report=hand_prediction();rows,summary=predictions(source,c,dates,asof,report,None,None)
 assert len(rows)==1 and rows[0]['signed_error']==D('-.009')
 assert summary['coverage']['candidate_rows']==24 and summary['coverage']['omitted_rows']==23
 assert summary['prediction_metrics']['mse']=='0.000081'


@pytest.mark.parametrize('fault',['target','prediction','error','revision','availability','duplicate','coverage','omission','rank','metrics','gate','asof','extra'])
def test_prediction_claims_cannot_override_original_rows_or_missing_coverage(fault):
 source,c,dates,asof,report=hand_prediction();v=deepcopy(report)
 if fault=='target':v['rows'][0]['target']='0.02'
 elif fault=='prediction':v['rows'][0]['prediction']='0.1'
 elif fault=='error':v['rows'][0]['signed_error']='0'
 elif fault=='revision':v['rows'][0]['entry_revision']='different'
 elif fault=='availability':v['rows'][0]['label_available_at']=v['rows'][0]['entry_at']
 elif fault=='duplicate':v['rows'].append(deepcopy(v['rows'][0]))
 elif fault=='coverage':v['coverage']['candidate_rows']=2
 elif fault=='omission':v['omissions'].pop()
 elif fault=='rank':v['daily_rank_correlation'][0]['spearman']='1'
 elif fault=='metrics':v['metrics']['mse']='0'
 elif fault=='gate':v['ml_contribution_gate']='PASS'
 elif fault=='asof':v['scoring_as_of']=session_times(dates[0]).decision.isoformat()
 else:v['verified']=True
 with pytest.raises(DataError):predictions(source,c,dates,asof,v,None,None)
