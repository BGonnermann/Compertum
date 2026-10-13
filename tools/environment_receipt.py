"""Non-secret observed inventory. No credentials or authenticated requests."""
import argparse
import ctypes
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def collect_environment(project_root: Path) -> dict:
    root = project_root.resolve()
    packages = {}
    for name, module in {"numpy":"numpy", "pandas":"pandas", "scipy":"scipy", "scikit-learn":"sklearn", "sympy":"sympy", "pyarrow":"pyarrow", "httpx":"httpx", "jsonschema":"jsonschema", "exchange-calendars":"exchange_calendars", "tzdata":"tzdata", "pytest":"pytest", "setuptools":"setuptools", "wheel":"wheel"}.items():
        try:
            importlib.import_module(module)
            packages[name] = {"version":importlib.metadata.version(name), "import":"VERIFIED_PASS"}
        except Exception as error:
            packages[name] = {"import":"UNVERIFIED", "error_type":type(error).__name__}
    documents = {}
    for name in ("Solo_Quant_System_Build_Preparation.md", "docs/BUILD_SPEC.md", "docs/M0_IMPLEMENTATION_PLAN.md", "uv.lock"):
        path = root / name
        if path.exists():
            documents[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    tools = {}
    for name, args in {"git":["--version"], "uv":["--version"], "nvidia-smi":["--query-gpu=name,driver_version,memory.total,memory.free", "--format=csv,noheader"]}.items():
        executable = shutil.which(name)
        if executable:
            result = subprocess.run([executable,*args],capture_output=True,text=True,timeout=10)
            tools[name] = {"exit_code":result.returncode,"observed":result.stdout.strip()[:2048]}
        else:
            tools[name] = {"status":"UNVERIFIED"}
    free = shutil.disk_usage(root)
    return {"schema_version":1, "at":datetime.now(timezone.utc).isoformat(), "python":{"version":platform.python_version(),"executable":sys.executable}, "os":platform.platform(), "packages":packages, "documents":documents, "tools":tools, "storage":{"free_bytes":free.free,"total_bytes":free.total}, "unknown":["subscription entitlement/quota","authenticated Alpaca access","Windows edition branding","DDR5 speed"], "new_spending":0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/m0/environment.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = (root / args.output).resolve()
    target.relative_to(root)
    payload = json.dumps(collect_environment(root),indent=2)
    if len(payload.encode()) > 1024*1024:
        raise ValueError("receipt capacity exceeded")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(payload,encoding="utf-8")
