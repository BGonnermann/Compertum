"""Owner-held provider diagnostics preserve controls and reject wrong worker kinds."""
from uuid import uuid4
import json,hashlib
import pytest
from test_persistence import owned
from test_storage import manager
from test_provider_replay import snapshot,envelopes,scenario
from compertum.simulation.runs import SavedRuns
from compertum.data.errors import DataError

def setup(owned,snapshot):
 storage=manager(owned);runs=SavedRuns(storage);run=str(uuid4());s=scenario(snapshot)
 assert hasattr(runs,'create_provider'),'Distinct saved provider input entry point missing'
 created=runs.create_provider(run,snapshot,s,maximum_bytes=32*1024**2)
 return storage,runs,run,s,created

def control(runs,run,action):return runs.control(run,str(uuid4()),action)

def test_provider_saved_pause_resume_exact_all_six_units(owned,snapshot):
 from compertum.simulation.provider_replay import replay_provider
 storage,runs,run,s,created=setup(owned,snapshot)
 assert created['state']=='PAUSED' and created['input_kind']=='provider-diagnostic'
 assert runs.create_provider(run,snapshot,s,maximum_bytes=32*1024**2)==created
 control(runs,run,'resume');runs.step(run);control(runs,run,'pause')
 with pytest.raises(DataError,match='RUN_NOT_READY'):runs.step(run)
 control(runs,run,'resume')
 for _ in range(5):runs.step(run)
 result=runs.status(run);assert result['state']=='COMPLETED' and len(result['results'])==6
 for row in result['results']:
  expected=replay_provider(snapshot,s,row['horizon'],cost_bps=row['cost_bps'])
  assert (storage.root/row['artifact']['path']).read_bytes()==expected.content


def test_provider_stop_and_corrupt_input_are_conservative(owned,snapshot):
 storage,runs,run,s,created=setup(owned,snapshot)
 control(runs,run,'resume');runs.step(run);control(runs,run,'stop')
 with pytest.raises(DataError,match='RUN_TERMINAL'):control(runs,run,'resume')
 assert runs.status(run)['completed_units']==1
 other=str(uuid4());v=runs.create_provider(other,snapshot,s)
 (storage.root/v['input_artifact']['path']).write_bytes(b'corrupt')
 with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):control(runs,other,'resume')
 assert control(runs,other,'stop')['state']=='STOPPED'


def test_native_worker_compute_kind_is_bound_to_saved_request(owned,snapshot):
 from compertum.runtime.replay_worker import compute
 from compertum.simulation.worker_record import verify_result
 from compertum.simulation.provider_replay import replay_provider
 storage,runs,run,s,created=setup(owned,snapshot)
 raw=(storage.root/created['input_artifact']['path']).read_bytes();digest=hashlib.sha256(raw).hexdigest()
 bundle=json.loads(raw);assert sorted(bundle['provider_evidence_utf8'])==sorted(c.content.decode('utf-8') for c in snapshot.evidence)
 result=compute(raw,digest,0)
 assert verify_result(result,digest,1,10,input_kind='provider-diagnostic')==replay_provider(snapshot,s,1).content
 with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):verify_result(result,digest,1,10)
 with pytest.raises(DataError):verify_result(result,digest,1,10,input_kind='qualified-real')


def test_native_job_accepts_only_provider_header_for_provider_run(owned,snapshot):
 from compertum.runtime.jobs import launch_bounded
 from compertum.storage import adopt_fixture_bytes
 from windows.test_replay_job import specification
 storage,runs,run,s,created=setup(owned,snapshot);control(runs,run,'resume');admitted=runs.begin(run)
 writer=storage.open_artifact(storage.reserve_bytes(run,'records',16*1024**2),f'artifacts/runs/{run}/baseline/unit-00-attempt-1.replay');job=None
 try:
  job=launch_bounded(storage.lease,specification(storage.root,run,admitted['input_artifact']),['fixture','replay',str(writer.destination)],writer=writer,input_artifact=admitted['input_artifact'],unit=0)
  receipt=job.wait();assert receipt['exit_code']==0 and receipt['active_processes']==0
  adopt_fixture_bytes(writer,job);artifact=writer.publish();assert runs.accept(run,artifact)['completed_units']==1
 finally:
  if job:job.close()
  writer.close()