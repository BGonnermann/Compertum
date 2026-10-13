"""An unavailable wheel must never trigger a source build or new environment."""

import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path


def test_incompatible_wheel_blocks_without_environment_or_lock_change():
    project = Path(__file__).resolve().parents[1]
    parent = project / ".cache/test-runs"
    assert not parent.is_symlink() and not parent.parent.is_symlink()
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / ("wheel-preflight-" + uuid.uuid4().hex)
    root.mkdir()
    wheels = root / "wheels"
    wheels.mkdir()
    # The owned fixture advertises a different interpreter/platform. Its code
    # must never be imported or built; uv should reject it during resolution.
    incompatible = "cp39-cp39-win_amd64" if os.name != "nt" else "cp39-cp39-manylinux_2_17_x86_64"
    wheel = wheels / f"compertum_incompatible_fixture-0.0.1-{incompatible}.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("compertum_incompatible_fixture-0.0.1.dist-info/METADATA",
                         "Metadata-Version: 2.1\nName: compertum-incompatible-fixture\nVersion: 0.0.1\n")
        archive.writestr("compertum_incompatible_fixture-0.0.1.dist-info/WHEEL",
                         f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {incompatible}\n")
    requirements = root / "requirements.in"
    requirements.write_text("compertum-incompatible-fixture==0.0.1\n")
    lock_before = (project / "uv.lock").read_bytes()
    uv = shutil.which("uv")
    assert uv is not None, "uv is a required setup capability"
    result = subprocess.run(
        [uv, "--no-config", "pip", "compile", str(requirements), "--no-build",
         "--no-index", "--find-links", str(wheels), "--python", sys.executable,
         "--no-managed-python", "--no-python-downloads", "--cache-dir", str(root / "uv-cache")],
        cwd=root, capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode != 0
    assert "No solution found" in result.stderr
    assert "compatible" in result.stderr or "wheel" in result.stderr
    assert not (root / ".venv").exists()
    assert (project / "uv.lock").read_bytes() == lock_before
    (root / "blocked-receipt.txt").write_text("BLOCKED_INCOMPATIBLE_WHEEL\n" + result.stderr)
