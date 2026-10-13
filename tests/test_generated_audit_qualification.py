"""Annual offsets and compounding from audited records, with hand returns."""
from copy import deepcopy
from decimal import Decimal as D
import pytest
from compertum.audit_generated_final import _qualification
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.modeling.registry import variant
from compertum.simulation.policy import fixed_decimal


def hand_years():
 dates=['2024-12-17']
 while dates[-1]!='2025-01-16':dates.append(session_times(dates[-1]).next_date)
 folds=[]
 for year,base,stress in ((2024,D('.01'),D('.005')),(2025,D('.02'),D('.015'))):
  days=[d for d in dates if d[:4]==str(year)];books={}
  for cost,ret in (('10',base),('20',stress)):
   navs=[D(10000)]
   for _ in days:navs.append(navs[-1]*(1+ret))
   books[cost]=dict(strategy=navs,spy60=[D(10000)]*(len(days)+1))
  policy=dict(first_eligible_index=0,checkpoints=list(range(len(days))),holding_intervals=[dict(symbol='AAPL',start_index=0,end_index=1)])
  rows=[dict(session=days[0],symbol='AAPL',prediction='0.01',momentum_prediction='0.01',target='0.02')]
  folds.append(dict(dates=days,policy=policy,independent_predictions=rows,recorded_predictions=deepcopy(rows),independent_navs=books,recorded_navs=deepcopy(books)))
 return dict(inputs=dict(protocol_sha256='a'*64)),variant('momentum-h01'),dict(scoring_sessions=dates),folds


@fixed_decimal
def test_yearly_reset_is_not_an_investment_loss_and_offsets_are_continuous():
 p,c,m,folds=hand_years();v=_qualification(p,c,m,folds,independent=False);rows=list(map(D,v['inputs']['navs']));cut=len(folds[0]['dates'])
 assert abs(rows[cut+1]/rows[cut]-1-D('.02'))<D('1e-24')
 assert abs(D(v['period_mean_daily_excess']['2024'])-D('.01'))<D('1e-24')
 assert abs(D(v['period_mean_daily_excess']['2025'])-D('.02'))<D('1e-24')
 assert v['inputs']['segments']==[dict(start=0,end=cut-1,anchor=0),dict(start=cut,end=len(m['scoring_sessions'])-1,anchor=cut)]
 assert v['inputs']['checkpoints']==list(range(len(m['scoring_sessions'])))
 assert v['inputs']['intervals'][1]==dict(symbol='AAPL',entry=cut,exit=cut+1)
 assert v['numeric_gates']['daily_observations'] is False
 assert v['numeric_gates']['complete_window'] is False
 assert not v['paper_eligible'] and not v['strategy_accepted']
 assert v==_qualification(p,c,m,folds,independent=True)


def test_base_and_stress_sources_cannot_be_interchanged():
 p,c,m,folds=hand_years();v=_qualification(p,c,m,folds,independent=False)
 assert D(v['inputs']['stress_navs'][-1])<D(v['inputs']['navs'][-1])


def test_independent_path_does_not_read_recorded_nav_or_predictions():
 p,c,m,folds=hand_years();before=_qualification(p,c,m,folds,independent=True)
 for f in folds:f['recorded_navs']={};f['recorded_predictions']=[{'untrusted':'unused'}]
 assert _qualification(p,c,m,folds,independent=True)==before


@pytest.mark.parametrize('fault',['duplicate_interval','cross_year_interval','wrong_calendar','missing_checkpoint'])
def test_invented_qualification_evidence_refuses(fault):
 p,c,m,folds=hand_years()
 if fault=='duplicate_interval':folds[0]['policy']['holding_intervals']*=2
 elif fault=='cross_year_interval':folds[0]['policy']['holding_intervals'][0].update(start_index=len(folds[0]['dates'])-1,end_index=len(folds[0]['dates']))
 elif fault=='wrong_calendar':m['scoring_sessions'].pop(2)
 else:folds[1]['policy']['checkpoints'].pop()
 with pytest.raises(DataError):_qualification(p,c,m,folds,independent=False)
