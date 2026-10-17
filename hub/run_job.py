"""Report a separately authorized trusted job. Never store its command or output."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from job_events import STAGE_IDS, event_folder, project_key
from live import now_string
from process_watch import observe
from stage_reporting import StageReport, METRICS


def main():
    parser = argparse.ArgumentParser(description='Add live observations to an already authorized job.')
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--event-folder', type=Path)
    parser.add_argument('--stage', choices=sorted(STAGE_IDS), required=True)
    parser.add_argument('--kind', choices=['engineering', 'operational'], default='engineering')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(); command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command: parser.error('Supply the separately authorized command after --.')
    root = args.project_root.resolve(); folder = args.event_folder or event_folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink() or getattr(folder.stat(), 'st_file_attributes', 0) & 0x400:
        parser.error('The activity folder must not be a link.')
    target = None
    for index in range(64):
        candidate = folder / f'{index:02}.json'
        try:
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor); target = candidate; break
        except FileExistsError: continue
    if target is None: parser.error('All 64 retained job slots are used. Preserve the receipts before choosing a new activity folder.')
    identity = str(uuid4()); started = now_string()
    value = dict(version=1, run_id=identity, project=project_key(root), stage=args.stage, kind=args.kind,
                 state='Running', started_at=started, observed_at=started, finished_at=None, exit_code=None,
                 pid=os.getpid(), process_identity=None)
    receipt_available=True

    def publish():
        nonlocal receipt_available
        if not receipt_available:return
        try:
            value['observed_at'] = now_string()
            raw = (json.dumps(value, sort_keys=True) + '\n').encode()
            if len(raw) > 8192: raise ValueError('Job receipt exceeds its bound')
            pending = folder / f'{identity}.pending'
            with pending.open('xb') as stream: stream.write(raw)
            pending.replace(target)
        except (OSError,ValueError):
            receipt_available=False
            try: print('The job receipt is unavailable. The original job continues; its result is not inferred.',file=sys.stderr)
            except OSError: pass

    child = None;stage_report=None
    try:
        child = subprocess.Popen(command, cwd=root)
        value['pid'] = child.pid
        observation = observe(root, exclude_pids=set())
        value['process_identity'] = next((row['identity'] for row in observation['processes'] if row['pid'] == child.pid), None)
        if args.stage in METRICS:
            stage_report=StageReport(root,args.stage,kind=args.kind,folder=args.event_folder.parent/'stage-reports' if args.event_folder is not None else None)
            stage_report.__enter__();stage_report.bind_process(child.pid,value['process_identity'])
        publish()
        while child.poll() is None:
            time.sleep(1)
            publish()
        value.update(state='Completed' if child.returncode == 0 else 'Failed', exit_code=child.returncode, finished_at=now_string())
        if stage_report is not None: stage_report.finish(value['state'])
        publish(); return child.returncode
    except KeyboardInterrupt:
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=2)
        value.update(state='Interrupted', exit_code=child.returncode if child is not None else 130, finished_at=now_string())
        if stage_report is not None: stage_report.finish('Interrupted')
        publish(); return 130
    except (OSError, ValueError):
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=2)
        value.update(state='Failed', exit_code=child.returncode if child is not None else 1, finished_at=now_string())
        if stage_report is not None: stage_report.finish('Failed')
        try: publish()
        except (OSError, ValueError): pass
        print('The job or its activity receipt failed. No successful result is assumed.', file=sys.stderr)
        return 1
    finally:
        if stage_report is not None: stage_report.__exit__(*sys.exc_info())


if __name__ == '__main__': raise SystemExit(main())
