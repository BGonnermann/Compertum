"""Current, sanitized local agent events and native process observations."""
from collections import deque
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import threading
import time

from activity_labels import activity_label
from process_watch import observe, project_path

MAX_READ = 512 * 1024
MAX_LINE = 256 * 1024
MAX_FILES = 24
STALE_SECONDS = 90
ID = re.compile(r'^[a-zA-Z0-9_-]{1,100}$')


def now_string():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def event_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed > datetime.now(timezone.utc) + timedelta(seconds=5):
            return None
        return parsed
    except (TypeError, ValueError, AttributeError):
        return None


class AgentReader:
    def __init__(self, root, sessions=None):
        self.root = Path(root).resolve()
        self.sessions = Path(sessions) if sessions is not None else Path.home() / '.codex/sessions'
        self.files = {}
        self.events = deque(maxlen=80)
        self.last_discovery = 0
        self.limited = False

    def discover(self):
        candidates = []
        today = datetime.now(timezone.utc)
        for offset in range(7):
            folder = self.sessions / (today - timedelta(days=offset)).strftime('%Y/%m/%d')
            try:
                for index, path in enumerate(folder.glob('rollout-*.jsonl')):
                    if index >= 128:
                        self.limited = True; break
                    info = path.lstat()
                    if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                        continue
                    candidates.append((info.st_mtime, path))
            except OSError:
                continue
        selected = []; metadata_budget = 4 * 1024 * 1024
        for inspected, (_, path) in enumerate(sorted(candidates, key=lambda pair: pair[0], reverse=True)):
            if inspected >= 128 or metadata_budget <= 0:
                self.limited = True; break
            if path in self.files:
                selected.append(path)
                if len(selected) >= MAX_FILES:
                    self.limited = True; break
                continue
            try:
                with path.open('rb') as stream:
                    raw = stream.readline(min(MAX_LINE + 1, metadata_budget))
                metadata_budget -= len(raw)
                if len(raw) > MAX_LINE:
                    self.limited = True; continue
                meta = json.loads(raw)
                if not isinstance(meta, dict):
                    self.limited = True; continue
                payload = meta.get('payload', {})
                if meta.get('type') != 'session_meta' or not isinstance(payload, dict):
                    continue
                cwd = payload.get('cwd', '')
                if not project_path(cwd, self.root) or Path(str(cwd).removeprefix('\\\\?\\')).resolve() != self.root:
                    continue
                identity = payload.get('id')
                if not isinstance(identity, str) or not ID.fullmatch(identity):
                    continue
                self.files[path] = {'id': identity, 'offset': 0, 'carry': b'', 'discarding': False, 'pending': {}, 'state': 'Not observed',
                                    'activity': 'No current event', 'last_signal': None, 'history_partial': False}
                selected.append(path)
                if len(selected) >= MAX_FILES:
                    self.limited = True; break
            except (OSError, ValueError, UnicodeError, RuntimeError):
                self.limited = True
        self.files = {path: self.files[path] for path in selected}
        self.last_discovery = time.monotonic()

    def consume(self, item, state):
        if not isinstance(item, dict) or not isinstance(item.get('payload'), dict):
            return
        if item.get('type') not in {'event_msg', 'response_item'}:
            return
        at = event_time(item.get('timestamp'))
        if at is None:
            return
        # A timestamp is a signal only. Reasoning, prompts and message content are never exported.
        if state['last_signal'] and at < state['last_signal']:
            return
        state['last_signal'] = at
        payload = item['payload']; kind = item.get('type'); subtype = payload.get('type')
        if kind == 'event_msg' and subtype in {'task_started', 'task_complete', 'turn_aborted'}:
            state['pending'].clear()
            state['state'] = {'task_started': 'Working', 'task_complete': 'Finished turn', 'turn_aborted': 'Interrupted'}[subtype]
            state['activity'] = {'task_started': 'Agent working', 'task_complete': 'Turn finished', 'turn_aborted': 'Turn interrupted'}[subtype]
            self.add_event(state, state['activity'], at)
        elif kind == 'response_item' and subtype in {'function_call', 'custom_tool_call'}:
            key = payload.get('call_id') or payload.get('id')
            if isinstance(key, str) and ID.fullmatch(key):
                text = payload.get('input', payload.get('arguments', ''))
                label = activity_label(payload.get('name', ''), text if isinstance(text, str) else '')
                if len(state['pending']) < 32:
                    state['pending'][key] = label
                else:
                    self.limited = True
                state.update(state='Working', activity=label)
                self.add_event(state, label, at)
        elif kind == 'response_item' and subtype in {'function_call_output', 'custom_tool_call_output'}:
            state['pending'].pop(payload.get('call_id'), None)
            if state['state'] == 'Working':
                state['activity'] = next(reversed(state['pending'].values()), 'Agent working')
        elif kind == 'event_msg' and subtype == 'item_completed':
            detail = payload.get('item', {})
            if not isinstance(detail, dict):
                return
            if detail.get('type') == 'CommandExecution' and project_path(detail.get('cwd', ''), self.root):
                code = detail.get('exit_code')
                if type(code) is int and -2147483648 <= code <= 4294967295:
                    self.add_event(state, 'Command exited', at, exit_code=code)
            elif detail.get('type') == 'FileChange':
                self.add_event(state, 'File changes reported', at)
        elif state['state'] == 'Not observed' and kind in {'event_msg', 'response_item'} and subtype in {'token_count', 'reasoning', 'agent_message', 'message'}:
            # A bounded tail may start after turn/start. State exactly what was observed.
            state.update(state='Recent activity', activity='Recent agent signal')

    def add_event(self, state, label, at, **extra):
        self.events.append({'source': 'Agent event', 'agent_id': state['id'], 'label': label,
                            'at': at.isoformat().replace('+00:00', 'Z'), 'stage': 'verification' if label == 'Running test tools' else 'engineering', **extra})

    def snapshot(self):
        if not self.sessions.is_dir():
            return {'status': 'Unavailable', 'agents': [], 'events': [], 'partial': True}
        if time.monotonic() - self.last_discovery > 10 or not self.files:
            self.discover()
        partial = self.limited
        budget = 2 * 1024 * 1024
        ordered = sorted(self.files.items(), key=lambda pair: pair[0].stat().st_mtime if pair[0].exists() else 0, reverse=True)
        for path, state in ordered[:MAX_FILES]:
            try:
                info = path.lstat()
                if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                    state['state'] = 'Unavailable'; partial = True; continue
                if info.st_size < state['offset']:
                    state.update(offset=0, carry=b'', discarding=False, pending={}, state='Not observed', last_signal=None)
                    state['history_partial'] = True
                start = state['offset']; skip_first = False
                if info.st_size - start > MAX_READ:
                    start = info.st_size - MAX_READ
                    state['carry'] = b''; state['pending'].clear(); state['history_partial'] = True
                    skip_first = True
                amount = min(MAX_READ, budget)
                if amount <= 0:
                    partial = True; break
                with path.open('rb') as stream:
                    stream.seek(start); raw = stream.read(amount)
                budget -= len(raw); state['offset'] = start + len(raw)
                # An initial tail starts mid-record. Skip that record before parsing.
                if skip_first or state['discarding']:
                    first = raw.find(b'\n')
                    state['discarding'] = first < 0
                    raw = raw[first + 1:] if first >= 0 else b''
                joined = state['carry'] + raw
                lines = joined.split(b'\n'); state['carry'] = lines.pop()
                if len(state['carry']) > MAX_LINE:
                    state['carry'] = b''; state['discarding'] = True; state['history_partial'] = True; partial = True
                for line in lines:
                    if len(line) > MAX_LINE:
                        state['history_partial'] = True; partial = True; continue
                    try:
                        self.consume(json.loads(line), state)
                    except (ValueError, UnicodeError, TypeError):
                        state['history_partial'] = True; partial = True
                partial = partial or bool(state['carry'])
            except OSError:
                state['state'] = 'Unavailable'; partial = True
        agents = []
        now = datetime.now(timezone.utc)
        for state in self.files.values():
            partial = partial or state['history_partial']
            at = state['last_signal']
            age = (now - at).total_seconds() if at else None
            status = state['state']
            if status in {'Working', 'Recent activity'} and (age is None or age > STALE_SECONDS):
                status = 'Stale observation'
            agents.append({'id': state['id'], 'state': status, 'activity': state['activity'],
                           'last_signal': at.isoformat().replace('+00:00', 'Z') if at else None,
                           'age_seconds': round(age, 1) if age is not None else None,
                           'pending_tools': len(state['pending']), 'history_partial': state['history_partial']})
        agents.sort(key=lambda row: row['last_signal'] or '', reverse=True)
        return {'status': 'Partial' if partial else 'Available', 'agents': agents,
                'events': list(reversed(self.events)), 'partial': partial,
                'note': 'Local project agent events. Raw prompts, reasoning, commands and output are never served.'}


