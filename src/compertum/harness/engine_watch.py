"""Read-only progress of engine runs, including runs started outside the harness with tools\\practice.ps1."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .display import clock
from .runs import RunError

# A run with no END record and no new cycle for this long may have stopped without recording its end.
QUIET_SECONDS = 30 * 60


def _connect(root: Path):
    path = root / "state" / "research.sqlite"
    if not path.is_file():
        return None
    try:
        # Read-only, so watching can never change or lock out a running engine job.
        return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        raise RunError("the research store cannot be read now") from None


def duration(seconds):
    hours, rest = divmod(int(seconds), 3600)
    return f"{hours}:{clock(rest).zfill(5)}" if hours else clock(rest)


def _when(text):
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _summary(con, start, end, now):
    run_id = start["run_id"]
    limits = start.get("limits") or {}
    cycles = con.execute("select record from engine_cycles where phase = 'END' and json_extract(record, '$.run_id') = ? "
                         "order by cast(json_extract(record, '$.cycle_index') as integer)", (run_id,)).fetchall()
    cycles = [json.loads(row[0]) for row in cycles]
    latest = con.execute("select max(json_extract(record, '$.recorded_at')) from engine_cycles "
                         "where json_extract(record, '$.run_id') = ?", (run_id,)).fetchone()[0]
    started = _when(start.get("started_at") or start.get("recorded_at"))
    if end:
        status = f"ENDED ({end.get('reason') or 'unknown reason'})"
        elapsed = end.get("elapsed_seconds")
        requests = end.get("requests")
    else:
        quiet = (now - (_when(latest) or started or now)).total_seconds()
        status = "RUNNING" if quiet < QUIET_SECONDS else f"NO PROGRESS FOR {int(quiet // 60)} MINUTES"
        elapsed = (now - started).total_seconds() if started else None
        requests = cycles[-1].get("requests_after") if cycles else 0
    director = ((start.get("models") or {}).get("director") or {}).get("model", "")
    return {"run": run_id, "type": start.get("kind") or "engine", "model": director, "status": status,
            "cycles": f"{len(cycles)} of {limits.get('cycle_limit', '?')}",
            "requests": f"{requests} of {limits.get('request_limit', '?')}",
            "elapsed": duration(elapsed) if isinstance(elapsed, (int, float)) else "unknown",
            "hour_limit": limits.get("hour_limit") or "none"}, cycles


def _cycle_line(cycle):
    candidates = cycle.get("candidates") or []
    scores = cycle.get("scores") or {}
    beats = any((score or {}).get("beats_baseline") for score in scores.values())
    deflation = [((candidate.get("deflation") or {}).get("status")) for candidate in candidates]
    audit = [((candidate.get("audit") or {}).get("label")) for candidate in candidates]
    idea = ((cycle.get("hypotheses") or [{}])[0].get("idea") or "").split(":")[0]
    idea = idea if len(idea) <= 70 else idea[:69].rstrip() + "…"
    parts = [f"cycle {cycle.get('cycle_index')}", cycle.get("status", "?")]
    if candidates:
        parts.append("beats buy-and-hold" if beats else "does not beat buy-and-hold")
        parts.append("deflation " + ("PASS" if "PASS" in deflation else "FAIL"))
        parts.append(", ".join(sorted({label for label in audit if label})) or "not audited")
    else:
        parts.append(cycle.get("stop_code") or "no candidate")
    return " · ".join(parts) + (f" · {idea}" if idea else "")


def engine_runs(root: Path, limit: int = 8):
    """Return summaries of the newest engine runs, newest first. Running ones come first."""
    con = _connect(root)
    if con is None:
        return []
    try:
        rows = con.execute("select run_id, phase, record from engine_bounded_runs order by recorded_at desc limit 400").fetchall()
        starts, ends = {}, {}
        for run_id, phase, record in rows:
            (starts if phase == "START" else ends)[run_id] = json.loads(record)
        now = datetime.now(timezone.utc)
        newest = sorted(starts, key=lambda run_id: starts[run_id].get("recorded_at", ""), reverse=True)[:limit]
        summaries = [_summary(con, starts[run_id], ends.get(run_id), now)[0] for run_id in newest]
    except (sqlite3.Error, ValueError, TypeError):
        raise RunError("the research store cannot be read now") from None
    finally:
        con.close()
    return sorted(summaries, key=lambda item: item["status"] != "RUNNING")


def engine_card(root: Path, run_id: str, recent: int = 6):
    """Return one engine run's progress and its most recent cycles."""
    con = _connect(root)
    if con is None:
        raise RunError("the run was not found")
    try:
        rows = dict(con.execute("select phase, record from engine_bounded_runs where run_id = ?", (run_id,)).fetchall())
        if "START" not in rows:
            raise RunError("the run was not found")
        start = json.loads(rows["START"])
        card, cycles = _summary(con, start, json.loads(rows["END"]) if "END" in rows else None, datetime.now(timezone.utc))
    except (sqlite3.Error, ValueError, TypeError):
        raise RunError("the research store cannot be read now") from None
    finally:
        con.close()
    card["recent_cycles"] = [_cycle_line(cycle) for cycle in cycles[-recent:]] or ["no finished cycle yet"]
    return card
