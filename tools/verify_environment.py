"""Verify locked dependency imports and installed wheel tags; stdout only."""

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import sys
import tomllib
from email.parser import Parser
from pathlib import Path
from urllib.parse import urlparse

from packaging.utils import canonicalize_name, parse_wheel_filename


MODULES = {
    "numpy": "numpy", "pandas": "pandas", "scipy": "scipy",
    "scikit-learn": "sklearn", "sympy": "sympy", "pyarrow": "pyarrow",
    "httpx": "httpx", "jsonschema": "jsonschema",
    "exchange-calendars": "exchange_calendars", "tzdata": "tzdata",
    "pytest": "pytest", "setuptools": "setuptools", "wheel": "wheel",
    "compertum": "compertum",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if sys.prefix == sys.base_prefix:
        print(json.dumps({"status": "BLOCKED_NOT_ISOLATED_ENVIRONMENT"}))
        return 3
    root = args.project_root.resolve()
    lock_bytes = (root / "uv.lock").read_bytes()
    lock = tomllib.loads(lock_bytes.decode())
    packages = lock["package"]
    versions = {}
    wheel_identities = {}
    for distribution in importlib.metadata.distributions():
        name = canonicalize_name(distribution.metadata["Name"])
        version = distribution.version
        matched = [p for p in packages if p["name"] == name and p["version"] == version]
        if len(matched) != 1:
            raise ValueError(f"Installed distribution does not match lock: {name}")
        versions[name] = version
        if name == "compertum":
            continue
        wheel_metadata = distribution.read_text("WHEEL")
        if wheel_metadata is None:
            raise ValueError(f"Missing installed wheel identity: {name}")
        tags = set(Parser().parsestr(wheel_metadata).get_all("Tag", []))
        identities = []
        for wheel in matched[0].get("wheels", []):
            filename = Path(urlparse(wheel["url"]).path).name
            _, _, _, wheel_tags = parse_wheel_filename(filename)
            if {str(tag) for tag in wheel_tags} == tags:
                identities.append({"filename": filename, "sha256": wheel["hash"].removeprefix("sha256:")})
        if not identities:
            raise ValueError(f"Installed wheel tags do not match lock: {name}")
        # These are lock identities matched to installed tags; uv verified the
        # download hashes. This helper does not independently re-download bytes.
        wheel_identities[name] = sorted(identities, key=lambda row: row["filename"])
    for distribution, module in MODULES.items():
        importlib.import_module(module)
        if distribution not in versions:
            raise ValueError(f"Required distribution missing: {distribution}")
    print(json.dumps({
        "status": "VERIFIED_CLOUD_IMPORTS", "m0_status": "INCOMPLETE",
        "python": sys.version.split()[0], "isolated_environment": True,
        "lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "versions": dict(sorted(versions.items())),
        "wheel_identities": dict(sorted(wheel_identities.items())),
        "wheel_evidence": "LOCK_HASHES_AND_INSTALLED_TAGS_WITH_UV_HASH_VERIFICATION",
        "native_validation": "UNVERIFIED",
    }, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
