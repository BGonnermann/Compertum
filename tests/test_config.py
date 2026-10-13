import importlib
from pathlib import Path
import pytest

ROOT=Path(__file__).parents[1]
def api():
    try: return importlib.import_module('compertum.config')
    except ImportError: pytest.fail('M0 configuration missing')

def test_config_cannot_enable_financial_commands(tmp_path):
    c=api()
    p=tmp_path/'bad.toml'; p.write_text('paper_enabled=true')
    with pytest.raises(ValueError): c.load_config(p,tmp_path)
    cfg=c.load_config(ROOT/'config/default.toml',ROOT)
    assert not cfg.paper_enabled
    assert cfg.capability('paper')=='CAPABILITY_UNAVAILABLE'

def test_config_cannot_raise_storage_or_worker_caps(tmp_path):
    c=api()
    p=tmp_path/'bad.toml'; p.write_text('storage_cap_gib=51')
    with pytest.raises(ValueError): c.load_config(p,tmp_path)

def test_lower_limits_cannot_be_silently_discarded(tmp_path):
    c=api();p=tmp_path/'lower.toml';p.write_text('cpu_threads=1')
    with pytest.raises(ValueError,match='NONDEFAULT_LIMIT_UNSUPPORTED'):c.load_config(p,tmp_path)
