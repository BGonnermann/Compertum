"""Short-lived native owner fixture, including deliberate abrupt-exit cases."""
from pathlib import Path
import json,os,sys
from uuid import uuid4

from compertum.config import load_config
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.storage import StorageManager
from compertum.simulation.runs import SavedRuns
from simulation_fixture import fixture,SECTORS

root=Path(sys.argv[1]).resolve();run_id=sys.argv[2];action=sys.argv[3]
lease=acquire_owner(resolve_project(root),'coordinator')
try:
    storage=StorageManager(lease,load_config(root/'config.toml',root));runs=SavedRuns(storage)
    if action in ('create','create_prediction'):
        chunks,start,end,_=fixture(scored=26 if action=='create_prediction' else 8)
        options={'scoring_as_of':'2026-10-09T00:00:00Z'} if action=='create_prediction' else {}
        result=runs.create(run_id,chunks,SECTORS,start,end,**options)
    elif action=='create_provider':
        from compertum.data.alpaca import read_bar_evidence
        from compertum.data.provider_snapshot import build_provider_snapshot
        from compertum.simulation.provider_replay import read_scenario
        source=root/'provider-fixture-inputs.json'
        if source.stat().st_size>20*1024**2:raise RuntimeError('FIXTURE_INPUT_BOUND')
        bundle=json.loads(source.read_bytes())
        chunks=tuple(read_bar_evidence(v.encode('utf-8')) for v in bundle['evidence_utf8'])
        snapshot=build_provider_snapshot(chunks,start=bundle['start'],end=bundle['end'],feed='sip')
        result=runs.create_provider(run_id,snapshot,read_scenario(bundle['scenario_utf8'].encode('utf-8')))
    elif action in ('pause','resume','stop'):result=runs.control(run_id,str(uuid4()),action)
    elif action=='status':result=runs.status(run_id)
    elif action=='step':result=runs.step(run_id)
    elif action in ('crash_after_publish','crash_before_compute','crash_after_write'):
        if action=='crash_after_publish':
            original=storage.open_artifact
            def open_artifact(*args):
                writer=original(*args);publish=writer.publish
                def crash():publish();os._exit(73)
                writer.publish=crash;return writer
            storage.open_artifact=open_artifact
        elif action=='crash_after_write':
            original=storage.open_artifact
            def open_artifact(*args):
                writer=original(*args);stream=writer.stream
                class ExitAfterWrite:
                    def write(self,raw):
                        stream.write(raw);stream.flush();os.fsync(stream.fileno());os._exit(75)
                    def __getattr__(self,name):return getattr(stream,name)
                writer.stream=ExitAfterWrite();return writer
            storage.open_artifact=open_artifact
        else:
            import compertum.simulation.runs as module
            def crash(*args,**kwargs):os._exit(74)
            module.compute_unit=crash
        result=runs.step(run_id)
    elif action=='finish':
        runs.control(run_id,str(uuid4()),'resume')
        for _ in range(6):
            result=runs.step(run_id)
            if result['state']=='COMPLETED':break
    else:raise RuntimeError('UNKNOWN_FIXTURE_ACTION')
    print(json.dumps({'generation':lease.generation,'result':result}),flush=True)
finally:release_owner(lease)
