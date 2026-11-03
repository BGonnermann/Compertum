"""Read-only cards for every kind of run: harness runs, engine runs, test jobs, check lanes and library sweeps.

Owner, 3 November 2026: "can /watch follow any run regardless if its internal or not?" ("yes").
Nothing here writes a file or a row. Vault data is never listed or read.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from .engine_watch import NEWEST, QUIET_SECONDS, RUN_ID, _connect, _summary, duration, engine_card
from .runs import RunError, read_card

JOB_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*-([0-9]{8}-[0-9]{6})")
JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}(?:/[A-Za-z0-9][A-Za-z0-9_.-]{0,80})?")
SWEEP_ID = re.compile(r"library(?:-multi)?-[0-9]{8}-[0-9a-f]{8}")
PARENT_DAYS = 7
SWEEP_QUIET = 10 * 60
TAIL = 1024 * 1024
COUNT = re.compile(r"\[\s*(\d+)/(\d+)\]\s*$")
PERCENT = re.compile(r"\[\s*(\d+)%\]\s*$")
RESULTS = re.compile(r"^([.FEsxX]+)(?:\s+\[[^\]]*\])?\s*$")
SUMMARY = re.compile(r"^=*\s*(\d+ (?:passed|failed|error|errors|skipped).*?)\s*=*$")
_CHILDREN: dict = {}


def _tests(root: Path):
    return root / ".cache" / "test-runs"


def _read(path: Path, limit=TAIL):
    try:
        with open(path, "rb") as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return None


def _json(path: Path):
    text = _read(path)
    try:
        value = json.loads(text) if text else None
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _job_folders(root: Path):
    """Job folders under .cache/test-runs, newest first by the time in their names. Other folders changed in the
    last 7 days are opened for jobs one level down (run_tests --under). A new child folder updates its parent's time."""
    base = _tests(root)
    found, recent = [], time.time() - PARENT_DAYS * 86400
    try:
        entries = list(os.scandir(base))
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        named = JOB_NAME.fullmatch(entry.name)
        if named:
            found.append((named.group(1), entry.name))
            continue
        try:
            changed = entry.stat(follow_symlinks=False).st_mtime
            if changed < recent:
                continue
            cached = _CHILDREN.get(entry.path)
            if cached is None or cached[0] != changed:
                cached = changed, [(named.group(1), f"{entry.name}/{child.name}") for child in os.scandir(entry.path)
                                   if (named := JOB_NAME.fullmatch(child.name)) and child.is_dir(follow_symlinks=False)]
                _CHILDREN[entry.path] = cached
        except OSError:
            continue
        found.extend(cached[1])
    return [identity for _, identity in sorted(found, reverse=True)]


def _open_jobs(root: Path, folders, hours=24):
    """Job folders from the last 24 hours that have output but no result record yet."""
    base, since, found = _tests(root), time.time() - hours * 3600, []
    for identity in folders:
        started = _started(identity)
        if started is None or started < since:
            break
        folder = base / identity
        if (folder / "output.txt").is_file() and not (folder / "retention.json").exists() and not (folder / "failed.json").exists():
            found.append(identity)
    return found


def _started(identity):
    try:
        return datetime.strptime(JOB_NAME.fullmatch(identity.rsplit("/", 1)[-1]).group(1), "%Y%m%d-%H%M%S").timestamp()
    except (AttributeError, ValueError):
        return None


def _progress(text):
    done, total, percent = 0, 0, None
    failed = 0
    for line in text.splitlines():
        line = line.rstrip()
        counted = COUNT.search(line)
        if counted:
            done, total = int(counted.group(1)), int(counted.group(2))
        shared = PERCENT.search(line)
        if shared:
            percent = int(shared.group(1))
        results = RESULTS.match(line)
        if results:
            failed += sum(results.group(1).count(mark) for mark in "FE")
    if total:
        return f"{done}/{total} tests ({100 * done // total}%)", failed
    return (f"{percent}%" if percent is not None else None), failed


def _summary_line(text):
    lines = [SUMMARY.match(line.strip()) for line in text.splitlines()]
    lines = [match.group(1) for match in lines if match]
    return lines[-1] if lines else None


def _history(root: Path, name):
    text = _read(_tests(root) / "check-history.jsonl", 256 * 1024) or ""
    for line in reversed(text.splitlines()):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("run") == name:
            return row
    return None


