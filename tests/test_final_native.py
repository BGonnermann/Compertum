"""Real private RPC final lifecycle, with explicitly simulated campaign workers."""
import json,os,subprocess,sys,time
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused


def test_native_final_empty_restart_barrier_and_limits(tmp_path):
    from test_fixture_processes import fixture_module
    from compertum.runtime.owners import release_owner,acquire_owner
    from compertum.runtime.managed import launch_owner
    from compertum.runtime.owner_rpc import call_owner
    from compertum.runtime.identity import resolve_project
    from compertum.storage import StorageManager
    from compertum.config import load_config
    from compertum.final_transaction import reserve_final
    from compertum.consumption import verify_consumption_guard
    from compertum.evaluation_seals import verify_seal_journal
    root=tmp_path/'prepared';root.mkdir()
    code="""import sys,json
from pathlib import Path
sys.path.insert(0,str(Path('tests').resolve()))
import pytest
from test_shortlist_owner import make_committed,owned,pair_inputs,environment
from test_shortlist_freeze_journal import freeze_now
from compertum.final_transaction import recipe_sha256
from compertum.data.encoding import canonical
root=Path(sys.argv[1]);generator=owned.__wrapped__(root);ownership=next(generator)
try:
 with pytest.MonkeyPatch.context() as patch:
  pair=pair_inputs.__wrapped__(environment.__wrapped__(root,patch))
  pair[0]['holdout_manifest_sha256']=recipe_sha256()
  seals,p,ticket,states,reviews=make_committed(ownership,pair,patch,real_runtime=True)
  freeze_now(seals,p,ticket)
  (root/'prepared-final.json').write_bytes(canonical(dict(pair=p,ticket_sha256=ticket.sha256)))
  seals.store.close();reviews.store.close()
finally:generator.close()
"""
    child=fixture_module().python_process(['-B','-c',code,str(root)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    out,err=child.communicate(timeout=30);assert child.returncode==0,(out,err)
    v=json.loads((root/'prepared-final.json').read_bytes());p=v['pair'];project=resolve_project(root)
    coordinator=acquire_owner(project,'coordinator');supervisor=acquire_owner(project,'supervisor');jobs=[];remotes=[]
    try:
        storage=StorageManager(coordinator,load_config(root/'config.toml',root))
        job,remote=launch_owner(supervisor,'evaluation');jobs.append(job);remotes.append(remote)
        limits=job.api.limits(job.job);assert limits.job_memory==256*1024**2 and limits.basic.active_limit==1 and limits.basic.affinity.bit_count()==1
        eid=str(uuid4());request=dict(operation='prepare_final',seal_id=p['source']['seal_id'],evaluation_id=eid)
        reserve_final(storage,p['source']['seal_id'])
        started=time.monotonic();first=call_owner(remote,'synthetic_protocol',request);elapsed=time.monotonic()-started
        assert elapsed<5 and first['status']=='NO_CANDIDATE_QUALIFIES' and first['price_reads']==0
        barrier=str(uuid4());call_owner(remote,'checkpoint',dict(operation='snapshot',barrier_id=barrier,destination='backups/final-fixture.sqlite',maximum_bytes=2*1024**2))
        with pytest.raises(RuntimeRefused,match='BARRIER_HELD'):call_owner(remote,'synthetic_protocol',request)
        call_owner(remote,'checkpoint',dict(operation='end',barrier_id=barrier))
        peak=job.api.limits(job.job).peak_job_memory
        remote.close();job.close();job,remote=launch_owner(supervisor,'evaluation');jobs.append(job);remotes.append(remote)
        assert call_owner(remote,'synthetic_protocol',request)==first
        assert call_owner(remote,'synthetic_protocol',dict(operation='inspect_final',seal_id=p['source']['seal_id']))==first
        with pytest.raises(RuntimeRefused,match='FINAL_CONFLICT'):
            call_owner(remote,'synthetic_protocol',dict(request,evaluation_id=str(uuid4())))
        assert verify_consumption_guard(project)['sequence']==1
        assert verify_seal_journal(project)['sequence']==7
        peak=max(peak,job.api.limits(job.job).peak_job_memory);assert 0<peak<=256*1024**2
        record=dict(scope='NATIVE_FINAL_OWNER_WITH_SIMULATED_CAMPAIGN_WORKER_RECEIPTS',final_seconds=elapsed,owner_peak_bytes=peak,owner_limit_bytes=256*1024**2,receipt=first,full_M3=False,financial_accepted=False)
        (root/'native-final-measurement.json').write_bytes(canonical(record))
    finally:
        for remote in remotes:remote.close()
        for job in jobs:job.close()
        release_owner(supervisor);release_owner(coordinator)

