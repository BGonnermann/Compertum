"""Observe bounded committed SQLite bytes entirely in memory.

The original database, WAL, and shared-memory files are never opened by SQLite.
Format reference: https://www.sqlite.org/fileformat2.html#walformat
"""
import sqlite3
import struct
import time
import os
from pathlib import Path

MAX_DB = 16 * 1024 * 1024
MAX_WAL = 17 * 1024 * 1024


class SnapshotUnavailable(ValueError):
    pass


def read_regular(root, path, maximum):
    root, path = Path(root).absolute(), Path(path).absolute()
    try:
        parts = path.relative_to(root).parts
        if not parts or '..' in parts: raise SnapshotUnavailable()
        current = root
        for part in ('', *parts):
            current = current / part
            info = current.lstat()
            if current.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise SnapshotUnavailable()
        if not path.is_file() or info.st_nlink != 1 or info.st_size > maximum:
            raise SnapshotUnavailable()
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev,opened.st_ino,opened.st_nlink)!=(info.st_dev,info.st_ino,1): raise SnapshotUnavailable()
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            if (opened.st_size,opened.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise SnapshotUnavailable()
        if len(raw) > maximum: raise SnapshotUnavailable()
        return raw
    except OSError:
        raise SnapshotUnavailable() from None


def checksum(raw, order, state=(0, 0)):
    a, b = state
    for x, y in struct.iter_unpack(order + 'II', raw):
        a = (a + x + b) & 0xffffffff
        b = (b + y + a) & 0xffffffff
    return a, b


def committed_image(main, wal):
    if len(main) < 100 or main[:16] != b'SQLite format 3\0': raise SnapshotUnavailable()
    size = int.from_bytes(main[16:18], 'big'); size = 65536 if size == 1 else size
    if size < 512 or size > 65536 or size & (size - 1) or len(main) % size: raise SnapshotUnavailable()
    image = bytearray(main); pending = {}; committed = {}; pages = len(main) // size
    partial = False
    if wal:
        if len(wal) < 32: raise SnapshotUnavailable()
        magic, version, page_size = struct.unpack('>III', wal[:12])
        if magic not in {0x377f0682, 0x377f0683} or version != 3007000 or page_size != size:
            raise SnapshotUnavailable()
        order = '<' if magic == 0x377f0682 else '>'
        state = checksum(wal[:24], order)
        if state != struct.unpack('>II', wal[24:32]): raise SnapshotUnavailable()
        frame_size = 24 + size
        for offset in range(32, len(wal), frame_size):
            frame = wal[offset:offset + frame_size]
            if len(frame) != frame_size:
                partial = True; break
            page, end = struct.unpack('>II', frame[:8])
            next_state = checksum(frame[24:], order, checksum(frame[:8], order, state))
            if frame[8:16] != wal[16:24] or next_state != struct.unpack('>II', frame[16:24]):
                partial = True; break
            if page < 1 or page * size > MAX_DB or end * size > MAX_DB: raise SnapshotUnavailable()
            state = next_state; pending[page] = frame[24:]
            if end:
                committed.update(pending); pending.clear(); pages = end
        partial = partial or bool(pending)
        image.extend(b'\0' * max(0, pages * size - len(image)))
        del image[pages * size:]
        for page, content in committed.items():
            if page <= pages: image[(page - 1) * size:page * size] = content
    # Only the private memory image changes journal mode. Original bytes stay untouched.
    image[18:20] = b'\1\1'
    return bytes(image), partial


class Snapshot(sqlite3.Connection):
    partial = False


def open_snapshot(root, path):
    path = Path(path); wal_path = path.with_name(path.name + '-wal')
    journal = path.with_name(path.name + '-journal')
    def capture():
        if journal.exists() and read_regular(root, journal, MAX_WAL): raise SnapshotUnavailable()
        return read_regular(root, path, MAX_DB), read_regular(root, wal_path, MAX_WAL) if wal_path.exists() else b''
    first = capture()
    if first != capture(): raise SnapshotUnavailable()
    image, partial = committed_image(*first)
    db = sqlite3.connect(':memory:', factory=Snapshot)
    try:
        db.deserialize(image)
        db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA trusted_schema=OFF')
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2 * 1024 * 1024)
        deadline = time.monotonic() + .3
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        db.set_authorizer(lambda action, a, b, c, d: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        db.partial = partial
        return db
    except (sqlite3.Error, ValueError):
        db.close(); raise SnapshotUnavailable() from None