class LiveMonitor:
    def __init__(self, root, sessions=None):
        self.root = Path(root).resolve(); self.reader = AgentReader(root, sessions)
        self.lock = threading.Lock(); self.cached = None; self.last_read = 0
        self.prior_processes = {}; self.process_events = deque(maxlen=40)
        from runtime_records import RuntimeReader
        self.runtime_reader = RuntimeReader(self.root)

    def snapshot(self):
        with self.lock:
            if self.cached is not None and time.monotonic() - self.last_read < 1:
                return self.cached
            agents = self.reader.snapshot(); native = observe(self.root)
            for root in self.runtime_reader.roots[1:]:
                if not root.is_dir() or root.is_relative_to(self.root): continue
                extra = observe(root)
                native['processes'].extend(row | {'runtime_name': 'Original development runtime'} for row in extra['processes'])
                native['unreadable_candidates'] += extra['unreadable_candidates']
                if extra['status'] != 'Available': native['status'] = 'Partial'
            current = {row['identity']: row for row in native['processes']}
            at = now_string()
            if native['status'] != 'Unavailable':
                for identity, old in self.prior_processes.items():
                    if identity not in current:
                        self.process_events.append({'source': 'Process observation', 'label': 'Process no longer observed; outcome unknown',
                                                    'at': at, 'pid': old['pid'], 'stage': old['stage']})
                self.prior_processes = current
            result = {'observed_at': at, 'agents': agents['agents'], 'processes': native['processes'],
                      'events': sorted(agents['events'] + list(self.process_events), key=lambda row: row['at'], reverse=True)[:80],
                      'coverage': {'agents': agents['status'], 'processes': native['status'],
                                   'partial_history': agents['partial'], 'unreadable_processes': native['unreadable_candidates']},
                      'stale_after_seconds': STALE_SECONDS, 'refresh_seconds': 2}
            from job_events import read_jobs
            reported = read_jobs(self.root, native['processes'])
            result['jobs'] = reported['jobs']; result['coverage']['stage_jobs'] = reported['status']
            result['reporting'] = self.runtime_reader.snapshot(native['processes'])
            from stage_reporting import read_reports
            result['stage_reports'] = read_reports(self.root,native['processes'])
            for stage in result['reporting']['stages']:
                if stage['id'] in result['stage_reports']['stages']:
                    stage['connection']=result['stage_reports']['stages'][stage['id']]['status']
            from loop import build_loop
            result['loop'] = build_loop(result)
            self.cached = result; self.last_read = time.monotonic()
            return result
