"""Reporting uses existing committed records without changing their files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import unittest
import uuid
from unittest.mock import patch
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from runtime_records import RuntimeReader, directory_project_id
    from journal_snapshot import open_snapshot, SnapshotUnavailable
    from activity_labels import worker_stage
except ImportError:
    RuntimeReader = open_snapshot = worker_stage = None
    SnapshotUnavailable = ValueError


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(RuntimeReader, 'The passive runtime reader must exist')
        self.base = Path(__file__).resolve().parents[2] / '.cache/test-runs/hub-reporting-20261017'
        self.base.mkdir(parents=True, exist_ok=True)
        self.root = self.base / uuid.uuid4().hex
        (self.root / 'state/locks').mkdir(parents=True)
        self.addCleanup(self.cleanup)
        self.path = self.root / 'state/research.sqlite'
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE baseline_runs(run_id TEXT PRIMARY KEY,body TEXT);")
        self.db.executemany('INSERT INTO metadata VALUES (?,?)', [('schema_version','1'),('project_id',directory_project_id(self.root)),('role','coordinator')])
        self.db.commit()

    def cleanup(self):
        target = self.root.resolve()
        self.assertEqual(target.parent, self.base.resolve())
        shutil.rmtree(target)

    def record(self, state='RUNNING'):
        self.db.execute('INSERT OR REPLACE INTO baseline_runs VALUES (?,?)', ('run-one', json.dumps(dict(state=state,updated_at=datetime.now(timezone.utc).isoformat(),private='never-display-this', account='secret-account'))))
        self.db.commit()

    def fingerprints(self):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.parent.iterdir() if p.is_file()}

    def test_reads_committed_wal_without_any_original_write(self):
        self.record('BLOCKED'); before = self.fingerprints()
        with open_snapshot(self.root, self.path) as db:
            self.assertEqual(db.execute("SELECT json_extract(body,'$.state') FROM baseline_runs").fetchone()[0], 'BLOCKED')
            with self.assertRaises(sqlite3.Error): db.execute('DELETE FROM baseline_runs')
        self.assertEqual(before, self.fingerprints())

    def test_uncommitted_record_is_not_reported(self):
        self.record('PAUSED')
        self.db.execute('UPDATE baseline_runs SET body=?', (json.dumps(dict(state='COMPLETED')),))
        with open_snapshot(self.root, self.path) as db:
            self.assertEqual(db.execute("SELECT json_extract(body,'$.state') FROM baseline_runs").fetchone()[0], 'PAUSED')

    def test_saved_running_is_not_current_activity(self):
        self.record()
        result = RuntimeReader(self.root, roots=[self.root]).snapshot([])
        stage = next(s for s in result['stages'] if s['id']=='experiments')
        self.assertEqual(stage['records'][0]['state'], 'Saved running; current activity unconfirmed')
        self.assertNotIn('never-display-this', json.dumps(result))
        self.assertNotIn('secret-account', json.dumps(result))

    def test_missing_journals_and_unimplemented_producers_are_explicit(self):
        result = RuntimeReader(self.root, roots=[self.root]).snapshot([])
        self.assertEqual(len(result['stages']),17)
        feedback = next(s for s in result['stages'] if s['id']=='feedback')
        self.assertEqual(feedback['connection'], 'Reporting not implemented')
        self.assertTrue(any(j['status']=='Missing journal' for j in result['runtimes'][0]['journals']))

    def test_project_identity_mismatch_is_refused(self):
        (self.root/'state/locks/coordinator.json').write_text(json.dumps(dict(project_id='b'*64)),encoding='utf-8')
        result = RuntimeReader(self.root, roots=[self.root]).snapshot([])
        self.assertTrue(any(j['status']=='Identity mismatch' for j in result['runtimes'][0]['journals']))
        self.assertFalse(any(s['records'] for s in result['stages']))

    def test_partial_wal_header_is_unavailable(self):
        self.db.close()
        self.path.with_name(self.path.name+'-wal').write_bytes(b'partial')
        with self.assertRaises(SnapshotUnavailable): open_snapshot(self.root,self.path)

    def test_linked_database_is_refused(self):
        self.db.close()
        linked=self.root/'state/linked.sqlite'; os.link(self.path,linked)
        with self.assertRaises(SnapshotUnavailable): open_snapshot(self.root,self.path)

    def test_restore_in_progress_is_not_presented_as_connected(self):
        (self.root/'state/restore-operation.json').write_text('{"status":"PREPARING"}',encoding='utf-8')
        result=RuntimeReader(self.root,roots=[self.root]).snapshot([])
        self.assertEqual(result['runtimes'][0]['status'],'Restore in progress; records uncertain')

    def test_native_workers_use_exact_executed_modules(self):
        self.assertEqual(worker_stage('python.exe -B -m compertum.runtime.campaign_worker 123 456'),'experiments')
        self.assertEqual(worker_stage('python.exe -B -m compertum.runtime.campaign_worker final 123'),'final_evaluation')
        self.assertEqual(worker_stage('python.exe -B -m compertum.runtime.audit_worker final_audit 123'),'independent_audit')
        self.assertIsNone(worker_stage('python.exe -c "print(\'compertum.runtime.audit_worker\')"'))
        self.assertIsNone(worker_stage('Get-Content compertum.runtime.audit_worker'))

    def test_generation_path_escape_is_refused(self):
        (self.root/'state/active-generation.json').write_text(json.dumps(dict(schema_version=1,project_id='a'*64,generation='../escape',operation_id=str(uuid.uuid4()))),encoding='utf-8')
        result=RuntimeReader(self.root,roots=[self.root]).snapshot([])
        self.assertEqual(result['runtimes'][0]['status'],'Generation pointer invalid')

    def test_source_without_timestamp_keeps_it_missing(self):
        self.db.execute('CREATE TABLE ai_tasks(task_id TEXT,status TEXT)')
        self.db.execute("INSERT INTO ai_tasks VALUES ('proposal-one','PENDING')"); self.db.commit()
        result=RuntimeReader(self.root,roots=[self.root]).snapshot([])
        row=next(s for s in result['stages'] if s['id']=='proposals')['records'][0]
        self.assertIsNone(row['source_at'])

    def test_changed_bytes_are_refused_instead_of_guessed(self):
        from journal_snapshot import read_regular
        calls=0
        def changing(root,path,maximum):
            nonlocal calls
            value=read_regular(root,path,maximum); calls+=1
            return value+b'x' if calls==3 else value
        with patch('journal_snapshot.read_regular',side_effect=changing):
            with self.assertRaises(SnapshotUnavailable): open_snapshot(self.root,self.path)

    def test_reader_does_not_use_views_or_unknown_state_text(self):
        self.db.execute('CREATE TABLE audit_runs(task_id TEXT,body TEXT)')
        self.db.execute('INSERT INTO audit_runs VALUES (?,?)',('audit-one','{"state":"secret-account"}')); self.db.commit()
        result=RuntimeReader(self.root,roots=[self.root]).snapshot([])
        self.assertNotIn('secret-account',json.dumps(result))

    def test_worker_observation_is_connected_without_acceptance(self):
        import loop
        activity=dict(processes=[dict(kind='stage_worker',stage='experiments',pid=123,identity='123-456',scope='Test runtime')],jobs=[],reporting=RuntimeReader(self.root,roots=[self.root]).snapshot([]))
        stage=next(s for s in loop.build_loop(activity)['stages'] if s['id']=='experiments')
        self.assertEqual(stage['state'],'Worker observed')
        self.assertEqual(stage['worker_observations'][0]['scope'],'Test runtime')

    def test_future_record_time_is_not_exported(self):
        self.db.execute('INSERT INTO baseline_runs VALUES (?,?)',('future','{"state":"COMPLETED","updated_at":"2999-01-01T00:00:00Z"}'));self.db.commit()
        result=RuntimeReader(self.root,roots=[self.root]).snapshot([])
        row=next(s for s in result['stages'] if s['id']=='experiments')['records'][0]
        self.assertIsNone(row['source_at'])

    def test_copied_runtime_identity_cannot_bind_to_another_root(self):
        self.record();self.db.close()
        copied=self.root/'copied';(copied/'state').mkdir(parents=True)
        shutil.copy2(self.path,copied/'state/research.sqlite')
        result=RuntimeReader(copied,roots=[copied]).snapshot([])
        self.assertEqual(result['runtimes'][0]['journals'][0]['status'],'Identity mismatch')
        self.assertFalse(any(stage['records'] for stage in result['stages']))

    def test_real_final_dispatch_and_closure_shapes_are_projected(self):
        self.db.executescript('CREATE TABLE final_dispatches(attempt_id TEXT,body TEXT);CREATE TABLE final_closures(attempt_id TEXT,body TEXT);')
        at=datetime.now(timezone.utc).isoformat()
        self.db.execute('INSERT INTO final_dispatches VALUES (?,?)',('one',json.dumps(dict(attempt=dict(started_at=at)))))
        self.db.execute('INSERT INTO final_closures VALUES (?,?)',('two','{"mode":"BLOCKED","publication":null}'));self.db.commit()
        records=next(s for s in RuntimeReader(self.root,roots=[self.root]).snapshot([])['stages'] if s['id']=='final_evaluation')['records']
        self.assertTrue(any(row['source_at']==at for row in records))
        self.assertTrue(any(row['state']=='Saved: blocked' and row['source_at'] is None for row in records))

    def test_real_scalar_risk_values_keep_their_meaning(self):
        # The execution table shape is the same; use a separate role fixture.
        self.db.close()
        self.path.rename(self.root/'state/execution.sqlite')
        self.db=sqlite3.connect(self.root/'state/execution.sqlite');self.addCleanup(self.db.close)
        self.db.execute("UPDATE metadata SET value='execution' WHERE key='role'")
        self.db.execute('CREATE TABLE state(key TEXT,value TEXT)')
        self.db.executemany('INSERT INTO state VALUES (?,?)',[('admission','"HALTED"'),('armed','false')]);self.db.commit()
        records=next(s for s in RuntimeReader(self.root,roots=[self.root]).snapshot([])['stages'] if s['id']=='risk')['records']
        self.assertTrue(any(row['state']=='Saved: halted' for row in records))
        self.assertTrue(any(row['state']=='Saved: disarmed' for row in records))

    def test_partial_wal_tail_keeps_only_committed_pages(self):
        from journal_snapshot import committed_image
        self.record('BLOCKED')
        image,partial=committed_image(self.path.read_bytes(),self.path.with_name(self.path.name+'-wal').read_bytes()+b'partial')
        self.assertTrue(partial)
        with sqlite3.connect(':memory:') as db:
            db.deserialize(image)
            self.assertEqual(db.execute("SELECT json_extract(body,'$.state') FROM baseline_runs").fetchone()[0],'BLOCKED')

if __name__=='__main__': unittest.main()
