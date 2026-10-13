"""Real Windows process exit/reacquisition; no in-memory mock of restart."""
import hashlib,json,os,sqlite3,subprocess,sys
from pathlib import Path
from uuid import uuid4
import pytest
from helpers.simulation_fixture import fixture,SECTORS
from compertum.simulation import replay

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')
ROOT=Path(__file__).parents[2]


def child(root,run,action,expected=0):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PYTHONPATH'}}
    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
        OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',NUMEXPR_NUM_THREADS='4')
    args=[sys.executable,'-B',str(ROOT/'tests/helpers/saved_run_child.py'),str(root),run,action]
    result=subprocess.run(args,executable=sys._base_executable,env=env,capture_output=True,timeout=45,creationflags=0x08000000)
    index=len(list(root.glob('process-*.json')))
    (root/f'process-{index:02}-{action}.json').write_text(json.dumps({'argv':args,'exit_code':result.returncode,
        'stdout':result.stdout.decode(),'stderr':result.stderr.decode()},indent=2))
    assert result.returncode==expected,result.stderr.decode()
    return json.loads(result.stdout) if expected==0 else None


@pytest.mark.parametrize('crash,exit_code',[('crash_before_compute',74),('crash_after_publish',73),('crash_after_write',75)])
def test_real_exit_resume_matches_uninterrupted(tmp_path,crash,exit_code):
    (tmp_path/'config.toml').write_bytes((ROOT/'config/default.toml').read_bytes());run=str(uuid4())
    created=child(tmp_path,run,'create');assert created['result']['state']=='PAUSED'
    child(tmp_path,run,'resume');child(tmp_path,run,crash,exit_code)
    after=child(tmp_path,run,'status')
    assert after['generation']>created['generation']
    assert after['result']['state']=='INTERRUPTED' and after['result']['completed_units']==0
    assert after['result']['attempts'][0]['reason']=='OWNER_RESTART'
    if crash=='crash_after_write':
        with sqlite3.connect((tmp_path/'state/research.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            rows=db.execute("SELECT maximum,written,path FROM reservations WHERE task=? AND status='ABANDONED'",(run,)).fetchall()
        assert len(rows)==1 and rows[0][0]>0 and rows[0][1]==0
        assert (tmp_path/rows[0][2]).stat().st_size==rows[0][0]
    orphans={p:p.read_bytes() for p in (tmp_path/f'artifacts/runs/{run}/baseline').glob('unit-*.json')}
    assert bool(orphans)==(crash=='crash_after_publish')
    child(tmp_path,run,'resume');first=child(tmp_path,run,'step')['result']
    assert first['completed_units']==1 and len(first['attempts'])==2
    child(tmp_path,run,'pause');assert child(tmp_path,run,'status')['result']['state']=='PAUSED'
    final=child(tmp_path,run,'finish')['result'];assert final['state']=='COMPLETED'
    chunks,start,end,_=fixture(scored=8)
    for result in final['results']:
        expected=replay(chunks,SECTORS,start,end,result['horizon'],cost_bps=result['cost_bps'])
        raw=(tmp_path/result['artifact']['path']).read_bytes()
        assert raw==expected.content and hashlib.sha256(raw).hexdigest()==result['artifact']['sha256']
    assert all(p.read_bytes()==raw for p,raw in orphans.items())
    assert len(final['results'])==6 and len(final['attempts'])==7


def test_stop_survives_new_owner_without_replay(tmp_path):
    (tmp_path/'config.toml').write_bytes((ROOT/'config/default.toml').read_bytes());run=str(uuid4())
    child(tmp_path,run,'create');child(tmp_path,run,'resume');child(tmp_path,run,'step')
    stopped=child(tmp_path,run,'stop')['result']
    restored=child(tmp_path,run,'status')['result']
    assert restored==stopped and restored['state']=='STOPPED' and restored['completed_units']==1
