"""Bounded evidence writes for a prepared, inactive storage allocation.

These helpers do not establish full storage admission or launch children.
Callers must retain their existing deadline, memory, and child cleanup checks.
"""
import json
import os
from pathlib import Path
import re
import stat
import threading
import time

BLOCK = 4096
LIMIT = 8 * 1024**2
NAMESPACE = 'artifacts/m5/simulated-evidence-next-01'


def charged(size):
    if type(size) is not int or size < 0:
        raise ValueError('INVALID_EVIDENCE_SIZE')
    return ((size + BLOCK - 1) // BLOCK) * BLOCK


def unused_allowance(actual):
    """Add this hold to a census that already includes actual records."""
    charged(actual)
    if actual > LIMIT:
        raise RuntimeError('EVIDENCE_FOLDER_LIMIT')
    return LIMIT - actual


def add_folder_check(existing, root):
    """Return 29 checks without changing any of the original 28 checks."""
    folder = Path(root) / NAMESPACE
    if len(existing) != 28 or folder in existing:
        raise ValueError('EXISTING_FOLDER_CHECKS_CHANGED')
    return [*existing, folder]


def output_bindings(proposal, kind, name):
    if kind not in ('stage', 'capacity') or not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', name):
        raise ValueError('INVALID_EVIDENCE_BINDING')
    if proposal['namespace'] != NAMESPACE or proposal['folder_limit_bytes'] != LIMIT:
        raise ValueError('EVIDENCE_ALLOCATION_CHANGED')
    return {key.replace('NAME', name): value
            for key, value in proposal[f'per_{kind}_output_charged_bytes'].items()}


def regular_folder(path):
    """Reject links and reparse points in every existing ancestor."""
    for parent in [path, *path.parents]:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RuntimeError('UNSAFE_EVIDENCE_FOLDER')


class EvidenceFolder:
    """Own a fixed set of files in one serial job.

    The complete per-file allowance is reserved before the first write.
    Existing files remain immutable. A failed stream cannot report success.
    External writers and child handle inheritance are not supported.
    """

    def __init__(self, folder, bindings, poll, *, limit=LIMIT, writable=None):
        self.folder = Path(folder).absolute()
        regular_folder(self.folder)
        self.poll = poll
        self.limit = limit
        self.bindings = dict(bindings)
        self.writable = set(self.bindings if writable is None else writable)
        if not self.writable <= self.bindings.keys():
            raise ValueError('UNKNOWN_WRITABLE_OUTPUT')
        self.streams = {}
        self.failed = False
        self.lock = threading.RLock()
        if not self.bindings:
            raise ValueError('EMPTY_EVIDENCE_BINDINGS')
        for name, bound in self.bindings.items():
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}', name):
                raise ValueError('INVALID_EVIDENCE_NAME')
            if type(bound) is not int or bound <= 0 or bound % BLOCK:
                raise ValueError('INVALID_EVIDENCE_BOUND')
        if len({name.casefold() for name in self.bindings}) != len(self.bindings):
            raise ValueError('DUPLICATE_EVIDENCE_NAME')
        if not any(name.endswith('.closure.json') for name in self.bindings):
            raise ValueError('CLOSURE_RESERVATION_REQUIRED')
        for name in self.writable:
            if os.path.lexists(self.folder / name):
                raise FileExistsError('PRESERVE_EXISTING_EVIDENCE')
        self.check()

    def check(self):
        self.poll()
        regular_folder(self.folder)
        used = BLOCK
        reserved = sum(self.bindings.values())
        observed = set()
        with os.scandir(self.folder) as entries:
            for entry in entries:
                self.poll()
                info = os.stat(entry.path, follow_symlinks=False)
                observed.add(entry.name)
                if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise RuntimeError('UNSAFE_EVIDENCE_ENTRY')
                stream = self.streams.get(entry.name)
                if stream is None:
                    if entry.name in self.bindings and entry.name not in self.writable:
                        if charged(info.st_size) > self.bindings[entry.name]:
                            raise RuntimeError('EVIDENCE_FILE_LIMIT')
                        continue
                    if entry.name.casefold() in {n.casefold() for n in self.bindings}:
                        raise RuntimeError('UNOWNED_EVIDENCE_OUTPUT')
                    used += charged(info.st_size)
                else:
                    if (info.st_dev, info.st_ino) != stream.identity or info.st_size != stream.size:
                        raise RuntimeError('EVIDENCE_CHANGED_EXTERNALLY')
                    if charged(info.st_size) > self.bindings[entry.name]:
                        raise RuntimeError('EVIDENCE_FILE_LIMIT')
        if not self.streams.keys() <= observed:
            raise RuntimeError('EVIDENCE_OUTPUT_REMOVED')
        if used + reserved > self.limit:
            raise RuntimeError('EVIDENCE_FOLDER_RESERVATION_LIMIT')
        self.poll()

    def open(self, name):
        with self.lock:
            self.check()
            if name not in self.writable or name in self.streams:
                raise ValueError('EVIDENCE_OUTPUT_NOT_AVAILABLE')
            stream = BoundedOutput(self, name)
            self.streams[name] = stream
            return stream

    def save(self, name, value):
        with self.open(name) as stream:
            stream.write((json.dumps(value, allow_nan=False, indent=2) + '\n').encode('utf-8'))

    def finish(self):
        """Call after child cleanup. A truncated or unclosed stream fails."""
        self.check()
        if self.failed or any(not stream.closed for stream in self.streams.values()):
            raise RuntimeError('EVIDENCE_OUTPUT_FAILED')

    def save_closure(self, name, record):
        """Use a separate five-second cleanup budget after execution stops.

        This does not extend child execution or authorize another job.
        """
        if not name.endswith('.closure.json'):
            raise ValueError('CLOSURE_NAME_REQUIRED')
        previous = self.poll
        deadline = time.monotonic() + 5
        def cleanup_poll():
            if time.monotonic() >= deadline:
                raise TimeoutError('EVIDENCE_CLOSURE_DEADLINE')
        self.poll = cleanup_poll
        try:
            if self.failed:
                record = dict(record, status='FAILED', evidence_output_failed=True)
            self.save(name, record)
            self.finish()
        finally:
            self.poll = previous

    def save_failure(self, name, record):
        """Save a reserved failure record after execution has stopped."""
        if record.get('status') not in {'FAILED', 'FIRST_GATE_FAILED_STOP'}:
            raise ValueError('FAILURE_RECORD_REQUIRED')
        previous = self.poll
        deadline = time.monotonic() + 5
        def cleanup_poll():
            if time.monotonic() >= deadline:
                raise TimeoutError('EVIDENCE_FAILURE_DEADLINE')
        self.poll = cleanup_poll
        try:
            self.save(name, record)
        finally:
            self.poll = previous


