"""Append-only local conversation sessions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .packets import MAX_CONVERSATION, encode

MAX_BYTES = 16 * 1024**2
MAX_RECORDS = 4096


class SessionError(Exception):
    pass


class SessionStore:
    def __init__(self, root: Path):
        self.folder = root / "state" / "harness" / "sessions"

    def create(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        identity = f"session-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        return Session(identity, self.folder / f"{identity}.jsonl")

    def load(self, identity):
        if not isinstance(identity, str) or not identity.startswith("session-") or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in identity):
            raise SessionError("the session ID is not valid")
        return Session(identity, self.folder / f"{identity}.jsonl").load()

    def list(self):
        if not self.folder.is_dir():
            return []
        return sorted(path.stem for path in self.folder.glob("session-*.jsonl") if path.is_file())

    def summaries(self, limit=20):
        """Describe the newest sessions with their date and first task, so the owner can choose one to resume."""
        rows = []
        for identity in sorted(self.list(), reverse=True)[:limit]:
            path = self.folder / f"{identity}.jsonl"
            first = ""
            try:
                with path.open("rb") as stream:
                    for line in stream.read(256 * 1024).splitlines():
                        record = json.loads(line)
                        payload = record.get("payload") or {}
                        if record.get("kind") == "message" and payload.get("role") == "user":
                            first = " ".join(str(payload.get("content") or "").split())[:80]
                            break
            except (OSError, ValueError, AttributeError):
                first = "(cannot be read)"
            stamp = identity[8:23]
            rows.append(f"{identity}  {stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]} UTC  "
                        f"{first or '(no task yet)'}")
        return rows


class Session:
    def __init__(self, identity, path):
        self.identity, self.path, self.records = identity, path, 0

    def append(self, kind, payload):
        if kind not in ("message", "outcome") or not isinstance(payload, dict):
            raise SessionError("the session record is not valid")
        record = {"kind": kind, "payload": payload}
        try:
            raw = encode(record) + b"\n"
        except (TypeError, ValueError, RecursionError):
            raise SessionError("the session record is not valid") from None
        if len(raw) > MAX_CONVERSATION:
            raise SessionError("the session record is too large")
        try:
            size = self.path.stat().st_size if self.path.exists() else 0
            if size + len(raw) > MAX_BYTES or self.records >= MAX_RECORDS:
                raise SessionError("the session is full; start a new session")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab") as stream:
                stream.write(raw)
                stream.flush()
            self.records += 1
        except OSError:
            raise SessionError("cannot save the session") from None

    def load(self):
        try:
            raw = self.path.read_bytes()
        except OSError:
            raise SessionError("cannot read the session") from None
        if len(raw) > MAX_BYTES:
            raise SessionError("the session is too large")
        messages = []
        try:
            lines = raw.splitlines()
            if len(lines) > MAX_RECORDS:
                raise SessionError("the session has too many records")
            for line in lines:
                record = json.loads(line)
                if not isinstance(record, dict) or record.get("kind") not in ("message", "outcome") or record.keys() != {"kind", "payload"}:
                    raise SessionError("the session record is not valid")
                payload = record["payload"]
                if not isinstance(payload, dict):
                    raise SessionError("the session payload is not valid")
                if record["kind"] == "message":
                    if payload.get("role") not in ("system", "user", "assistant", "tool"):
                        raise SessionError("the session message is not valid")
                    if payload.get("content") is not None and not isinstance(payload.get("content"), str):
                        raise SessionError("the session message is not valid")
                    messages.append(payload)
                self.records += 1
        except (ValueError, UnicodeError):
            raise SessionError("the session is not valid") from None
        if not messages or messages[0].get("role") != "system":
            raise SessionError("the session has no starting message")
        self.messages = messages
        return self
