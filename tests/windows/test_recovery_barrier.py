"""Actual separate store owners, shared barrier and owner-death admission check."""
import os
import pytest
from test_recovery import invoke
from pathlib import Path
pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')

def test_native_three_owner_barrier_and_dead_owner_blocks_admission(tmp_path,request):
    root=Path(request.config.getoption('--m0-managed-project') or tmp_path)
    assert root.resolve().is_relative_to((Path(__file__).parents[2]/'.cache/test-runs').resolve())
    root.mkdir(parents=True,exist_ok=True)
    invoke(root,'prepare')
    result=invoke(root,'managed_verification')
    assert result['status']=='VERIFIED'
    assert result['detection_seconds']<15
    assert result['dead_process_exit']!=0
    assert len(result['writers'])==4
