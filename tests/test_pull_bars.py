"""tools/pull_bars.py against a local bars server: one envelope per year, never replaced, the manifest loads, no secret leaves the headers."""
from datetime import datetime,time,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from urllib.parse import parse_qs,urlparse
import pytest
from compertum.ai.engine.real_market import load_market_manifest
from compertum.data.calendar import NY,session_times

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import pull_bars  # noqa: E402

KEY='test-key-id-1234';SECRET='test-secret-5678'


def sessions_of(year):
    out=[];day=f'{year}-01-01'
    while day[:4]==str(year):
        try: session_times(day);out.append(day)
        except Exception: pass
        day=(datetime.fromisoformat(day)+__import__('datetime').timedelta(days=1)).date().isoformat()
    return out


class Server:
    def __enter__(self):
        state={'requests':[],'bad_auth':0}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                url=urlparse(self.path);query={k:v[0] for k,v in parse_qs(url.query).items()};state['requests'].append((url.path,query))
                if self.headers.get('APCA-API-KEY-ID')!=KEY or self.headers.get('APCA-API-SECRET-KEY')!=SECRET:
                    state['bad_auth']+=1;self.send_response(403);self.end_headers();return
                year=int(query['start'][:4]);days=sessions_of(year);symbol=query['symbols'];page=int(query.get('page_token','0'))
                bars=[{'t':datetime.combine(datetime.fromisoformat(d).date(),time(),NY).astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
                       'o':100+i,'h':101+i,'l':99+i,'c':100.5+i,'v':1000,'n':5,'vw':100.25+i} for i,d in enumerate(days)]
                chunk=bars[page*100:(page+1)*100];token=str(page+1) if (page+1)*100<len(bars) else None
                raw=json.dumps({'bars':{symbol:chunk},'next_page_token':token}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        return self.server.server_address[1],state
    def __exit__(self,*args): self.server.shutdown();self.server.server_close()


def test_pull_writes_one_envelope_per_year_and_a_loadable_manifest(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(pull_bars,'PAUSE_SECONDS',0.0)
    creds=tmp_path/'env';creds.write_text(f'# owner file\nother=1\nalpaca_key="{KEY}"\nalpaca_secret={SECRET}\n',encoding='utf-8')
    out=tmp_path/'history'
    with Server() as (port,state):
        code=pull_bars.main(['--symbols','qqq','--start','2023','--end','2023','--credentials',str(creds),'--out',str(out),'--host',f'http://127.0.0.1:{port}'])
        printed=capsys.readouterr().out;summary=json.loads(printed)
        assert code==0 and state['bad_auth']==0 and len(state['requests'])==3 and all(q['feed']=='sip' and q['adjustment']=='split' and q['limit']=='100' for _,q in state['requests'])
        assert KEY not in printed and SECRET not in printed
        record=summary['symbols'][0];assert record['symbol']=='QQQ' and record['requests']==3 and record['years']['2023']['missing']==0
        envelope=json.loads((out/'QQQ'/'2023.json').read_bytes());assert envelope['schema_version']=='alpaca-bars-v1' and len(envelope['pages'])==3
        assert KEY not in (out/'QQQ'/'2023.json').read_text(encoding='utf-8') and 'APCA' not in (out/'QQQ'/'2023.json').read_text(encoding='utf-8')
        market,_=load_market_manifest(ROOT,record['market']['manifest'])
        assert market['provenance']['symbol']=='QQQ' and market['provenance']['sessions_available']==record['market']['sessions_available']==len(sessions_of(2023))-1
        again=pull_bars.main(['--symbols','QQQ','--start','2023','--end','2023','--credentials',str(creds),'--out',str(out),'--host',f'http://127.0.0.1:{port}'])
        assert again==0 and len(state['requests'])==3 and json.loads(capsys.readouterr().out)['symbols'][0]['years']['2023']=='kept'
    assert pull_bars.main(['--symbols','QQQ','--start','2023','--end','2024','--credentials',str(creds),'--out',str(out)])==2
    assert json.loads(capsys.readouterr().out)=={'refused':'ARGUMENTS'}
    (tmp_path/'noenv').write_text('alpaca_key=only\n',encoding='utf-8')
    assert pull_bars.main(['--symbols','QQQ','--start','2023','--end','2023','--credentials',str(tmp_path/'noenv'),'--out',str(out)])==2
    assert json.loads(capsys.readouterr().out)=={'refused':'CREDENTIAL_ENTRIES_MISSING'}
    assert pull_bars.main(['--symbols','QQQ','--start','2023','--end','2023','--credentials',str(creds),'--out',str(tmp_path/'history2'),'--dry-run'])==0
    assert json.loads(capsys.readouterr().out)['symbols'][0]['years']['2023']=='would fetch' and not (tmp_path/'history2'/'QQQ'/'2023.json').exists()
