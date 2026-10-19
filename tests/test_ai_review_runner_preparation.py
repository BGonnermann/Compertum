"""Draft helper checks. Storage admission must pass before execution."""
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def runner():
    spec = importlib.util.spec_from_file_location(
        'review_test_runner', ROOT/'tools/run_ai_review_tests.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_test_folder_is_preserved(tmp_path):
    parent = tmp_path/'.cache/test-runs/m5-local-economics-20261017-01'
    old = parent/'ai-review-tests01'
    old.mkdir(parents=True)
    evidence = old/'keep.txt'
    evidence.write_bytes(b'Preserve failed evidence.')
    with pytest.raises(FileExistsError):
        runner().fresh_test_folder(tmp_path, 'ai-review-tests01')
    assert evidence.read_bytes() == b'Preserve failed evidence.'


def test_new_folder_is_exclusive_and_pytest_leaf_is_absent(tmp_path):
    parent = tmp_path/'.cache/test-runs/m5-local-economics-20261017-01'
    parent.mkdir(parents=True)
    path = runner().fresh_test_folder(tmp_path, 'ai-review-tests01')
    assert path == parent/'ai-review-tests01/pytest'
    assert path.parent.is_dir() and not path.exists()
    with pytest.raises(FileExistsError):
        runner().fresh_test_folder(tmp_path, 'ai-review-tests01')


@pytest.mark.parametrize('label', ['../outside', 'ai-review-tests04', ''])
def test_unknown_folder_label_is_refused(tmp_path, label):
    with pytest.raises(ValueError, match='TEST_LABEL_DENIED'):
        runner().fresh_test_folder(tmp_path, label)
