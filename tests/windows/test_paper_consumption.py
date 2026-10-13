"""Actual1GiB reserve and separate native processes. Offline records only."""
import json,os,subprocess,sys
from pathlib import Path
import pytest
from fixture_processes import python_process
from uuid import uuid4


def run_native(helper,root,argument,expected=0,*,timeout=40):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    p=python_process(['-B',str(helper),str(root),str(argument)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=0x08000000)
    try:out,err=p.communicate(timeout=timeout)
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=5)
    assert p.returncode==expected and not err,(p.returncode,out,err)
    if not out:return None
    import compertum
    value=json.loads(out);assert value.pop('package_origin')==str(Path(compertum.__file__).resolve())
    return value


def invoke(root,action,**arguments):
    packet=root/('invocation-'+str(uuid4())+'.json');packet.write_text(json.dumps(dict(action=action,**arguments)))
    return run_native(Path(__file__).resolve().parents[1]/'helpers/recovery_fixture.py',root,packet)


@pytest.mark.parametrize('point',['before_consumption','after_identity','before_head','after_head','after_commit'])
def test_process_crash_never_regrants_consumption(tmp_path,point):
    helper=Path(__file__).resolve().parents[1]/'helpers/paper_consumption_crash.py'
    run_native(helper,tmp_path,point,23);result=run_native(helper,tmp_path,'inspect')
    fixture=json.loads((tmp_path/'paper-fixture.json').read_text());r=fixture['reserve']
    assert r['capacity_bytes']==1024**3 and r['allocated_bytes']>=r['unused_bytes']==1024**3 and r['sparse'] is False
    if point=='before_head':assert result=={'status':'EXECUTION_COMPROMISED'}
    else:
        assert result['generation']==2 and result['guard']=='VERIFIED' and result['waiting']=='PAPER_SKIPPED_RESTART'
        assert result['result']['first_consumption'] is result['result']['transport_authorized'] is False
        assert result['result']['record']['status']==('PAPER_CONSUMED' if point in ('after_head','after_commit') else 'PAPER_SKIPPED_RESTART')
    (tmp_path/'crash-result.json').write_text(json.dumps(dict(point=point,result=result,reserve=r)))


def test_old_recovery_set_preserves_later_paper_consumption(tmp_path):
    p=invoke(tmp_path,'prepare',paper_preparation=True);r=p['actual_reserve']
    assert r['capacity_bytes']==1024**3 and r['allocated_bytes']>=1024**3 and r['sparse'] is False
    args=dict(manifest=p['before'],seal_id=p['seal_id'],evaluation_id=p['evaluation_id'],pending_event=p['pending_event'])
    for n in range(2):
        restored=invoke(tmp_path,'restore',**args)
        assert restored['status']=='RESTORED' and restored['execution_state']=='VERIFIED' and restored['admission']=='HALTED'
        result=invoke(tmp_path,'inspect_paper')
        assert not result['result']['first_consumption'] and not result['result']['transport_authorized']
        assert result['result']['record']['status']=='PAPER_CONSUMED' and result['waiting']=='PAPER_SKIPPED_RESTART'
    (tmp_path/'paper-restore-result.json').write_text(json.dumps(dict(restore=restored,result=result,reserve=r)))


def test_blocked_fixture_timeout_releases_actual_execution_owner(tmp_path,monkeypatch):
    import time
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    actual=python_process;children=[]
    def launched(*a,**kw):
        child=actual(*a,**kw);children.append(child);deadline=time.monotonic()+8
        while not (tmp_path/'blocked-ready.json').exists():
            if child.poll() is not None or time.monotonic()>deadline:
                if child.poll() is None:child.kill()
                child.communicate(timeout=5);pytest.fail('BLOCKED_FIXTURE_START_FAILED')
            time.sleep(.02)
        return child
    monkeypatch.setattr(sys.modules[__name__],'python_process',launched)
    helper=Path(__file__).resolve().parents[1]/'helpers/paper_consumption_crash.py'
    with pytest.raises(subprocess.TimeoutExpired):run_native(helper,tmp_path,'block',timeout=.05)
    assert len(children)==1 and children[0].poll() is not None
    lease=acquire_owner(resolve_project(tmp_path),'execution')
    try:assert lease.generation==2
    finally:release_owner(lease)
