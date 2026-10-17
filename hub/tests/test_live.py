"""Live observations must come from current events or actual native processes."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

HUB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB))
try:
    import live
    import process_watch
    import loop
except ImportError:
    live = process_watch = loop = None

IDENTITY = '12345678-1234-4234-8234-123456789012'


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(live, 'The live activity reader must exist')
        base = HUB.parent / '.cache/test-runs/hub-live-20261017'
        base.mkdir(parents=True, exist_ok=True)
        self.folder = base / uuid.uuid4().hex
        self.folder.mkdir()
        self.addCleanup(self.cleanup, base.resolve())
        self.root = self.folder / 'project'; self.root.mkdir()
        self.sessions = self.folder / 'sessions'
        today = datetime.now(timezone.utc)
        self.day = self.sessions / today.strftime('%Y/%m/%d'); self.day.mkdir(parents=True)
        self.path = self.day / f'rollout-test-{IDENTITY}.jsonl'
        self.at = today.isoformat()
        self.append('session_meta', dict(id=IDENTITY, cwd=str(self.root)))
        self.reader = live.AgentReader(self.root, self.sessions)

    def cleanup(self, base):
        target = self.folder.resolve(); self.assertEqual(target.parent, base); shutil.rmtree(target)

    def append(self, kind, payload, at=None):
        with self.path.open('ab') as stream:
            stream.write((json.dumps(dict(type=kind, timestamp=at or self.at, payload=payload)) + '\n').encode())

    def test_agent_start_and_completion_are_current(self):
        self.append('event_msg', dict(type='task_started', turn_id='turn1'))
        self.assertEqual(self.reader.snapshot()['agents'][0]['state'], 'Working')
        self.append('event_msg', dict(type='task_complete', turn_id='turn1', last_agent_message='private fixture'))
        row = self.reader.snapshot()['agents'][0]
        self.assertEqual(row['state'], 'Finished turn')
        self.assertNotIn('private fixture', json.dumps(row))

    def test_pending_test_tool_is_visible(self):
        self.append('response_item', dict(type='custom_tool_call', name='exec', call_id='call1', input='await tools.exec_command({cmd:"python -B -m unittest discover"})'))
        row = self.reader.snapshot()['agents'][0]
        self.assertEqual(row['activity'], 'Running test tools')
        self.assertEqual(row['pending_tools'], 1)

    def test_reading_a_test_script_is_not_running_it(self):
        self.append('response_item', dict(type='custom_tool_call', name='exec', call_id='call1', input='text(await tools.exec_command({cmd:"Get-Content hub/tests/check_browser.cjs"}))'))
        self.assertNotEqual(self.reader.snapshot()['agents'][0]['activity'], 'Running test tools')

    def test_tool_return_does_not_invent_test_success(self):
        self.append('response_item', dict(type='function_call', name='exec', call_id='call1', arguments='pytest tests/test_example.py'))
        self.reader.snapshot()
        self.append('response_item', dict(type='function_call_output', call_id='call1', output='private fixture output'))
        row = self.reader.snapshot()['agents'][0]
        self.assertEqual(row['pending_tools'], 0)
        self.assertNotIn('Passed', row['activity'])
        self.assertNotIn('private fixture', json.dumps(row))

    def test_command_exit_is_an_observed_command_result(self):
        self.append('event_msg', dict(type='item_completed', item=dict(type='CommandExecution', id='cmd1', cwd=str(self.root), command='python -m pytest', status='completed', exit_code=1, aggregated_output='private fixture output')))
        result = self.reader.snapshot()
        self.assertEqual(result['events'][0]['exit_code'], 1)
        self.assertNotIn('private fixture', json.dumps(result))

    def test_other_projects_are_excluded(self):
        self.path.write_text(json.dumps(dict(type='session_meta', payload=dict(id=IDENTITY, cwd=str(self.folder / 'other')))) + '\n', encoding='utf-8')
        self.assertEqual(self.reader.snapshot()['agents'], [])

    def test_newer_other_projects_do_not_hide_this_project(self):
        os.utime(self.path, (1, 1))
        for index in range(25):
            path = self.day / f'rollout-other-{index}.jsonl'
            path.write_text(json.dumps(dict(type='session_meta', payload=dict(id=str(uuid.uuid4()), cwd=str(self.folder / 'other')))) + '\n', encoding='utf-8')
        self.append('event_msg', dict(type='task_started', turn_id='turn1'))
        os.utime(self.path, (1, 1))
        self.assertEqual(len(self.reader.snapshot()['agents']), 1)

    def test_relative_project_identity_is_refused(self):
        self.path.write_text(json.dumps(dict(type='session_meta', payload=dict(id=IDENTITY, cwd='.'))) + '\n', encoding='utf-8')
        reader = live.AgentReader(Path.cwd(), self.sessions)
        self.assertEqual(reader.snapshot()['agents'], [])

    def test_oversized_record_suffix_cannot_become_an_event(self):
        with self.path.open('ab') as stream: stream.write(b'x' * (live.MAX_LINE + 10))
        self.reader.snapshot()
        self.append('event_msg', dict(type='task_started', turn_id='fake-suffix'))
        self.assertNotEqual(self.reader.snapshot()['agents'][0]['state'], 'Working')

    def test_stale_signal_is_not_reported_running(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.append('event_msg', dict(type='task_started', turn_id='turn1'), old)
        self.assertEqual(self.reader.snapshot()['agents'][0]['state'], 'Stale observation')

    def test_future_signal_is_not_accepted(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.append('event_msg', dict(type='task_started', turn_id='turn1'), future)
        self.assertNotEqual(self.reader.snapshot()['agents'][0]['state'], 'Working')

    def test_partial_append_waits_for_a_complete_record(self):
        with self.path.open('ab') as stream: stream.write(b'{"type":"event_msg",')
        result = self.reader.snapshot()
        self.assertTrue(result['partial'])
        with self.path.open('ab') as stream:
            stream.write(('"timestamp":' + json.dumps(self.at) + ',"payload":{"type":"task_started","turn_id":"turn1"}}\n').encode())
        self.assertEqual(self.reader.snapshot()['agents'][0]['state'], 'Working')

    def test_reasoning_and_user_content_are_not_exposed(self):
        self.append('response_item', dict(type='reasoning', summary='private fixture', content='private fixture'))
        self.append('event_msg', dict(type='user_message', message='private fixture'))
        self.assertNotIn('private fixture', json.dumps(self.reader.snapshot()))

    def test_missing_activity_source_is_unavailable(self):
        reader = live.AgentReader(self.root, self.folder / 'absent')
        self.assertEqual(reader.snapshot()['status'], 'Unavailable')

    def test_unsupported_metadata_is_partial_without_stopping_live_reads(self):
        self.path.write_text('[]\n', encoding='utf-8')
        result = self.reader.snapshot()
        self.assertEqual(result['status'], 'Partial')
        self.assertEqual(result['agents'], [])

    def test_loop_has_whole_path_and_feedback(self):
        result = loop.build_loop(dict(processes=[], agents=[], events=[]))
        names = {row['id'] for row in result['stages']}
        self.assertTrue({'data', 'quality', 'proposals', 'experiments', 'mathematics', 'development_audit', 'final_evaluation', 'independent_audit', 'qualification', 'authorization', 'signals', 'risk', 'intentions', 'execution', 'reconciliation', 'reports', 'feedback'} <= names)
        self.assertTrue(any(edge['from'] == 'feedback' and edge['to'] == 'proposals' for edge in result['connections']))
        self.assertTrue(all(row['state'] == 'Not observed' for row in result['stages']))

    def test_engineering_tests_do_not_activate_operational_loop(self):
        result = loop.build_loop(dict(processes=[dict(kind='test', stage='verification', label='Python tests')], agents=[], events=[]))
        self.assertTrue(all(row['state'] == 'Not observed' for row in result['stages']))
        self.assertEqual(len(result['engineering']), 1)

    def test_reported_engineering_process_is_counted_once(self):
        result = loop.build_loop(dict(processes=[dict(kind='test',stage='verification',pid=123,identity='123-456')], jobs=[dict(kind='engineering',stage='verification',pid=123,process_identity='123-456',state='Running')]))
        self.assertEqual(len(result['engineering']), 1)

    def test_reported_operational_process_is_not_engineering(self):
        result = loop.build_loop(dict(processes=[dict(kind='work',stage='engineering',pid=123,identity='123-456')], jobs=[dict(kind='operational',stage='experiments',pid=123,process_identity='123-456',state='Running')]))
        self.assertEqual(len(result['engineering']), 0)

    def test_explicit_operational_event_updates_only_its_stage(self):
        result = loop.build_loop(dict(processes=[], agents=[], events=[], jobs=[dict(kind='operational', stage='experiments', state='Running')]))
        self.assertEqual(next(row for row in result['stages'] if row['id'] == 'experiments')['state'], 'Running')
        self.assertTrue(all(row['state'] == 'Not observed' for row in result['stages'] if row['id'] != 'experiments'))

    def test_reported_job_completion_is_read_from_its_receipt(self):
        import job_events
        folder = self.folder / 'jobs'
        command = [sys.executable, '-B', str(HUB / 'run_job.py'), '--project-root', str(self.root), '--event-folder', str(folder), '--stage', 'verification', '--', sys.executable, '-B', '-c', 'pass']
        reply = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(reply.returncode, 0)
        result = job_events.read_jobs(self.root, [], folder)
        self.assertEqual(result['jobs'][0]['state'], 'Completed')
        self.assertEqual(result['jobs'][0]['exit_code'], 0)
        self.assertEqual(result['jobs'][0]['kind'], 'engineering')

    def test_untrusted_job_fields_are_not_exported(self):
        import job_events
        folder = self.folder / 'jobs'; folder.mkdir()
        (folder/'00.json').write_text(json.dumps(dict(secret='private fixture')), encoding='utf-8')
        result = job_events.read_jobs(self.root, [], folder)
        self.assertEqual(result['jobs'], [])
        self.assertEqual(result['status'], 'Partial')

    def test_terminal_job_timestamp_is_validated(self):
        import job_events
        folder = self.folder / 'jobs'; folder.mkdir()
        value = dict(version=1,run_id=str(uuid.uuid4()),project=job_events.project_key(self.root),stage='experiments',kind='operational',state='Completed',started_at=self.at,observed_at=self.at,finished_at='private fixture text',exit_code=0,pid=123,process_identity=None)
        (folder/'00.json').write_text(json.dumps(value), encoding='utf-8')
        result = job_events.read_jobs(self.root, [], folder)
        self.assertEqual(result['jobs'], [])
        self.assertNotIn('private fixture', json.dumps(result))

    def test_running_job_requires_current_process_identity(self):
        import job_events
        folder = self.folder / 'jobs'; folder.mkdir()
        value = dict(version=1,run_id=str(uuid.uuid4()),project=job_events.project_key(self.root),stage='experiments',kind='operational',state='Running',started_at=self.at,observed_at=self.at,finished_at=None,exit_code=None,pid=123,process_identity='123-456')
        (folder/'00.json').write_text(json.dumps(value), encoding='utf-8')
        self.assertEqual(job_events.read_jobs(self.root, [], folder)['jobs'][0]['state'], 'Process not verified')
        self.assertEqual(job_events.read_jobs(self.root, [dict(identity='123-456')], folder)['jobs'][0]['state'], 'Running')

    def test_process_directory_must_be_present_and_absolute(self):
        self.assertFalse(process_watch.project_path('', Path.cwd()))
        self.assertFalse(process_watch.project_path('.', Path.cwd()))

    @unittest.skipUnless(os.name == 'nt', 'Native process observation requires Windows')
    def test_actual_native_process_is_project_bound(self):
        child = subprocess.Popen([sys.executable, '-B', '-c', 'import time; time.sleep(10)'], cwd=self.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: child.poll() is None and child.kill())
        try:
            result = process_watch.observe(self.root, exclude_pids=set())
            row = next(item for item in result['processes'] if item['pid'] == child.pid)
            self.assertEqual(row['state'], 'Process observed')
            self.assertEqual(row['stage'], 'unclassified')
            self.assertIsNotNone(row['started_at'])
            self.assertNotIn('command', row)
        finally:
            child.kill(); child.wait(timeout=3)


if __name__ == '__main__': unittest.main()
