"""Explicit, bounded ownership fixtures. This cannot grant M0 acceptance.

Default invocation is observational and writes nothing. --run-fixtures runs
trusted tests on Windows only, within unique project-local fixture namespaces.
No dependencies/interpreter are installed, providers called, or OS settings changed.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-fixtures", action="store_true")
    p.add_argument("--suite", choices=("ownership", "ipc", "all"), default="ownership")
    a = p.parse_args()
    report = {"status": "NATIVE_FIXTURES_NOT_RUN", "fixture_run": False,
              "native_ownership": "UNVERIFIED", "native_task1": "UNVERIFIED",
              "native_task3": "UNVERIFIED", "m0": "INCOMPLETE",
              "native_ipc": "UNVERIFIED", "named_pipe": "NATIVE_UNVERIFIED",
              "worker_bootstrap": "UNIMPLEMENTED", "durable_dispatch": "DISABLED", "suite": a.suite,
              "python": sys.version.split()[0], "spending_usd": "0.00"}
    if os.name != "nt" or sys.platform != "win32":
        report["status"] = "NATIVE_WINDOWS_UNAVAILABLE"
        print(json.dumps(report, sort_keys=True)); return 3
    if not a.run_fixtures:
        print(json.dumps(report, sort_keys=True)); return 3
    root = Path(__file__).resolve().parents[1]
    # All evidence is inside the source workspace and never an arbitrary output path.
    out = root / ".cache/test-runs" / ("native-verification-" + str(uuid.uuid4()))
    current = root
    for part in (".cache", "test-runs"):
        current = current / part
        if current.exists():
            info = current.lstat()
            if current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                report["status"] = "REPARSE_DENIED"; print(json.dumps(report)); return 3
        current.mkdir(exist_ok=True)
    out.mkdir()
    junit = out / (a.suite + ".xml")
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "PATH"}}
    env["PYTHONPATH"] = str(root / "src"); env["PYTHONDONTWRITEBYTECODE"] = "1"
    report["fixture_run"] = True
    report["evidence_directory"] = str(out.relative_to(root))
    files = {"ownership": ["tests/windows/test_ownership.py"], "ipc": ["tests/windows/test_ipc.py"],
             "all": ["tests/windows/test_ownership.py", "tests/windows/test_ipc.py"]}[a.suite]
    minimum = {"ownership": 9, "ipc": 11, "all": 20}[a.suite]
    try:
        result = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", *files,
                                 "--junitxml", str(junit)], cwd=root, env=env,
                                text=True, capture_output=True, timeout=120)
        # Fixture helpers carry a separate 30-second exit bound. This is not
        # Task 5's verified whole-child-tree cancellation or native Job limit.
        # capture_output buffers first: 1 MiB bounds retained evidence only,
        # not subprocess output allocation or memory during capture.
        log = result.stdout + result.stderr
        if len(log.encode("utf-8")) > 1024 * 1024:
            report["status"] = "OUTPUT_BOUND_EXCEEDED"; return emit(report, out, 3)
        (out / "pytest.log").write_text(log, encoding="utf-8")
        report["pytest_exit"] = result.returncode
        totals = {k: 0 for k in ("tests", "failures", "errors", "skipped")}
        if junit.exists():
            for suite in ET.parse(junit).getroot().iter("testsuite"):
                for k in totals: totals[k] += int(suite.attrib.get(k, 0))
        report["counts"] = totals
        if result.returncode == 0 and totals["tests"] >= minimum and not any(totals[k] for k in ("failures", "errors", "skipped")):
            if a.suite in ("ownership", "all"): report["native_ownership"] = "FIXTURES_PASS"
            if a.suite in ("ipc", "all"): report["native_ipc"] = "INSPECTION_FIXTURES_PASS"
            report["status"] = a.suite.upper() + "_FIXTURES_PASS_M0_INCOMPLETE"
            return emit(report, out, 0)
        report["status"] = "NATIVE_FIXTURES_UNVERIFIED"
        return emit(report, out, 3)
    except (subprocess.TimeoutExpired, OSError, ET.ParseError, ValueError):
        report["status"] = "NATIVE_VERIFICATION_UNVERIFIED"
        return emit(report, out, 3)


def emit(report, out, code):
    (out / "result.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True)); return code


if __name__ == "__main__": raise SystemExit(main())
