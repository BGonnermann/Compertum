"""tools/run_tests.py (owner decision, 25 October 2026): working files of a complete passing job are removed; anything else is kept.

Product lane; standard library only. The end-to-end cases run real pytest jobs inside the test's own temporary folder.
"""
import importlib.util
import json
import os
from pathlib import Path
import stat
import pytest

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('run_tests_tool',PROJECT/'tools'/'run_tests.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


@pytest.mark.parametrize('code,text,expected',[
    (0,'....\n12 passed, 1 skipped in 3.21s\n',True),
    (0,'==================== 160 passed in 141.94s (0:02:21) ====================\n',True),
    (1,'1 failed, 11 passed in 2.00s\n',False),
    (0,'1 failed, 11 passed in 2.00s\n',False),  # never trust the exit code alone
    (1,'3 passed, 2 errors in 1.0s\n',False),
    (5,'no tests ran in 0.10s\n',False),
    (0,'no summary at all\n',False),
    (2,'!!! Interrupted: 1 error during collection !!!\n1 error in 0.74s\n',False),
    (0,'5 skipped in 0.2s\n',False),  # nothing passed
])
def test_only_a_complete_passing_job_counts_as_passed(code,text,expected):
    assert tool.passed(code,text) is expected


def build_tree(tmp):
    """Nested folders, files, a read-only file, and links to a folder and to a file inside the tree (like pytest's 'current' links)."""
    (tmp/'a'/'b').mkdir(parents=True);(tmp/'c').mkdir()
    (tmp/'a'/'one.txt').write_text('1');(tmp/'a'/'b'/'two.txt').write_text('22');(tmp/'c'/'three.txt').write_text('333')
    readonly=tmp/'c'/'ro.txt';readonly.write_text('x');os.chmod(readonly,stat.S_IREAD)
    os.symlink(tmp/'a',tmp/'acurrent',target_is_directory=True);os.symlink(tmp/'c'/'three.txt',tmp/'three-link.txt')


def job_with_tree(tmp_path):
    job=tmp_path/'job';(job/'tmp').mkdir(parents=True);build_tree(job/'tmp');(job/'output.txt').write_text('kept')
    return job


def test_a_passing_job_loses_only_its_working_files_and_links_are_not_followed(tmp_path):
    job=job_with_tree(tmp_path)
    found=tool.inventory(job/'tmp')
    assert found=={'files':4,'dirs':3,'links':2,'bytes':7,'links_outside':[]}
    record=tool.clean(job,0,'7 passed in 1.0s\n')
    assert record['passed'] and record['removed'] and record['before']=={'files':4,'dirs':3,'links':2,'bytes':7}
    assert not (job/'tmp').exists() and (job/'output.txt').read_text()=='kept' and job.is_dir()


def test_a_failed_job_keeps_everything(tmp_path):
    job=job_with_tree(tmp_path)
    record=tool.clean(job,1,'1 failed, 6 passed in 1.0s\n')
    assert not record['passed'] and not record['removed'] and 'evidence' in record['reason']
    assert tool.inventory(job/'tmp')['files']==4


def test_a_link_to_outside_stops_the_cleanup_and_its_target_is_untouched(tmp_path):
    job=job_with_tree(tmp_path);outside=tmp_path/'outside';outside.mkdir();(outside/'keep.txt').write_text('precious')
    os.symlink(outside,job/'tmp'/'escape',target_is_directory=True)
    record=tool.clean(job,0,'7 passed in 1.0s\n')
    assert not record['removed'] and 'outside' in record['reason'] and record['links_outside']==[str(job/'tmp'/'escape')]
    assert (outside/'keep.txt').read_text()=='precious' and (job/'tmp'/'a'/'one.txt').exists()


def test_removing_a_tree_deletes_a_link_not_its_target(tmp_path):
    target=tmp_path/'target';target.mkdir();(target/'keep.txt').write_text('k')
    tree=tmp_path/'tree';tree.mkdir();os.symlink(target,tree/'link',target_is_directory=True)
    tool.remove_tree(tree)
    assert not tree.exists() and (target/'keep.txt').read_text()=='k'


def test_names_and_parents_are_checked(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'TEST_RUNS',tmp_path)
    for bad in ('../x','a b','','x'*90):
        with pytest.raises(SystemExit,match='--name'): tool.job_folder(bad,None)
    with pytest.raises(SystemExit,match='--under'): tool.job_folder('ok','missing-folder')
    (tmp_path/'capped').mkdir()
    assert tool.job_folder('ok','capped').parent==tmp_path/'capped'


def test_refusals_before_any_test_runs(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'TEST_RUNS',tmp_path)
    monkeypatch.setattr(tool,'free_gib',lambda:6.0)
    with pytest.raises(SystemExit,match='under the 8 GiB floor'): tool.main(['--name','x','--','tests/test_x.py'])
    monkeypatch.setattr(tool,'free_gib',lambda:40.0);monkeypatch.setattr(tool,'open_engine_runs',lambda:['run-20261025-0123abcd'])
    with pytest.raises(SystemExit,match='engine run open'): tool.main(['--name','x','--','tests/test_x.py'])
    # During an open run, --allow-during-run admits only whole files known to be sandbox-free (26 October 2026).
    with pytest.raises(SystemExit,match='may use the sandbox profile: tests/test_engine_bench.py'):
        tool.main(['--name','x','--allow-during-run','--','tests/test_engine_preflight.py','tests/test_engine_bench.py'])
    with pytest.raises(SystemExit,match='may use the sandbox profile: tests'): tool.main(['--name','x','--allow-during-run','--','tests'])
    assert tool.sandbox_files(['tests/test_engine_preflight.py','tests\\test_engine_lessons.py','tests/test_engine_roles.py::test_x','-q'])==[]
    monkeypatch.setattr(tool,'open_engine_runs',lambda:[])
    with pytest.raises(SystemExit,match='sets --basetemp itself'): tool.main(['--name','x','--','--basetemp','y','tests/test_x.py'])
    with pytest.raises(SystemExit,match='give the test files'): tool.main(['--name','x'])
    assert list(tmp_path.iterdir())==[]  # no job folder was made


def test_open_engine_runs_reads_the_ledger_read_only(tmp_path):
    assert tool.open_engine_runs(tmp_path)==[]  # no store
    import sqlite3
    (tmp_path/'state').mkdir();db=sqlite3.connect(tmp_path/'state'/'research.sqlite')
    db.execute('CREATE TABLE engine_bounded_runs(row_id TEXT,run_id TEXT,phase TEXT,recorded_at TEXT,record TEXT)')
    for run,phase in (('run-a','START'),('run-a','END'),('run-b','START')): db.execute('INSERT INTO engine_bounded_runs VALUES(?,?,?,?,?)',(run+phase,run,phase,'',json.dumps({'run_id':run,'phase':phase})))
    db.commit();db.close()
    assert tool.open_engine_runs(tmp_path)==['run-b']


@pytest.mark.parametrize('body,exit_code,removed',[('def test_ok(tmp_path):\n    (tmp_path/"f.txt").write_text("x")\n',0,True),
                                                   ('def test_bad(tmp_path):\n    (tmp_path/"f.txt").write_text("x")\n    assert False\n',1,False)])
def test_end_to_end_job(tmp_path,monkeypatch,capsys,body,exit_code,removed):
    root=tmp_path/'project';(root/'.cache'/'test-runs').mkdir(parents=True)
    monkeypatch.setattr(tool,'ROOT',root);monkeypatch.setattr(tool,'TEST_RUNS',root/'.cache'/'test-runs')
    monkeypatch.setattr(tool,'open_engine_runs',lambda:[]);monkeypatch.setattr(tool,'free_gib',lambda:40.0)
    test=root/'test_sample.py';test.write_text(body,encoding='utf-8')
    assert tool.main(['--name','sample','--',str(test),'-q'])==exit_code
    job=next((root/'.cache'/'test-runs').iterdir())
    record=json.loads((job/'retention.json').read_text(encoding='utf-8'))
    assert record['removed'] is removed and (job/'tmp').exists() is not removed and record['exit_code']==exit_code
    assert (job/'output.txt').exists() and record['job']==str(job.relative_to(root)) and len(record['output_sha256'])==64
    assert ('working files removed' if removed else 'working files kept as evidence') in capsys.readouterr().out