def test_card(root: Path, identity: str, tail=10):
    """A test job of tools/run_tests.py or a lane of tools/check.py. A passed lane's folder is removed, so its card
    comes from check-history.jsonl."""
    if not JOB_ID.fullmatch(identity) or not JOB_NAME.fullmatch(identity.rsplit("/", 1)[-1]):
        raise RunError("the run was not found")
    base = _tests(root)
    folder = base / identity
    if folder.is_symlink() or (folder.parent != base and folder.parent.is_symlink()):
        raise RunError("the run was not found")
    text = _read(folder / "output.txt")
    if text is None:
        row = _history(root, identity) if "/" not in identity else None
        if row is None:
            raise RunError("the run was not found")
        seconds = row.get("seconds")
        return {"run": identity, "type": "check lane", "status": "COMPLETED" if row.get("passed") else "FAILED",
                "result": row.get("summary") or "unknown",
                "elapsed": duration(seconds) if isinstance(seconds, (int, float)) else "unknown",
                "folder": "removed after the pass" if row.get("passed") else f".cache/test-runs/{identity}"}
    kind = "test job" if text.startswith("command: ") else "check lane"
    record = _json(folder / "retention.json") or _json(folder / "failed.json")
    progress, failed = _progress(text)
    started = _started(identity)
    if record is not None:
        status = "COMPLETED" if record.get("passed") else "FAILED"
        seconds = record.get("elapsed_seconds", record.get("seconds"))
        result = record.get("summary") or _summary_line(text) or "unknown"
    else:
        times = []
        for path in (folder / "output.txt", folder / "tmp"):
            try:
                times.append(path.stat().st_mtime)
            except OSError:
                pass
        quiet = time.time() - max(times or [started or time.time()])
        status = "RUNNING" if quiet < QUIET_SECONDS else f"NO OUTPUT FOR {int(quiet // 60)} MINUTES"
        seconds = time.time() - started if started else None
        result = _summary_line(text) or "not finished"
        if not progress:
            try:
                progress = f"{sum(1 for entry in os.scandir(folder / 'tmp') if entry.is_dir(follow_symlinks=False))} tmp folders so far"
            except OSError:
                pass
    card: dict = {"run": identity, "type": kind, "status": status}
    if progress:
        card["progress"] = progress
    card.update({"failed": failed, "result": result,
                 "elapsed": duration(seconds) if isinstance(seconds, (int, float)) else "unknown",
                 "folder": f".cache/test-runs/{identity}"})
    card["log_tail"] = "\n".join(line for line in text.splitlines()[-tail:])
    return card


def test_jobs(root: Path, limit=6):
    """Summaries of the open test jobs and check lanes, then the newest finished ones."""
    rows, folders = [], _job_folders(root)
    for identity in dict.fromkeys(_open_jobs(root, folders) + folders):
        if len(rows) == limit:
            break
        if not (_tests(root) / identity / "output.txt").is_file():
            continue
        try:
            rows.append(test_card(root, identity, tail=0))
        except RunError:
            continue
    return rows


def _sweep_status(root: Path, run_id, recorded_at, now):
    if (root / "state" / "engine" / "library" / f"{run_id}.json").is_file():
        return "COMPLETED"
    try:
        quiet = now - datetime.fromisoformat(recorded_at).timestamp()
    except (TypeError, ValueError):
        return "UNKNOWN"
    return "RUNNING" if quiet < SWEEP_QUIET else f"NO REPORT AFTER {int(quiet // 60)} MINUTES"


def _sweep_rows(root: Path, limit, run_id=None):
    con = _connect(root)
    if con is None:
        return []
    try:
        if not con.execute("select 1 from sqlite_master where type = 'table' and name = 'engine_trials'").fetchone():
            return []
        if run_id is None:
            rows = con.execute("select source, count, recorded_at, record from engine_trials where source like 'library%:%' "
                               "order by recorded_at desc limit ?", (limit,)).fetchall()
        else:
            rows = con.execute("select source, count, recorded_at, record from engine_trials where source in (?, ?)",
                               (f"library:{run_id}", f"library-multi:{run_id}")).fetchall()
    except sqlite3.Error:
        raise RunError("the research store cannot be read now") from None
    finally:
        con.close()
    out = []
    for source, count, recorded_at, record in rows:
        identity = source.split(":", 1)[1]
        if not SWEEP_ID.fullmatch(identity):
            continue
        try:
            evidence = (json.loads(record) or {}).get("evidence") or {}
        except (TypeError, ValueError, AttributeError):
            evidence = {}
        out.append((identity, count, recorded_at, evidence if isinstance(evidence, dict) else {}))
    return out


