"""Manually open or start this local Hub. Never take another program's port."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import webbrowser

from job_events import project_key

ROOT = Path(__file__).resolve().parents[1]


def probe(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/identity',timeout=2) as response:
            raw=response.read(4097)
        value=json.loads(raw) if len(raw)<=4096 else None
        return 'matching' if value==dict(app='Compertum Hub',project=project_key(ROOT),protocol=1) else 'other'
    except HTTPError: return 'other'
    except URLError as error:
        return 'absent' if isinstance(error.reason,ConnectionRefusedError) else 'other'
    except (ValueError,TimeoutError,OSError): return 'other'


def serve(port,open_browser):
    from server import main
    prior=sys.argv
    try:
        sys.argv=['server.py','--project-root',str(ROOT),'--port',str(port)]+(['--open-browser'] if open_browser else [])
        return main()
    finally: sys.argv=prior


def start(port=8767,open_browser=True):
    state=probe(port)
    if state=='matching':
        if open_browser: webbrowser.open(f'http://127.0.0.1:{port}/#loop')
        return 0
    if state=='other':
        print('Another program uses the Hub port, or its identity could not be checked. Nothing was stopped.',file=sys.stderr)
        return 1
    return serve(port,open_browser)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Open the local read-only Compertum Hub.')
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    if not 1<=args.port<=65535: parser.error('The port must be between 1 and 65535.')
    raise SystemExit(start(args.port,not args.no_browser))
