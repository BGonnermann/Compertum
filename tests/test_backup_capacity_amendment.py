"""The owner approved 21 GiB backups (under the then 50 GiB total); on 24 October 2026 the owner set scratch 50 GiB and the project total 200 GiB."""
from pathlib import Path
import pytest
from compertum.config import load_config, ConfigError

ROOT=Path(__file__).resolve().parents[1]


def test_backup_amendment_preserves_all_other_storage_limits():
    from compertum.storage import CAPS
    value=load_config(ROOT/'config/default.toml',ROOT)
    assert dict(value.storage_categories)==dict(data=15*1024**3,models=5*1024**3,
        scratch=50*1024**3,records=5*1024**3,backups=21*1024**3)  # scratch 50 GiB: owner decision of 24 October 2026
    assert value.storage_categories==CAPS
    assert value.storage_total_bytes==200*1024**3  # owner decision of 24 October 2026; the 50 GiB free-space minimum below is unchanged
    assert value.execution_reserve_bytes==1024**3
    assert value.storage_policy['minimum_free_bytes']==50*1024**3
    assert value.storage_policy['minimum_unused_reserve_bytes']==256*1024**2


@pytest.mark.parametrize('retired',['5368709120','12884901888'])
def test_frozen_configs_with_retired_scratch_limits_still_load(tmp_path,retired):
    # 5 GiB until 16 October 2026, 12 GiB until 24 October 2026. Reading them rewrites no bytes and names the current ceiling.
    path=tmp_path/'config.toml'
    path.write_text((ROOT/'config/default.toml').read_text().replace('scratch_bytes = 53687091200','scratch_bytes = '+retired))
    assert load_config(path,tmp_path).storage_categories['scratch']==50*1024**3


def test_frozen_config_with_the_retired_50_gib_total_still_loads(tmp_path):
    # The project total was 50 GiB until 24 October 2026 (owner decision: 200 GiB).
    path=tmp_path/'config.toml'
    path.write_text((ROOT/'config/default.toml').read_text().replace('total_bytes = 214748364800','total_bytes = 53687091200'))
    assert load_config(path,tmp_path).storage_total_bytes==200*1024**3


def test_total_config_cannot_raise_the_approved_ceiling(tmp_path):
    path=tmp_path/'config.toml'
    path.write_text((ROOT/'config/default.toml').read_text().replace('total_bytes = 214748364800','total_bytes = 214748364801'))
    with pytest.raises(ConfigError,match='FIXED_M0_SETTING'):load_config(path,tmp_path)


def test_every_total_cap_guard_reads_the_one_configured_total():
    from compertum import storage,watchdog,recovery
    from compertum.config import _DEFAULTS
    assert storage.TOTAL_CAP==watchdog.TOTAL_CAP==recovery.TOTAL_CAP==_DEFAULTS['storage']['total_bytes']==200*1024**3


def test_scratch_config_cannot_raise_the_approved_ceiling(tmp_path):
    path=tmp_path/'config.toml'
    path.write_text((ROOT/'config/default.toml').read_text().replace('scratch_bytes = 53687091200','scratch_bytes = 53687091201'))
    with pytest.raises(ConfigError,match='FIXED_M0_SETTING'):load_config(path,tmp_path)


def test_backup_config_cannot_raise_the_approved_ceiling(tmp_path):
    path=tmp_path/'config.toml'
    path.write_text((ROOT/'config/default.toml').read_text().replace(
        'backups_bytes = 22548578304','backups_bytes = 22548578305'))
    with pytest.raises(ConfigError,match='FIXED_M0_SETTING'):load_config(path,tmp_path)
