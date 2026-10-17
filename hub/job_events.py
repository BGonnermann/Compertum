"""Small explicit job receipts, stored outside the product and source tree."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from loop import STAGES

FIELDS = {'version', 'run_id', 'project', 'stage', 'kind', 'state', 'started_at', 'observed_at',
          'finished_at', 'exit_code', 'pid', 'process_identity'}
STAGE_IDS = {item[0] for item in STAGES} | {'verification', 'engineering'}


def project_key(root):
    return hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()


def event_folder(root):
    return Path.home() / '.codex/visualizations' / f'compertum-live-{project_key(root)[:12]}' / 'jobs'


def read_jobs(root, processes, folder=None):
    folder = Path(folder) if folder is not None else event_folder(root)
    result = {'status': 'Not connected', 'jobs': []}
    if not folder.exists(): return result
    if folder.is_symlink() or getattr(folder.stat(), 'st_file_attributes', 0) & 0x400:
        result['status'] = 'Unavailable'; return result
    result['status'] = 'Available'
    identities = {row['identity'] for row in processes}
    for index in range(64):
        path = folder / f'{index:02}.json'
        if not path.exists(): continue
        try:
            if path.is_symlink() or getattr(path.stat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError()
            with path.open('rb') as stream: raw = stream.read(8193)
            if len(raw) > 8192: raise ValueError()
            value = json.loads(raw)
            if set(value) != FIELDS or value['version'] != 1 or value['project'] != project_key(root): raise ValueError()
            if not isinstance(value['run_id'], str) or not re.fullmatch(r'[0-9a-f-]{36}', value['run_id']): raise ValueError()
            if value['stage'] not in STAGE_IDS or value['kind'] not in {'engineering', 'operational'}: raise ValueError()
            if value['state'] not in {'Running', 'Completed', 'Failed', 'Interrupted'}: raise ValueError()
            if type(value['pid']) is not int or value['pid'] <= 0: raise ValueError()
            if value['process_identity'] is not None and (not isinstance(value['process_identity'], str) or not re.fullmatch(r'\d+-\d+', value['process_identity'])): raise ValueError()
            if value['exit_code'] is not None and type(value['exit_code']) is not int: raise ValueError()
            at = datetime.fromisoformat(value['observed_at'].replace('Z', '+00:00'))
            started = datetime.fromisoformat(value['started_at'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if at.tzinfo is None or started.tzinfo is None or not 0 <= (now - at).total_seconds() or started > at: raise ValueError()
            state = value['state']
            if state == 'Running':
                if value['finished_at'] is not None or value['exit_code'] is not None: raise ValueError()
                if (now - at).total_seconds() > 8: state = 'Stale observation'
                elif value['process_identity'] not in identities: state = 'Process not verified'
            else:
                finished = datetime.fromisoformat(value['finished_at'].replace('Z', '+00:00'))
                if finished.tzinfo is None or not started <= finished <= at or value['exit_code'] is None: raise ValueError()
                if state == 'Completed' and value['exit_code'] != 0: raise ValueError()
            result['jobs'].append({key: value[key] for key in FIELDS - {'project', 'version'}} | {'state': state, 'source': 'Explicit job receipt'})
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            result['status'] = 'Partial'
    result['jobs'].sort(key=lambda row: row['observed_at'], reverse=True)
    return result
