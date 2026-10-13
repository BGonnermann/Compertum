"""Owner metadata and early worker checks must not load scientific libraries."""
import subprocess,sys
import pytest

GUARD="""import sys,importlib.abc
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'numpy','scipy','sklearn','pandas','exchange_calendars'} or fullname=='compertum.data.calendar':
   raise AssertionError('Numerical import before admission: '+fullname)
sys.meta_path.insert(0,Deny())
"""

@pytest.mark.parametrize('module',['compertum.execution_operation_owner','compertum.execution_plan_owner','compertum.execution_observations','compertum.execution_authority','compertum.runtime.execution_health','compertum.fake_recovery','compertum.fake_attempt_guard','compertum.deterministic_broker','compertum.fake_execution_driver','compertum.fake_execution_journal','compertum.execution_contracts','compertum.execution_risk','compertum.execution_plans','compertum.final_controller','compertum.recovery_lineage','compertum.final_dispatch','compertum.final_completion','compertum.final_task','compertum.runtime.final_worker','compertum.final_transaction','compertum.shortlist_evidence','compertum.shortlist_freeze','compertum.evaluation_seals','compertum.prepared_campaign','compertum.development_seals','compertum.data.snapshot_text','compertum.modeling.registry','compertum.simulation.campaign_record','compertum.simulation.campaign_runs','compertum.audit_runs','compertum.runtime.jobs','compertum.runtime.campaign_worker','compertum.runtime.audit_worker','compertum.runtime.campaign_review_worker'])
def test_metadata_and_entrypoint_imports_are_lightweight(module):
 result=subprocess.run([sys.executable,'-B','-c',GUARD+'\nimport '+module],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr

@pytest.mark.parametrize('module',['campaign_worker','audit_worker'])
def test_malformed_worker_arguments_fail_before_numerical_imports(module):
 code=GUARD+'\nfrom compertum.runtime import '+module+' as m\nsys.argv=["worker"]\nassert m.main()==6'
 result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr


def test_shared_schedule_matches_fixed_protocol_without_calendar():
 code=GUARD+'''
from dataclasses import asdict
from compertum.campaign_contract import UNITS,VARIANTS,FEATURES
from compertum.evaluation_protocol import fixed_definition
p=fixed_definition()
assert len(UNITS)==63 and [asdict(v) for v in VARIANTS]==p['registered_family'] and list(FEATURES)==p['features']
assert len({u.key for u in UNITS})==63
assert sum(u.phase=='fit' for u in UNITS)==27 and sum(u.phase=='evaluate' for u in UNITS)==36
for i,u in enumerate(UNITS):
 if u.fit_unit is not None:
  fit=UNITS[u.fit_unit]
  assert u.fit_unit==i-1 and fit.phase=='fit' and fit.candidate_id==u.candidate_id and fit.year==u.year
'''
 result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr
