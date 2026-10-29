import json
import os
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import clean_test_runs  # noqa: E402


def tree(root):
    runs=root/'.cache'/'test-runs'
    for name in ('engine-practice-20261029-aaaaaaaa','e8-full-product-03','m5-local-economics-20261017-01','other-job'):
        (runs/name/'job-001'/'deep').mkdir(parents=True);(runs/name/'job-001'/'deep'/'a.txt').write_text('x');(runs/name/'b.txt').write_text('yy')
    return runs


def go(root,folders=(),sandboxes=True,apply=False,**kw):
    options={'open_runs':[],'queued':0,'free':64.0,**kw}
    return clean_test_runs.run(root,list(folders),sandboxes,apply,**options)


def test_a_dry_run_reports_and_removes_nothing(tmp_path):
    runs=tree(tmp_path);record=go(tmp_path,['e8-full-product-03'])
    assert [t['folder'] for t in record['targets']]==['engine-practice-20261029-aaaaaaaa','e8-full-product-03'] and record['applied'] is False
    assert record['targets'][0]=={'folder':'engine-practice-20261029-aaaaaaaa','files':2,'dirs':2,'bytes':3}
    assert (runs/'e8-full-product-03'/'job-001'/'deep'/'a.txt').exists() and not (runs/'cleanup-records').exists()


def test_apply_empties_only_the_chosen_folders_and_keeps_them(tmp_path):
    runs=tree(tmp_path);record=go(tmp_path,['e8-full-product-03'],apply=True)
    for name in ('engine-practice-20261029-aaaaaaaa','e8-full-product-03'): assert (runs/name).is_dir() and not any((runs/name).iterdir())
    assert (runs/'other-job'/'job-001'/'deep'/'a.txt').exists() and (runs/'m5-local-economics-20261017-01'/'b.txt').exists()
    assert record['removed']=={'files':4,'dirs':4,'bytes':6} and all(t['removed'] for t in record['targets'])
    saved=list((runs/'cleanup-records').iterdir());assert len(saved)==1 and json.loads(saved[0].read_text())['removed']['files']==4


def test_refusals_come_before_any_removal(tmp_path):
    runs=tree(tmp_path)
    assert go(tmp_path,apply=True,open_runs=['run-20261029-0123abcd'])['refused']=='an engine run is open'
    assert 'below' in go(tmp_path,apply=True,free=2.0)['refused']
    for bad in ('m5-local-economics-20261017-01','../outside','missing'):
        with pytest.raises(SystemExit): go(tmp_path,[bad],apply=True)
    assert (runs/'engine-practice-20261029-aaaaaaaa'/'b.txt').exists()


def test_a_queued_candidate_keeps_every_engine_sandbox(tmp_path):
    runs=tree(tmp_path);record=go(tmp_path,apply=True,queued=1)
    assert record['targets']==[] and record['engine_sandboxes']=='skipped: the queue has events'
    assert (runs/'engine-practice-20261029-aaaaaaaa'/'b.txt').exists()


def test_a_link_out_of_the_folder_skips_that_folder(tmp_path):
    runs=tree(tmp_path);outside=tmp_path/'precious';outside.mkdir();(outside/'keep.txt').write_text('k')
    try: os.symlink(outside,runs/'e8-full-product-03'/'escape',target_is_directory=True)
    except OSError: pytest.skip('this account cannot create symbolic links')
    record=go(tmp_path,['e8-full-product-03'],sandboxes=False,apply=True)
    assert record['targets'][0]['skipped']=='a link points outside the folder' and (outside/'keep.txt').exists()
    assert (runs/'e8-full-product-03'/'b.txt').exists()