class BoundedOutput:
    def __init__(self, owner, name):
        self.owner, self.name = owner, name
        self.file = (owner.folder / name).open('xb', buffering=0)
        info = os.fstat(self.file.fileno())
        self.identity = (info.st_dev, info.st_ino)
        self.size = 0

    @property
    def closed(self):
        return self.file.closed

    def write(self, data):
        with self.owner.lock:
            try:
                self.owner.check()
                if not isinstance(data, bytes):
                    raise TypeError('EVIDENCE_REQUIRES_BYTES')
                if self.size + len(data) > self.owner.bindings[self.name]:
                    raise RuntimeError('EVIDENCE_FILE_LIMIT')
                written = self.file.write(data)
                self.size += written
                if written != len(data):
                    raise OSError('EVIDENCE_SHORT_WRITE')
                os.fsync(self.file.fileno())
                self.owner.check()
                return written
            except BaseException:
                self.owner.failed = True
                raise

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind:
            self.owner.failed = True
        self.close()


class EvidenceJournal:
    """Keep diagnostic records inside the same reserved output ledger."""
    def __init__(self, folder, name, poll):
        self.stream = folder.open(name)
        self.poll = poll
        self.next_progress = 0.0
        self.records = 0

    def emit_progress(self, phase, *, force=False, **values):
        self.poll()
        if force or time.monotonic() >= self.next_progress:
            raw = (json.dumps(dict(values, phase=phase, diagnostic_only=True,
                                   complete=False, production_admission=False)) + '\n').encode()
            if self.records >= 64 or len(raw) > 1024:
                raise RuntimeError('DIAGNOSTIC_LIMIT')
            self.stream.write(raw)
            self.records += 1
            self.next_progress = time.monotonic() + 5

    def emit(self, phase, **values):
        self.emit_progress(phase, force=True, **values)

    def close(self):
        self.stream.close()
        self.poll()


class TextOutput:
    """Encode text into a bounded binary stream without exposing its handle."""
    encoding = 'utf-8'

    def __init__(self, stream):
        self.stream = stream

    def write(self, value):
        self.stream.write(value.encode(self.encoding))
        return len(value)

    def flush(self):
        pass

    def close(self):
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.stream.__exit__(kind, value, traceback)
