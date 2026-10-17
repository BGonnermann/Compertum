"""Read-only Hub contract checks. These do not run Compertum."""
import http.client
import json
from pathlib import Path
import shutil
import sys
import threading
import unittest
import uuid
import time

HUB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB))
try:
    import records
    import server
except ImportError:
    records = server = None

CURRENT = """# Current checkpoint

## Current declared-fee verification - 17 October 2026

**Declared-fee engineering is locally verified. The approved local finish plan remains incomplete.**
Source and installed inventories each passed 260 distinct cases, with zero failures, errors, or skips.
Each contains 258 in-process cases and two native Windows stages.
Actual billing coverage and unpaid liabilities remain unverified.
Next, implement posted fee observations under M5_POSTED_FEES_PLAN.md.
M5 gates 2 through 5 remain open. M6 remains zero of ten actual supervised sessions. Only M0 is fully accepted.
Strata stays off.

## Earlier failed checks

Source and installed checks each passed 900 distinct cases, with zero failures, errors, or skips.
Owner approval remains pending.
"""
SPEC = """# Build specification
| Milestone | Deliverable and measurable pass conditions | Deliberate failure checks |
| --- | --- | --- |
| M0: foundations | Repeatable environment | Reject wrong identity |
| M1: data | Reproducible data | Reject future input |
| M5: paper walkthrough | Separate account authority | Reject unclear outcome |
| M6: supervised sessions | Ten actual sessions | Detect gaps |
"""


class HubTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(records, 'The Hub record reader must exist')
        self.assertIsNotNone(server, 'The read-only server must exist')
        scratch = HUB.parent / '.cache' / 'test-runs' / 'compertum-hub-20261017'
        scratch.mkdir(parents=True, exist_ok=True)
        self.root = scratch / uuid.uuid4().hex
        self.root.mkdir()
        self.addCleanup(self.remove_fixture, scratch.resolve())
        (self.root / 'docs').mkdir()
        (self.root / 'reports').mkdir()
        (self.root / 'docs/CURRENT_CHECKPOINT.md').write_text(CURRENT, encoding='utf-8')
        (self.root / 'docs/BUILD_SPEC.md').write_text(SPEC, encoding='utf-8')
        self.store = records.RecordStore(self.root)

    def remove_fixture(self, parent):
        target = self.root.resolve()
        self.assertEqual(target.parent, parent)
        shutil.rmtree(target)

    def test_newest_section_excludes_historical_counts(self):
        snapshot = self.store.snapshot()
        self.assertIn('Declared-fee engineering', snapshot['checkpoint']['summary'])
        self.assertNotIn('900', snapshot['checkpoint']['text'])
        self.assertNotIn('approval remains pending', snapshot['checkpoint']['text'])
        self.assertEqual(snapshot['results']['source']['passed'], 260)
        self.assertEqual(snapshot['results']['installed']['passed'], 260)

    def test_summary_uses_only_the_first_current_line(self):
        self.assertEqual(self.store.snapshot()['checkpoint']['summary'], 'Declared-fee engineering is locally verified. The approved local finish plan remains incomplete.')

    def test_git_output_is_bounded_while_reading(self):
        result = records.read_command([sys.executable, '-B', '-c', 'import sys; sys.stdout.buffer.write(b"x" * (2 * 1024 * 1024))'])
        self.assertIsNone(result)

    def test_git_command_timeout_is_bounded(self):
        started = time.monotonic()
        result = records.read_command([sys.executable, '-B', '-c', 'import time; time.sleep(10)'], seconds=0.1)
        self.assertIsNone(result)
        self.assertLess(time.monotonic() - started, 3)

    def test_result_counts_and_breakdown_are_separate(self):
        result = self.store.snapshot()['results']
        self.assertEqual(result['source'], dict(passed=260, failed=0, errors=0, skipped=0))
        self.assertEqual(result['in_process'], 258)
        self.assertEqual(result['native_per_environment'], 2)
        self.assertEqual(result['source'], result['installed'])

    def test_original_source_and_fingerprint_are_present(self):
        record = self.store.read_record('docs/CURRENT_CHECKPOINT.md')
        self.assertEqual(record['text'], (self.root / 'docs/CURRENT_CHECKPOINT.md').read_bytes().decode('utf-8'))
        self.assertEqual(len(record['sha256']), 64)
        self.assertTrue(record['modified_at'].endswith('Z'))
        self.assertEqual(record['status'], 'available')

    def test_milestones_require_explicit_acceptance(self):
        rows = {row['id']: row for row in self.store.snapshot()['milestones']}
        self.assertEqual(rows['M0']['status'], 'Accepted')
        self.assertEqual(rows['M5']['status'], 'Not fully accepted')
        self.assertEqual(self.store.snapshot()['sessions'], dict(completed=0, required=10))

    def test_unsupported_counts_are_unavailable(self):
        (self.root / 'docs/CURRENT_CHECKPOINT.md').write_text('# Status\n\n## Current work\n\nChecks are underway.\n', encoding='utf-8')
        result = self.store.snapshot()
        self.assertIsNone(result['results']['source']['passed'])
        self.assertIsNone(result['sessions']['completed'])
        self.assertTrue(all(row['status'] == 'Unavailable' for row in result['milestones']))

    def test_missing_checkpoint_is_explicit(self):
        (self.root / 'docs/CURRENT_CHECKPOINT.md').unlink()
        result = self.store.snapshot()
        self.assertEqual(result['checkpoint']['status'], 'missing')
        self.assertIsNone(result['results']['source']['passed'])

    def test_oversized_record_is_refused(self):
        (self.root / 'docs/CURRENT_CHECKPOINT.md').write_bytes(b'x' * (records.MAX_RECORD_BYTES + 1))
        self.assertEqual(self.store.read_record('docs/CURRENT_CHECKPOINT.md')['status'], 'too_large')

    def test_invalid_utf8_is_refused(self):
        (self.root / 'docs/CURRENT_CHECKPOINT.md').write_bytes(b'\xff\xfe\x00')
        self.assertEqual(self.store.read_record('docs/CURRENT_CHECKPOINT.md')['status'], 'invalid')

    def test_path_traversal_and_private_files_are_refused(self):
        for path in ('../README.md', '.env', 'state/runtime.sqlite', 'docs/../.env', '/etc/passwd', 'docs\\CURRENT_CHECKPOINT.md', 'docs/%2e%2e/.env', 'C:/Windows/win.ini'):
            with self.subTest(path=path):
                self.assertEqual(self.store.read_record(path)['status'], 'not_allowed')

    def test_untracked_documents_are_not_published(self):
        (self.root / 'docs/private-note.md').write_text('private fixture', encoding='utf-8')
        self.assertEqual(self.store.read_record('docs/private-note.md')['status'], 'not_allowed')

    def test_directory_is_not_a_record(self):
        target = self.root / 'docs/CURRENT_CHECKPOINT.md'
        target.unlink(); target.mkdir()
        self.assertEqual(self.store.read_record('docs/CURRENT_CHECKPOINT.md')['status'], 'unreadable')

    def test_checkpoint_reads_refresh(self):
        before = self.store.snapshot()['checkpoint']['sha256']
        path = self.root / 'docs/CURRENT_CHECKPOINT.md'
        path.write_text(CURRENT.replace('260', '261'), encoding='utf-8')
        after = self.store.snapshot()
        self.assertNotEqual(before, after['checkpoint']['sha256'])
        self.assertEqual(after['results']['source']['passed'], 261)

    def start_server(self):
        httpd = server.make_server(self.store, port=0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd

    def request(self, httpd, path='/', method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
        connection.request(method, path, headers=headers or {})
        reply = connection.getresponse()
        result = (reply.status, dict(reply.getheaders()), reply.read())
        connection.close()
        return result

    def test_real_http_snapshot(self):
        status, headers, body = self.request(self.start_server(), '/api/snapshot')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['results']['source']['passed'], 260)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_http_record_is_plain_json_text(self):
        path = self.root / 'docs/CURRENT_CHECKPOINT.md'
        path.write_text(CURRENT + '\n<script>alert(1)</script>', encoding='utf-8')
        status, headers, body = self.request(self.start_server(), '/api/record?path=docs%2FCURRENT_CHECKPOINT.md')
        self.assertEqual(status, 200)
        self.assertTrue(headers['Content-Type'].startswith('application/json'))
        self.assertIn('<script>', json.loads(body)['text'])

    def test_http_write_methods_are_refused(self):
        httpd = self.start_server()
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
            with self.subTest(method=method):
                self.assertEqual(self.request(httpd, '/api/snapshot', method)[0], 405)

    def test_foreign_host_and_cross_origin_are_refused(self):
        httpd = self.start_server()
        for headers in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(httpd, '/api/snapshot', headers=headers)[0], 403)

    def test_http_paths_are_allowlisted(self):
        httpd = self.start_server()
        for path in ('/.env', '/api/record?path=..%2F.env', '/api/record?path=docs%252fCURRENT_CHECKPOINT.md', '/api/record?path=README.md&path=.env', '/../../.env', '/api/record'):
            with self.subTest(path=path):
                self.assertIn(self.request(httpd, path)[0], (400, 404))

    def test_page_assets_and_head(self):
        httpd = self.start_server()
        for path in ('/', '/app.js', '/style.css'):
            with self.subTest(path=path):
                status, headers, body = self.request(httpd, path)
                self.assertEqual(status, 200)
                self.assertGreater(len(body), 20)
                self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(self.request(httpd, '/', 'HEAD')[2], b'')

    def test_missing_map_is_explicit(self):
        self.store.map_pdf = self.root / 'absent.pdf'
        httpd = self.start_server()
        self.assertFalse(self.store.snapshot()['map']['available'])
        self.assertEqual(self.request(httpd, '/project-map.pdf')[0], 404)

    def test_map_route_serves_only_the_named_pdf(self):
        self.store.map_pdf = self.root / 'map.pdf'
        self.store.map_pdf.write_bytes(b'%PDF-1.4\nfixture')
        status, headers, body = self.request(self.start_server(), '/project-map.pdf')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/pdf')
        self.assertTrue(body.startswith(b'%PDF'))


if __name__ == '__main__':
    unittest.main()
