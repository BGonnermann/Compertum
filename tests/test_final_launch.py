"""Launcher policy refusals only; no native worker or RAM admission is claimed."""
import pytest
from test_final_dispatch import dispatch,owned,pair_inputs,environment
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime import jobs

@pytest.mark.parametrize('fault',['missing_callback','missing_request','foreign_review','foreign_input'])
def test_final_mode_refuses_unbound_launch_before_native_creation(dispatch,monkeypatch,fault):
 runs,seals,p,d,task,out=dispatch
 # Isolate policy checks. The native boundary is a failing sentinel, not a worker.
 monkeypatch.setattr(jobs,'available_physical_memory',lambda:8*1024**3)
 def forbidden():raise AssertionError('Native API reached for invalid dispatch')
 monkeypatch.setattr(jobs,'JobAPI',forbidden)
 kw=dict(writer=out,final_request=d,before_resume=lambda n:None)
 if fault=='missing_callback':kw['before_resume']=None
 elif fault=='missing_request':kw['final_request']=None
 elif fault=='foreign_review':kw['review_request']={}
 else:kw['input_artifact']={}
 with pytest.raises(RuntimeRefused,match='FINAL_INPUT_DENIED|REPLAY_INPUT_DENIED|REVIEW_INPUT_DENIED'):
  jobs.launch_bounded(runs.storage.lease,task,['fixture','final',str(out.destination)],**kw)

def test_final_request_cannot_expand_other_registered_modes(dispatch,monkeypatch):
 runs,seals,p,d,task,out=dispatch
 with pytest.raises(RuntimeRefused,match='FINAL_INPUT_DENIED'):
  jobs.launch_bounded(runs.storage.lease,task,['fixture','canonical',str(out.destination)],writer=out,final_request=d)
