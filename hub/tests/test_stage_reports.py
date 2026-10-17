"""Stage reporters describe separately authorized work. They never start it."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    import stage_reporting as reporting
except ImportError: reporting=None


class StageReportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(reporting,'The four stage reporters must exist')
        self.base=Path(__file__).resolve().parents[2]/'.cache/test-runs/hub-four-stage-20261017'
        self.base.mkdir(parents=True,exist_ok=True)
        self.root=self.base/uuid.uuid4().hex;self.root.mkdir()
        self.folder=self.root/'reports'
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.assertEqual(self.root.resolve().parent,self.base.resolve());shutil.rmtree(self.root)

    def read(self,processes=()): return reporting.read_reports(self.root,list(processes),self.folder)

    def test_four_stages_wait_for_real_reports(self):
        result=self.read()
        self.assertEqual(set(result['stages']),{'mathematics','qualification','signals','feedback'})
        self.assertTrue(all(row['status']=='No report received' for row in result['stages'].values()))
        self.assertFalse(self.folder.exists())

    def test_each_reporter_keeps_only_its_allowed_numeric_progress(self):
        for stage,metric in [('mathematics','checks_completed'),('qualification','checks_passed'),('signals','signals_count'),('feedback','items_reviewed')]:
            with reporting.StageReport(self.root,stage,folder=self.folder) as report: report.update(**{metric:2})
            row=self.read()['stages'][stage]['reports'][0]
            self.assertEqual(row['state'],'Completed');self.assertEqual(row['metrics'][metric],2)
            self.assertEqual(row['kind'],'engineering')

    def test_running_requires_current_native_identity(self):
        identity=f'{os.getpid()}-456'
        with patch.object(reporting,'current_identity',return_value=identity):
            with reporting.StageReport(self.root,'mathematics',folder=self.folder):
                self.assertEqual(self.read()['stages']['mathematics']['reports'][0]['state'],'Process not verified')
                row=self.read([dict(identity=identity)])['stages']['mathematics']['reports'][0]
                self.assertEqual(row['state'],'Running')

    def test_exception_is_preserved_and_never_serialized(self):
        with self.assertRaisesRegex(RuntimeError,'private fixture'):
            with reporting.StageReport(self.root,'feedback',folder=self.folder): raise RuntimeError('private fixture')
        result=self.read();self.assertNotIn('private fixture',json.dumps(result))
        self.assertEqual(result['stages']['feedback']['reports'][0]['state'],'Failed')

    def test_blocked_and_no_signal_are_not_success(self):
        with reporting.StageReport(self.root,'signals',folder=self.folder) as report: report.finish('No signal')
        self.assertEqual(self.read()['stages']['signals']['reports'][0]['state'],'No signal')
        with reporting.StageReport(self.root,'qualification',folder=self.folder) as report: report.finish('Blocked')
        self.assertEqual(self.read()['stages']['qualification']['reports'][0]['state'],'Blocked')

    def test_reporting_failure_does_not_abort_the_work(self):
        self.folder.mkdir();self.folder.joinpath('mathematics-00.json').write_text('retained',encoding='utf-8')
        with patch.object(reporting,'SLOTS',1):
            reached=False
            with reporting.StageReport(self.root,'mathematics',folder=self.folder) as report: reached=True
            self.assertTrue(reached);self.assertFalse(report.available)
        self.assertEqual(self.folder.joinpath('mathematics-00.json').read_text(),'retained')

    def test_unknown_fields_and_sensitive_metrics_are_rejected(self):
        with reporting.StageReport(self.root,'qualification',folder=self.folder) as report:
            with self.assertRaises(ValueError): report.update(account='private fixture')
            with self.assertRaises(ValueError): report.update(checks_passed=True)
        self.assertNotIn('private fixture',json.dumps(self.read()))

    def test_finished_receipts_are_preserved_between_jobs(self):
        for _ in range(2):
            with reporting.StageReport(self.root,'feedback',folder=self.folder): pass
        self.assertEqual(len(self.read()['stages']['feedback']['reports']),2)

    def test_stale_heartbeat_does_not_show_running(self):
        identity=f'{os.getpid()}-456'
        with patch.object(reporting,'current_identity',return_value=identity):
            with reporting.StageReport(self.root,'signals',folder=self.folder):
                path=next(self.folder.glob('signals-*.json'));value=json.loads(path.read_text())
                old=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat()
                value.update(started_at=old,observed_at=old);path.write_text(json.dumps(value),encoding='utf-8')
                self.assertEqual(self.read([dict(identity=identity)])['stages']['signals']['reports'][0]['state'],'Stale observation')

    def test_copied_report_project_identity_is_refused(self):
        with reporting.StageReport(self.root,'mathematics',folder=self.folder): pass
        other=self.root/'other';other.mkdir()
        result=reporting.read_reports(other,[],self.folder)
        self.assertEqual(result['stages']['mathematics']['status'],'Invalid or incomplete reports')
        self.assertEqual(result['stages']['mathematics']['reports'],[])

    def test_reading_does_not_change_receipt_bytes(self):
        with reporting.StageReport(self.root,'signals',folder=self.folder): pass
        before={p.name:p.read_bytes() for p in self.folder.iterdir()};self.read()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.folder.iterdir()})

    def test_engineering_stage_job_is_visible_in_its_stage(self):
        import loop
        result=loop.build_loop(dict(processes=[],jobs=[dict(stage='feedback',kind='engineering',state='Running',run_id='x',observed_at='2026-10-17T00:00:00Z')]))
        stage=next(s for s in result['stages'] if s['id']=='feedback')
        self.assertEqual(stage['state'],'Engineering: running')

    def test_old_job_completion_does_not_hide_a_current_report(self):
        import loop
        activity=dict(processes=[],jobs=[dict(stage='signals',kind='operational',state='Completed',observed_at='2026-10-16T00:00:00Z')],stage_reports=dict(stages=dict(signals=dict(status='Stage reporting connected',reports=[dict(kind='engineering',state='Running',observed_at='2026-10-17T00:00:00Z')]))))
        stage=next(s for s in loop.build_loop(activity)['stages'] if s['id']=='signals')
        self.assertEqual(stage['state'],'Engineering: running')

    def test_wrapper_reports_an_actual_child_exit_in_an_isolated_feed(self):
        command=[sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'run_job.py'),'--project-root',str(self.root),'--event-folder',str(self.root/'jobs'),'--stage','mathematics','--',sys.executable,'-B','-c','assert sum((1,2,3)) == 6']
        reply=subprocess.run(command,capture_output=True,timeout=10)
        self.assertEqual(reply.returncode,0)
        row=reporting.read_reports(self.root,[],self.root/'stage-reports')['stages']['mathematics']['reports'][0]
        self.assertEqual(row['state'],'Completed');self.assertEqual(row['kind'],'engineering')
        self.assertNotEqual(row['pid'],os.getpid())

    def test_exception_after_a_declared_finish_still_reports_failure(self):
        with self.assertRaises(RuntimeError):
            with reporting.StageReport(self.root,'qualification',folder=self.folder) as report:
                report.finish();raise RuntimeError('private fixture')
        self.assertEqual(self.read()['stages']['qualification']['reports'][0]['state'],'Failed')

    def test_actual_native_reporter_has_a_current_heartbeat(self):
        code="""import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from stage_reporting import StageReport
