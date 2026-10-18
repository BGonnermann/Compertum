"""Small maintenance helpers for the disabled storage-check candidates.

These helpers cannot establish storage admission. They never enumerate folders.
"""
import hashlib
import json
import os
import time


def verify_archive_members(archive, pins):
    """Verify the same members using one name set for this open archive only."""
    names = set(archive.namelist())
    for name, pin in pins.items():
        if name in names:
            assert hashlib.sha256(archive.read(name)).hexdigest() == pin, name


def observation_charge(value, streams):
    """Compute the charge once after a fresh observation or its error fallback."""
    return value['charged'] + sum(row['charged'] for row in streams)


def poll_deadline(started, seconds, guard_poll, *, clock=time.monotonic, error='JOB_DEADLINE'):
    """Keep the caller's original start point and check host memory first."""
    guard_poll()
    if clock() - started >= seconds:
        raise RuntimeError(error)


def finish_child(record, exit_code, final_count, check):
    """Retain the child result before final checks can fail."""
    record['exit_code'] = exit_code
    final_count()
    check()
    record['status'] = 'PASSED' if exit_code == 0 else 'FAILED'


def close_diagnostics(record, journal):
    """A late or failed close must not leave a successful parent result."""
    try:
        journal.close()
    except BaseException as error:
        record.update(status='FAILED', error=type(error).__name__, reason=str(error))


class DiagnosticJournal:
    """Save at most 64 incomplete diagnostic records in an exclusive file.

    The caller charges this file to its existing records budget. Each write
    checks the original deadline before and after flushing. A blocking system
    call can delay the second check. The enclosing Job retains its deadline.
    """
    MAX_RECORDS = 64
    MAX_RECORD_BYTES = 1024
    MAX_BYTES = 64 * 1024

    def __init__(self, path, check, *, clock=time.monotonic):
        self.check = check
        self.clock = clock
        self.stream = path.open('xb')
        self.records = 0
        self.bytes = 0
        self.next_progress = 0.0

    def emit(self, phase, **values):
        self.check()
        record = dict(values, phase=phase, monotonic=self.clock(), diagnostic_only=True, complete=False,
                      production_admission=False)
        raw = (json.dumps(record, allow_nan=False, separators=(',', ':')) + '\n').encode()
        if (self.records >= self.MAX_RECORDS or len(raw) > self.MAX_RECORD_BYTES
                or self.bytes + len(raw) > self.MAX_BYTES):
            raise RuntimeError('DIAGNOSTIC_LIMIT')
        written = self.stream.write(raw)
        if written != len(raw):
            raise OSError('DIAGNOSTIC_SHORT_WRITE')
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.records += 1
        self.bytes += len(raw)
        self.check()

    def emit_progress(self, phase, *, force=False, **values):
        """Limit routine saved events. Keep the caller's monitoring frequency."""
        if force or self.clock() >= self.next_progress:
            self.emit(phase, **values)
            self.next_progress = self.clock() + 5

    def close(self):
        try:
            self.stream.close()
        finally:
            self.check()

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()
