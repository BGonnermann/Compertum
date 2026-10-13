import importlib
import pytest
from compertum.runtime.owners import acquire_owner,resolve_project

def api():
    try:return importlib.import_module('compertum.consumption')
    except ImportError:pytest.fail('consumption guard missing')

def test_consume_once_and_missing_guard_is_not_unused(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'evaluation')
    try:
        m.create_guard(owner)
        m.consume_once(owner,'synthetic-A','EVAL-A',{'protocol':'fixed'})
        evidence=m.verify_consumption_guard(owner.project)
        assert evidence['verified'] and evidence['consumed']['synthetic-A']=='EVAL-A'
        with pytest.raises(ValueError):m.consume_once(owner,'synthetic-A','EVAL-B',{})
        head=tmp_path/'state/evaluation-consumption/head.json';head.rename(head.with_suffix('.withheld'))
        assert not m.verify_consumption_guard(owner.project)['verified']
        with pytest.raises(ValueError):m.consume_once(owner,'synthetic-B','EVAL-B',{})
    finally:owner.close()
