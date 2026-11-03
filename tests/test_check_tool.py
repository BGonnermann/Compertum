import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import check  # noqa: E402


def fake_lanes(root,body):
    test=root/'test_sample.py';test.write_text(body,encoding='utf-8')
    return {'sample':('engine',[str(test)])}


def test_pass_cleanup(tmp_path,monkeypatch,capsys):
    """A passing lane leaves no folder, only one history line; an earlier failed run of the same lane is removed."""
    runs=tmp_path/'runs';runs.mkdir();old=runs/'check-sample-20260101-000000';old.mkdir();(old/check.FAILED).write_text('{}',encoding='utf-8')
    other=runs/'check-other-20260101-000000';other.mkdir();(other/check.FAILED).write_text('{}',encoding='utf-8')
    monkeypatch.setattr(check,'lane_files',lambda root=None: fake_lanes(tmp_path,'def test_ok():\n    assert True\n'))
    monkeypatch.setattr(check.run_tests,'free_gib',lambda:40.0);monkeypatch.setattr(check.run_tests,'open_engine_runs',lambda:[])
    assert check.main(['--lanes','sample'],runs=runs)==0
    assert sorted(p.name for p in runs.iterdir())==[check.HISTORY,'check-other-20260101-000000']
    row=json.loads((runs/check.HISTORY).read_text(encoding='utf-8').strip().splitlines()[-1])
    assert row['passed'] and row['lane']=='sample' and row['resolved_failures']==['check-sample-20260101-000000'] and '1 passed' in row['summary']
    assert 'CHECK: PASS' in capsys.readouterr().out


def test_fail_evidence(tmp_path,monkeypatch,capsys):
    """A failing lane keeps its folder with output.txt and failed.json, adds one history line, and answers FAIL."""
    runs=tmp_path/'runs';runs.mkdir()
    monkeypatch.setattr(check,'lane_files',lambda root=None: fake_lanes(tmp_path,'def test_bad():\n    assert False\n'))
    monkeypatch.setattr(check.run_tests,'free_gib',lambda:40.0);monkeypatch.setattr(check.run_tests,'open_engine_runs',lambda:[])
    assert check.main(['--lanes','sample'],runs=runs)==1
    kept=[p for p in runs.iterdir() if p.is_dir()];assert len(kept)==1 and (kept[0]/'output.txt').is_file() and (kept[0]/check.FAILED).is_file()
    out=capsys.readouterr().out;assert 'CHECK: FAIL' in out and 'Evidence:' in out


def test_light_beside(tmp_path,monkeypatch,capsys):
    """The harness and tools lanes run beside the sandbox lanes; the engine and product lanes never overlap each other."""
    import threading,time
    spans={};lock=threading.Lock()
    def fake(name,env,files,runs,live=False):
        start=time.monotonic();time.sleep(0.3)
        with lock: spans[name]=(start,time.monotonic())
        job=runs/f'{check.PREFIX}{name}-x';job.mkdir()
        return {'lane':name,'env':env,'files':1,'exit_code':0,'summary':'1 passed','passed':True,'seconds':0.3,'output_sha256':'0','folder':job}
    monkeypatch.setattr(check,'run_lane',fake)
    monkeypatch.setattr(check.run_tests,'free_gib',lambda:40.0);monkeypatch.setattr(check.run_tests,'open_engine_runs',lambda:[])
    runs=tmp_path/'runs';runs.mkdir()
    assert check.main([],runs=runs)==0
    assert spans['engine'][1]<=spans['product'][0] and spans['harness'][0]<spans['engine'][1] and spans['tools'][0]<spans['engine'][1]
    assert 'CHECK: PASS (engine 1 passed, product 1 passed, harness 1 passed, tools 1 passed)' in capsys.readouterr().out
    assert len((runs/check.HISTORY).read_text(encoding='utf-8').splitlines())==4


def test_progress():
    """The live line reads pytest's count-style output: full lines give done and total, the open line adds its marks, F and E count as failed."""
    full='.'*70+'F.'
    assert check.progress('')==(0,None,0) and check.progress('....s')==(5,None,0)
    assert check.progress(f'{full} [ 72/326]\n..E.')==(76,326,2)
    done=f'{full} [ 72/326]\n'+'.'*254+' [326/326]\n\n=================================== FAILURES ===\nF. E\n'
    assert check.progress(done)==(326,326,1)
    line=check.show_line('engine',f'{full} [ 72/326]\n...',check.time.monotonic()-130)
    assert line=='  engine: 75/326 tests (23%), 1 failed, 2:10 elapsed'


def test_check_refusals(tmp_path,monkeypatch):
    """Unknown lanes, low memory and an open engine run refuse before any test runs."""
    monkeypatch.setattr(check.run_tests,'free_gib',lambda:40.0);monkeypatch.setattr(check.run_tests,'open_engine_runs',lambda:[])
    with pytest.raises(SystemExit,match='lanes must come from'): check.main(['--lanes','nope'],runs=tmp_path)
    monkeypatch.setattr(check.run_tests,'free_gib',lambda:2.0)
    with pytest.raises(SystemExit,match='GiB free host memory'): check.main(['--lanes','tools'],runs=tmp_path)
    monkeypatch.setattr(check.run_tests,'free_gib',lambda:40.0);monkeypatch.setattr(check.run_tests,'open_engine_runs',lambda:['run-x'])
    with pytest.raises(SystemExit,match='engine run is open'): check.main(['--lanes','tools'],runs=tmp_path)
    lanes=check.lane_files();assert set(lanes)=={'engine','product','harness','tools'}
    assert all((check.ROOT/f).is_file() for _,files in lanes.values() for f in files) and 'tests/test_engine_french.py' not in lanes['product'][1]
