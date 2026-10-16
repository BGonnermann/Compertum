"""The owner approved 21 GiB backups under the unchanged 50 GiB total."""
from pathlib import Path
import pytest
from compertum.config import load_config, ConfigError

ROOT=Path(__file__).resolve().parents[1]


def test_backup_amendment_preserves_all_other_storage_limits():
    from compertum.storage import CAPS
    value=load_config(ROOT/'config/default.toml',ROOT)
    assert dict(value.storage_categories)==dict(data=15*1024**3,models=5*1024**3,
        scratch=10*1024**3,records=5*1024**3,backups=21*1024**3)
    assert value.storage_categories==CAPS
    assert value.storage_total_bytes==50*1024**3
    assert value.execution_reserve_bytes==1024**3
    assert value.storage_policy['minimum_free_bytes']==50*1024**3
    assert value.storage_policy['minimum_unused_reserve_bytes']==256*1024**2


def test_backup_config_cannot_raise_the_approved_ceiling(tmp_path):
    path=tmp_path/'config.toml'
    path.write_text((ROOT/'config/default.toml').read_text().replace(
        'backups_bytes = 22548578304','backups_bytes = 22548578305'))
    with pytest.raises(ConfigError,match='FIXED_M0_SETTING'):load_config(path,tmp_path)