root=Path.cwd()
with StageReport(root,'signals',folder=root/'reports') as report:
    report.update(items_checked=2,signals_count=1)
    deadline=time.monotonic()+7
    while not (root/'release').exists() and time.monotonic()<deadline: time.sleep(.05)
"""
        child=subprocess.Popen([sys.executable,'-B','-c',code,str(Path(__file__).resolve().parents[1])],cwd=self.root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+5;observed=[]
            while time.monotonic()<deadline:
                native=reporting.observe(self.root,exclude_pids=set())
                rows=self.read(native['processes'])['stages']['signals']['reports']
                if rows and rows[0]['state']=='Running':
                    observed.append(rows[0]['observed_at'])
                    if len(set(observed))>=2:break
                time.sleep(.08)
            self.assertGreaterEqual(len(set(observed)),2)
            self.root.joinpath('release').write_text('release',encoding='utf-8');child.wait(timeout=3)
            self.assertEqual(child.returncode,0)
            row=self.read()['stages']['signals']['reports'][0]
            self.assertEqual(row['state'],'Completed');self.assertEqual(row['metrics']['signals_count'],1)
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=3)

    def test_receipt_publish_failure_does_not_terminate_the_actual_job(self):
        import run_job
        original_open=Path.open
        def fail_pending(path,*args,**kwargs):
            if path.suffix=='.pending':raise PermissionError('private fixture')
            return original_open(path,*args,**kwargs)
        command=['run_job.py','--project-root',str(self.root),'--event-folder',str(self.root/'jobs'),'--stage','verification','--',sys.executable,'-B','-c',"import time;from pathlib import Path;time.sleep(.15);Path('work-completed').write_text('complete')"]
        with patch.object(sys,'argv',command),patch.object(Path,'open',new=fail_pending):
            code=run_job.main()
        self.assertEqual(code,0)
        self.assertTrue(self.root.joinpath('work-completed').is_file())

    def test_malformed_receipt_never_exposes_unknown_fields(self):
        with reporting.StageReport(self.root,'signals',folder=self.folder):pass
        path=next(self.folder.glob('signals-*.json'));value=json.loads(path.read_text())
        value['account']='private fixture';path.write_text(json.dumps(value),encoding='utf-8')
        result=self.read()
        self.assertEqual(result['stages']['signals']['status'],'Invalid or incomplete reports')
        self.assertNotIn('private fixture',json.dumps(result))

if __name__=='__main__':unittest.main()
