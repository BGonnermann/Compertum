"""Manually started, loopback-only Hub. Reads do not start Compertum."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
import threading
from urllib.parse import parse_qs, urlsplit

from records import DEFAULT_MAP, MAX_MAP_BYTES, RecordStore, regular_without_links
from live import LiveMonitor
from job_events import project_key

STATIC = Path(__file__).resolve().parent / 'static'
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}


def make_server(store, port=8767):
    monitor = LiveMonitor(store.root)
    class HubHandler(BaseHTTPRequestHandler):
        server_version = 'CompertumHub'
        sys_version = ''

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, format, *args):
            # Do not retain source contents, request paths or private query text.
            pass

        def trusted_request(self):
            port = self.server.server_port
            allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
            hosts = self.headers.get_all('Host', [])
            if len(hosts) != 1 or hosts[0] not in allowed:
                return False
            origin = self.headers.get('Origin')
            if origin is not None and origin != f'http://{hosts[0]}':
                return False
            return self.headers.get('Sec-Fetch-Site', 'none') in ('none', 'same-origin')

        def respond(self, status, content, content_type='application/json; charset=utf-8'):
            if not isinstance(content, bytes):
                content = json.dumps(content, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.send_header('Connection', 'close')
            if status == 405:
                self.send_header('Allow', 'GET, HEAD')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(content)
            self.close_connection = True

        def do_GET(self):
            if not self.trusted_request():
                return self.respond(403, {'error': 'Only this local Hub can read these records.'})
            if len(self.path) > 2048:
                return self.respond(400, {'error': 'The request is too long.'})
            try:
                address = urlsplit(self.path)
                if address.scheme or address.netloc or address.fragment:
                    return self.respond(400, {'error': 'Use a local Hub path.'})
                if address.path == '/api/snapshot' and not address.query:
                    return self.respond(200, store.snapshot())
                if address.path == '/api/live' and not address.query:
                    return self.respond(200, monitor.snapshot())
                if address.path == '/api/identity' and not address.query:
                    return self.respond(200, dict(app='Compertum Hub',project=project_key(store.root),protocol=1))
                if address.path == '/api/record':
                    query = parse_qs(address.query, strict_parsing=True, max_num_fields=1)
                    if set(query) != {'path'} or len(query['path']) != 1:
                        return self.respond(400, {'error': 'Choose one source record.'})
                    record = store.read_record(query['path'][0])
                    return self.respond(404 if record['status'] == 'not_allowed' else 200, record)
                if address.query:
                    return self.respond(404, {'error': 'This path is not available.'})
                if address.path in ASSETS:
                    name, mime = ASSETS[address.path]
                    return self.respond(200, (STATIC / name).read_bytes(), mime)
                if address.path == '/project-map.pdf':
                    if not store.map_info()['available']:
                        return self.respond(404, {'error': 'The saved project-map PDF is unavailable.'})
                    if not regular_without_links(store.map_pdf, store.map_pdf.parent):
                        return self.respond(404, {'error': 'The saved project-map PDF is unavailable.'})
                    with store.map_pdf.open('rb') as stream:
                        content = stream.read(MAX_MAP_BYTES + 1)
                    if len(content) > MAX_MAP_BYTES:
                        return self.respond(404, {'error': 'The saved project-map PDF exceeds its read limit.'})
                    return self.respond(200, content, 'application/pdf')
                return self.respond(404, {'error': 'This path is not available.'})
            except ValueError:
                return self.respond(400, {'error': 'The request is invalid.'})
            except (OSError, RuntimeError):
                return self.respond(503, {'error': 'The record could not be read. Retry shortly.'})

        do_HEAD = do_GET

        def refuse_write(self):
            self.respond(405, {'error': 'The Compertum Hub is read-only.'})

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = refuse_write

    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address = False
        daemon_threads = True
        slots = threading.BoundedSemaphore(4)

        def process_request(self, request, client_address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except Exception:
                self.slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.slots.release()

        def server_bind(self):
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

        def handle_error(self, request, client_address):
            # A disconnected browser is not a reason to write a traceback or a log.
            pass

    return LocalServer(('127.0.0.1', port), HubHandler)


def main():
    parser = argparse.ArgumentParser(description='Open the local read-only Compertum Hub.')
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--map-pdf', type=Path, default=DEFAULT_MAP)
    parser.add_argument('--open-browser', action='store_true', help='Open the Hub in the default browser.')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('The port must be between 1 and 65535.')
    try:
        httpd = make_server(RecordStore(args.project_root, args.map_pdf), args.port)
    except OSError:
        print('The Hub could not open its local port. Another program may be using it.', file=sys.stderr)
        return 1
    print(f'Compertum Hub: http://127.0.0.1:{httpd.server_port}', flush=True)
    print('Read-only project records. Press Ctrl+C in this terminal to stop the Hub.', flush=True)
    if args.open_browser:
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{httpd.server_port}')
    try:
        httpd.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
