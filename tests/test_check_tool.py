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
