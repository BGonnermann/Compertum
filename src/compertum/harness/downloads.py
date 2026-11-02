"""Read-only progress of history downloads, from the file that tools/update_indices.py writes."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from .display import ACCENT, BAD, FAINT, GOOD, MUTED, paint, visible
from .editor import LiveView

PROGRESS = Path("data") / "indices" / "pull-progress.json"
SCHEMA = "pull-progress-v1"
STALE_SECONDS = 120
MAX_BYTES = 1_000_000
RECENT, PENDING = 8, 8
FULL, EMPTY = "█", "░"
MISSING = "No download has started."
UNREADABLE = "The progress file cannot be read now."


def read_progress(root: Path):
    """Return the progress record, None when no download has started, or a message when the file cannot be read."""
    try:
        with open(root / PROGRESS, "rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError:
        return UNREADABLE
    if len(data) > MAX_BYTES:
        return UNREADABLE
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return UNREADABLE


def _text(value, limit):
    if not isinstance(value, str):
        return ""
    text = " ".join(visible(value).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _count(value):
    number = _number(value)
    return None if number is None else int(number)


def _when(value):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _span(minutes):
    minutes = int(round(minutes))
    if minutes < 1:
        return "under 1 min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min" if hours else f"{rest} min"


def finished(progress):
    return isinstance(progress, dict) and progress.get("finished") is True


def _head(progress, width):
    job = _text(progress.get("job"), 40) or "History download"
    total, done = _count(progress.get("total")), _count(progress.get("done"))
    if not total:
        return f"{job}  {done or 0} done"
    shown = min(done or 0, total)
    counts = f"{done if done is not None else '?'}/{total}  {shown * 100 // total}%"
    room = max(5, min(60, width - len(job) - len(f"{total}/{total}  100%") - 4))
    filled = room * shown // total
    return f"{job}  {FULL * filled}{EMPTY * (room - filled)}  {counts}"


def _detail(progress, ended):
    parts = ["finished"] if ended else []
    for key in ("loaded", "failed"):
        count = _count(progress.get(key))
        if count is not None:
            parts.append(f"{key} {count}")
    if ended:
        started, updated = _when(progress.get("started_utc")), _when(progress.get("updated_utc"))
        if started and updated and updated >= started:
            parts.append(f"took {_span((updated - started).total_seconds() / 60)}")
        return parts
    current = progress.get("current")
    symbol = _text(current.get("symbol"), 20) if isinstance(current, dict) else ""
    if symbol:
        years = _text(current.get("years"), 20).replace("-", "–")
        active = _count(progress.get("active"))
        more = f" +{active - 1}" if active is not None and active > 1 else ""
        parts.append(f"now: {symbol}" + (f" ({years})" if years else "") + more)
    rate, eta = _number(progress.get("rate_per_min")), _number(progress.get("eta_minutes"))
    if rate is not None:
        parts.append(f"{rate:.1f}/min")
    if eta is not None:
        parts.append(f"~{_span(eta)} left")
    return parts


def _recent(progress):
    recent = progress.get("recent")
    rows = []
    for item in recent[-RECENT:] if isinstance(recent, list) else []:
        symbol = _text(item.get("symbol"), 20) if isinstance(item, dict) else ""
        if not symbol:
            continue
        status = item.get("status")
        if status == "loaded":
            rows.append(f"  ✓ {symbol}")
        elif status == "failed":
            code = _text(item.get("code"), 80)
            rows.append(f"  ✗ {symbol}" + (f"  {code}" if code else ""))
        else:
            label = _text(status, 20)
            rows.append(f"  · {symbol}" + (f"  {label}" if label else ""))
    return rows


def progress_lines(progress, width=80, now=None):
    """Return the plain lines of the download view. Every field is untrusted, so bad fields are left out."""
    if progress is None:
        return [MISSING]
    if isinstance(progress, str):
        return [progress]
    if not isinstance(progress, dict):
        return [UNREADABLE]
    schema = progress.get("schema")
    if schema is not None and schema != SCHEMA:
        return [f"The progress file has an unknown format: {_text(schema, 40) or 'not text'}."]
    width = max(30, width)
    ended = finished(progress)
    lines = [_head(progress, width)]
    detail = _detail(progress, ended)
    while len(detail) > 1 and len(" · ".join(detail)) > width:
        detail.pop()
    if detail:
        lines.append(" · ".join(detail))
    updated = _when(progress.get("updated_utc"))
    if not ended and updated is not None:
        quiet = ((now or datetime.now(timezone.utc)) - updated).total_seconds()
        if quiet > STALE_SECONDS:
            lines += ["", f"No update for {int(quiet // 60)} minutes; the download may have stopped."]
    rows = _recent(progress)
    if rows:
        lines += ["", "recent", *rows]
    pending = progress.get("pending")
    names = [_text(name, 20) for name in pending if _text(name, 20)] if isinstance(pending, list) else []
    if names and not ended:
        lines += ["", "next  " + "  ".join(names[:PENDING])]
    return [line[:width] for line in lines]


def painted(line, first=False):
    """Color one line of the view in the project-map palette."""
    if first and line != MISSING and not line.startswith("The progress file"):
        bar = [index for index in (line.find(FULL), line.find(EMPTY)) if index >= 0]
        if not bar:
            return paint("1;" + ACCENT, line)
        start, end = min(bar), max(line.rfind(FULL), line.rfind(EMPTY)) + 1
        return (paint("1;" + ACCENT, line[:start]) + paint(ACCENT, FULL * line[start:end].count(FULL))
                + paint(FAINT, EMPTY * line[start:end].count(EMPTY)) + paint(MUTED, line[end:]))
    if line == "recent" or line.startswith("next  "):
        name, _, rest = line.partition(" ")
        return paint(ACCENT, name) + paint(MUTED, " " + rest if rest else "")
    if line.startswith("  ✓ "):
        return paint(GOOD, line[:3]) + line[3:]
    if line.startswith("  ✗ "):
        symbol, gap, code = line[4:].partition("  ")
        return paint(BAD, line[:3]) + " " + symbol + gap + paint(FAINT, code)
    if line.startswith(("No update for", "The progress file")):
        return paint(BAD, line)
    if line.startswith("finished"):
        return paint(GOOD, "finished") + paint(MUTED, line[len("finished"):])
    return paint(FAINT if line.startswith("  · ") else MUTED, line)


class DownloadView(LiveView):
    """A live view of the progress file. It reads the file once a second and stops reading after the download ends."""

    def __init__(self, out, root: Path, get_key=None, width=None, color=False, hint="q closes this pane", **clock):
        super().__init__(out, self._fetch, "History downloads", get_key=get_key, width=width, every=1.0,
                         color=color, hint=hint, **clock)
        self.root, self.done = root, False

    def _fetch(self):
        progress = read_progress(self.root)
        self.done = finished(progress)
        return progress_lines(progress, self._size())

    def _refresh(self):
        if not self.done:
            super()._refresh()

    def _lines(self):
        heading, blank, first, rest, column = super()._lines()
        if self.done:
            heading = f"{self.title} · finished · {self.hint}"[:self._size()]
        return heading, blank, first, rest, column

    def _paint(self, index, line):
        if index == 0:
            return paint("1;" + ACCENT, line[:len(self.title)]) + paint(FAINT, line[len(self.title):])
        return painted(line, first=index == 2)