def sweeps(root: Path, limit=3):
    """Summaries of the newest library sweeps, from their trial rows. Newest first."""
    now = time.time()
    return [{"run": identity, "type": "library sweep", "status": _sweep_status(root, identity, recorded_at, now),
             "trials": count, "recorded_at": recorded_at} for identity, count, recorded_at, _ in _sweep_rows(root, limit)]


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sweep_card(root: Path, identity: str, best=6):
    if not SWEEP_ID.fullmatch(identity):
        raise RunError("the run was not found")
    rows = _sweep_rows(root, 1, identity)
    if not rows:
        raise RunError("the run was not found")
    _, count, recorded_at, evidence = rows[0]
    card = {"run": identity, "type": "library sweep", "status": _sweep_status(root, identity, recorded_at, time.time()),
            "note": str(evidence.get("note") or ""), "trials_recorded": count, "recorded_at": recorded_at}
    report = _json(root / "state" / "engine" / "library" / f"{identity}.json") if card["status"] == "COMPLETED" else None
    if report is None:
        card["result"] = "the report is written when the sweep ends" if card["status"] == "RUNNING" else "no report"
        return card
    results = [row for row in report.get("rows") or [] if isinstance(row, dict)]
    card["total_trials"] = report.get("total_trials", "unknown")
    card["gates"] = f"{sum(row.get('gate') == 'PASS' for row in results)} of {len(results)} PASS"
    ranked = sorted(results, key=lambda row: _number(row.get("deflated_sharpe")) or float("-inf"), reverse=True)
    lines = []
    for row in ranked[:best]:
        value = _number(row.get("deflated_sharpe"))
        where = row.get("universe") or row.get("symbol") or "?"
        lines.append(f"{where} {row.get('family') or '?'} · {row.get('gate') or '?'}"
                     + (f" · deflated {value:.2f}" if value is not None else ""))
    card["best_rows"] = lines or ["no rows"]
    return card


def _epoch(text):
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()


def _engine_heads(root: Path, limit=4):
    con = _connect(root)
    if con is None:
        return []
    try:
        rows = con.execute("select run_id, phase, record from engine_bounded_runs where run_id in (select run_id from "
                           "engine_bounded_runs where phase = 'START' order by recorded_at desc limit ?)", (limit,)).fetchall()
        starts, ends = {}, set()
        for run_id, phase, record in rows:
            if phase == "START":
                starts[run_id] = json.loads(record)
            else:
                ends.add(run_id)
        now = datetime.now(timezone.utc)
        heads = []
        for run_id, start in starts.items():
            running = run_id not in ends and _summary(con, start, None, now)[0]["status"] == "RUNNING"
            heads.append((running, _epoch(start.get("recorded_at") or start.get("started_at")) or 0.0, run_id))
    except (sqlite3.Error, ValueError, TypeError):
        raise RunError("the research store cannot be read now") from None
    finally:
        con.close()
    return heads


def _harness_heads(root: Path, limit=3):
    folder = root / "state" / "harness" / "runs"
    heads = []
    try:
        records = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]
    except OSError:
        return []
    for path in records:
        meta = _json(path)
        if not meta or meta.get("dismissed") or meta.get("kind") != "test":
            continue
        try:
            running = read_card(root, path.stem)["status"] == "RUNNING"
        except RunError:
            continue
        heads.append((running, float(meta.get("started_wall") or 0.0), path.stem))
    return heads


def newest(root: Path):
    """The run to follow: the newest running run of any kind, else the newest run. None before the first run.
    Harness practice, GEPA and bench runs appear through their engine run."""
    heads = _engine_heads(root) + _harness_heads(root)
    folders = _job_folders(root)
    for identity in dict.fromkeys(_open_jobs(root, folders) + folders[:2]):
        try:
            card = test_card(root, identity, tail=0)
        except RunError:
            continue
        heads.append((card["status"] == "RUNNING", _started(identity) or 0.0, identity))
    now = time.time()
    for identity, _, recorded_at, _ in _sweep_rows(root, 2):
        heads.append((_sweep_status(root, identity, recorded_at, now) == "RUNNING", _epoch(recorded_at) or 0.0, identity))
    if not heads:
        return None
    return max(heads, key=lambda head: (head[0], head[1]))[2]


def watch_card(root: Path, identity: str):
    """The card for any run ID, or for the run that newest() names."""
    if identity == NEWEST:
        found = newest(root)
        if found is None:
            return {"status": "WAITING", "note": "no run yet; the next run shows here when it starts"}
        identity = found
    if JOB_ID.fullmatch(identity) and "/" not in identity and (root / "state" / "harness" / "runs" / f"{identity}.json").is_file():
        return read_card(root, identity)
    if RUN_ID.fullmatch(identity) or (identity.startswith("run-") and not JOB_NAME.fullmatch(identity)):
        return engine_card(root, identity)
    if SWEEP_ID.fullmatch(identity):
        return sweep_card(root, identity)
    return test_card(root, identity)
