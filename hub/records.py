"""Bounded reads of public Compertum documents. No product or account access."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import threading
import time

MAX_RECORD_BYTES = 256 * 1024
MAX_CATALOG = 512
MAX_MAP_BYTES = 16 * 1024 * 1024
MAX_GIT_BYTES = 1024 * 1024
CORE_RECORDS = (
    'README.md', 'docs/CURRENT_CHECKPOINT.md', 'docs/BUILD_SPEC.md',
    'docs/PROJECT_MAP_REFRESH.md', 'docs/HUB_PLAN.md',
    'docs/M5_POSTED_FEES_PLAN.md', 'reports/M5_NATIVE_FEE_CONTEXT.md',
    'reports/HUB_VERIFICATION.md',
    'docs/HUB_LIVE_PLAN.md', 'docs/HUB_LIVE_ACTIVITY.md', 'reports/HUB_LIVE_VERIFICATION.md',
    'docs/HUB_REPORTING_PLAN.md', 'reports/HUB_REPORTING_VERIFICATION.md',
)
DEFAULT_MAP = Path.home() / '.codex/visualizations/2026/10/15/01a14191-f4fd-7730-8c3f-810c63c1b081/output/pdf/Compertum-project-map.pdf'
WORDS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
         'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}


def timestamp(seconds=None):
    value = datetime.now(timezone.utc) if seconds is None else datetime.fromtimestamp(seconds, timezone.utc)
    return value.isoformat(timespec='seconds').replace('+00:00', 'Z')


def clean_markdown(text):
    return re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text).replace('**', '').replace('`', '').strip()


def number(text):
    return WORDS.get(text.lower()) if not text.replace(',', '').isdigit() else int(text.replace(',', ''))


def newest_section(text):
    """Use only the first level-two section. Never search history for a result."""
    lines = text.splitlines()
    headings = [i for i, line in enumerate(lines) if line.startswith('## ')]
    if not headings:
        return {'heading': 'Current section unavailable', 'text': '', 'line': None, 'summary': 'No current section was found.'}
    start = headings[0]
    end = headings[1] if len(headings) > 1 else len(lines)
    body = '\n'.join(lines[start + 1:end]).strip()
    first_line = next((clean_markdown(line) for line in body.splitlines() if line.strip()), '')
    return {'heading': clean_markdown(lines[start][3:]), 'text': body,
            'line': start + 1, 'summary': first_line or 'This section has no recorded summary.'}


def result_counts(text):
    unavailable = dict(passed=None, failed=None, errors=None, skipped=None)
    source, installed = unavailable.copy(), unavailable.copy()
    match = re.search(r'Source and installed (?:checks|inventories) each (?:passed|contain) ([\d,]+) (?:matching )?distinct', text, re.I)
    if match:
        source['passed'] = installed['passed'] = number(match[1])
        if re.search(r'(?:with )zero failures, errors, (?:or|and) skips', text, re.I):
            for row in (source, installed):
                row.update(failed=0, errors=0, skipped=0)
    process = re.search(r'(\d[\d,]*) in-process cases', text, re.I)
    native = re.search(r'and (\d+|two) native Windows stages', text, re.I)
    return {'source': source, 'installed': installed,
            'in_process': number(process[1]) if process else None,
            'native_per_environment': number(native[1]) if native else None,
            'note': 'Saved checkpoint results. These inventories check the same cases in separate environments.'}


def safe_document_name(name):
    if name in CORE_RECORDS:
        return True
    parts = PurePosixPath(name).parts
    return (len(parts) == 2 and parts[0] in ('docs', 'reports')
            and re.fullmatch(r'[A-Za-z0-9_-]+\.md', parts[1]) is not None)


def regular_without_links(path, boundary):
    """Refuse links, Windows reparse points, and files outside the named root."""
    path = Path(path)
    try:
        path.relative_to(boundary)
        current = path
        while current != boundary:
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                return False
            current = current.parent
        return path.is_file() and path.resolve().is_relative_to(boundary.resolve())
    except (OSError, ValueError, RuntimeError):
        return False


def read_command(arguments, seconds=3):
    """Cap pipe bytes during collection. Never retain standard error output."""
    output = []
    deadline = time.monotonic() + seconds
    try:
        with subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as child:
            def collect():
                try:
                    output.append(child.stdout.read(MAX_GIT_BYTES + 1))
                except OSError:
                    pass
            reader = threading.Thread(target=collect, daemon=True)
            reader.start()
            reader.join(max(0, deadline - time.monotonic()))
            if reader.is_alive() or not output or len(output[0]) > MAX_GIT_BYTES:
                child.kill()
                child.wait(timeout=1)
                reader.join(timeout=1)
                return None
            try:
                code = child.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=1)
                return None
            return output[0].decode('utf-8') if code == 0 else None
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return None


class RecordStore:
    def __init__(self, root, map_pdf=DEFAULT_MAP):
        self.root = Path(root).resolve()
        self.map_pdf = Path(map_pdf)
        self._allowed = set(CORE_RECORDS)

    def _git(self, *arguments):
        """Disable optional Git writes. Keep execution and output bounded."""
        return read_command(['git', '--no-optional-locks', '-c', f'safe.directory={self.root.as_posix()}',
                             '-C', str(self.root), *arguments])

    def catalogue(self):
        raw = self._git('ls-files', '-z', '--', 'README.md', 'docs/*.md', 'reports/*.md')
        names = set(CORE_RECORDS)
        if raw is not None:
            names.update(name for name in raw.split('\0') if safe_document_name(name))
        ordered = sorted(names)
        omitted = max(0, len(ordered) - MAX_CATALOG)
        # Core records always survive the catalogue bound.
        ordered = list(CORE_RECORDS) + [n for n in ordered if n not in CORE_RECORDS][:MAX_CATALOG - len(CORE_RECORDS)]
        self._allowed = set(ordered)
        entries = []
        for name in ordered:
            path = self.root / name
            entry = {'path': name, 'kind': 'Report' if name.startswith('reports/') else 'Plan' if 'PLAN' in name else 'Project record'}
            try:
                info = path.stat()
                entry.update(modified_at=timestamp(info.st_mtime), bytes=info.st_size,
                             status='available' if regular_without_links(path, self.root) else 'unreadable')
            except OSError:
                entry.update(modified_at=None, bytes=None, status='missing')
            entries.append(entry)
        return {'entries': entries, 'omitted': omitted, 'git_available': raw is not None}

    def read_record(self, name):
        result = {'path': name, 'status': 'not_allowed', 'text': '', 'modified_at': None, 'sha256': None}
        if name not in self._allowed or not safe_document_name(name):
            return result
        path = self.root / name
        try:
            if not path.exists():
                result['status'] = 'missing'
                return result
            if not regular_without_links(path, self.root):
                result['status'] = 'unreadable'
                return result
            with path.open('rb') as stream:
                before = os.fstat(stream.fileno())
                if before.st_size > MAX_RECORD_BYTES:
                    result['status'] = 'too_large'
                    return result
                content = stream.read(MAX_RECORD_BYTES + 1)
                after = os.fstat(stream.fileno())
            if len(content) > MAX_RECORD_BYTES:
                result['status'] = 'too_large'
                return result
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                result['status'] = 'changed_during_read'
                return result
            result.update(text=content.decode('utf-8-sig'), status='available',
                          modified_at=timestamp(after.st_mtime), bytes=len(content),
                          sha256=hashlib.sha256(content).hexdigest())
        except UnicodeError:
            result['status'] = 'invalid'
        except OSError:
            result['status'] = 'unreadable'
        return result

    def work(self):
        raw = self._git('status', '--porcelain=v1', '-z', '--no-renames', '--untracked-files=normal')
        changes = []
        if raw is not None:
            for item in raw.split('\0'):
                if len(item) < 4:
                    continue
                code, name = item[:2], item[3:]
                first = name.split('/')[0]
                if first not in {'src', 'tests', 'docs', 'reports', 'hub', 'tools', 'config', 'README.md', 'AGENTS.md', 'pyproject.toml', 'uv.lock'}:
                    continue
                if any(p.startswith('.') for p in PurePosixPath(name).parts):
                    continue
                label = 'New file' if code == '??' else 'Deleted' if 'D' in code else 'Changed'
                changes.append({'path': name, 'status': label})
        return {'available': raw is not None, 'changes': changes[:100], 'omitted': max(0, len(changes) - 100),
                'note': 'Observed file changes. These do not establish that a job is running or that checks passed.'}

    def map_info(self):
        path = self.map_pdf
        available = (path.suffix.lower() == '.pdf' and regular_without_links(path, path.parent))
        try:
            info = path.stat() if available else None
            available = bool(info and info.st_size <= MAX_MAP_BYTES)
        except OSError:
            available, info = False, None
        return {'available': available, 'url': '/project-map.pdf' if available else None,
                'modified_at': timestamp(info.st_mtime) if available else None,
                'note': 'Saved project map. Its file time is not a verification time.'}

    def snapshot(self):
        catalogue = self.catalogue()
        checkpoint = self.read_record('docs/CURRENT_CHECKPOINT.md')
        section = newest_section(checkpoint['text'])
        section.update({key: checkpoint[key] for key in ('path', 'status', 'modified_at', 'sha256')})
        current = section['text']
        results = result_counts(current)
        spec = self.read_record('docs/BUILD_SPEC.md')
        accepted = re.search(r'Only (M\d) is fully accepted', current, re.I)
        milestone_rows = []
        for line in spec['text'].splitlines():
            cells = [clean_markdown(c) for c in line.strip().strip('|').split('|')]
            if len(cells) < 3 or not re.match(r'M\d+:', cells[0]):
                continue
            identity, name = cells[0].split(':', 1)
            status = 'Unavailable' if not accepted else 'Accepted' if identity.upper() == accepted[1].upper() else 'Not fully accepted'
            milestone_rows.append({'id': identity, 'name': name.strip(), 'requirements': cells[1], 'failure_checks': cells[2],
                                   'status': status, 'source': spec['path']})
        sessions = re.search(r'M6 remains (zero|\d+) of (ten|\d+) actual supervised sessions', current, re.I)
        lines = [clean_markdown(line) for line in current.splitlines() if line.strip()]
        next_steps = [line for line in lines if re.match(r'^(?:Next[, :]|Then )', line)]
        gaps = [line for line in lines if re.search(r'remain(?:s)? (?:open|unverified|incomplete)|remain unknown|remains incomplete', line, re.I)]
        links = []
        for name in re.findall(r'\b[A-Z][A-Z0-9_]+\.md\b', current):
            for prefix in ('docs/', 'reports/'):
                if prefix + name in self._allowed and prefix + name not in links:
                    links.append(prefix + name)
        return {'read_at': timestamp(), 'checkpoint': section, 'results': results,
                'next_steps': next_steps, 'gaps': gaps, 'related_records': links,
                'milestones': milestone_rows, 'sessions': {
                    'completed': number(sessions[1]) if sessions else None,
                    'required': number(sessions[2]) if sessions else None},
                'work': self.work(), 'catalogue': catalogue, 'map': self.map_info(),
                'runtime': {'status': 'Not observed', 'note': 'Operational stage status needs explicit job events. Saved documents do not establish a running operational loop.'}}
