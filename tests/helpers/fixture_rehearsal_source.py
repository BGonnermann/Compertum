"""Original controlled source for the native rehearsal. All account values are invented."""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import RLock,Thread
from urllib.parse import parse_qs,urlparse
from zoneinfo import ZoneInfo
import hashlib,json,re,socket
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.paper_contracts import strict_json,utc
from compertum.paper_market_inputs import prepare_market_plan
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime._winhttp_order import _wire
from .fixture_order_peer import require_native_execution
from .stateful_economic_fixture import ControlledEconomicSource
from .stateful_order_fixture import ControlledOrderSource

NY=ZoneInfo('America/New_York');ROOT=Path(__file__).parents[2]
BID='89.875';ASK='90'
def need(value):
 if not value:raise RuntimeRefused('CONTROLLED_REHEARSAL_SOURCE_REFUSED')
def market_now():return datetime.now(timezone.utc)

def stamp():return utc(market_now().isoformat())

def clock_reply(now):
 need(type(now) is datetime and now.utcoffset() is not None)
 day=now.astimezone(NY).date();current=None;following=None
 try:current=session_times(day.isoformat());following=session_times(current.next_date)
 except DataError:
  for offset in range(1,15):
   try:following=session_times((day+timedelta(days=offset)).isoformat());break
   except DataError:continue
 need(following is not None)
 opened=current is not None and current.open<=now<current.close
 next_open=current.open if current is not None and now<current.open else following.open
 next_close=current.close if current is not None and now<current.close else following.close
 calendar=[] if current is None else [dict(date=day.isoformat(),open=current.open.astimezone(NY).strftime('%H:%M'),close=current.close.astimezone(NY).strftime('%H:%M'))]
 return dict(timestamp=now.isoformat(),is_open=opened,next_open=next_open.isoformat(),next_close=next_close.isoformat()),calendar

def write_header(header):
 need(type(header) is str)
 match=re.fullmatch(r'synthetic_(cmp-[0-9a-f]{40})_([0-9a-f]{64})_([0-9a-f]{64})',header)
 need(match is not None);return match[1],(match[2],match[3])

class OriginalSourceServer:
 def __init__(self,root,*,lose_buy_reply=False):
  need(root==ROOT/'.cache/test-runs/native-economic-fresh-20261017-01/native-shared')
  self.root=root;self.project=resolve_project(root);self.lock=RLock();self.supervisor=None;self.requests=[];self.errors=[];self.writes=[]
  self.lose_buy_reply=lose_buy_reply;self.lost=False;self._history=None
  records=ROOT/'artifacts/m5/native-economics-20261017-01'
  birth=json.loads((records/'original-source-birth01.json').read_text());order_birth=json.loads((records/'original-order-source-birth01.json').read_text())
  self.economic=ControlledEconomicSource.open(root/'state/fixture-economic-source.jsonl',stamp)
  try:
   need(self.project.project_id==birth['project_id'] and self.economic._producer==birth['producer_id'] and self.economic._genesis==birth['genesis_sha256'])
   self.orders=ControlledOrderSource.open(root/'state/fixture-order-source.jsonl',self.economic,stamp,
    lambda:verify_attempt_guard(self.project),lambda:(BID,ASK),lock=self.lock)
   need(hashlib.sha256(self.orders._raw.splitlines(keepends=True)[0]).hexdigest()==order_birth['origin_sha256'])
   app=self
   class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def handle_request(self):
     try:
      need(not any(k.lower().startswith('apca-') for k in self.headers))
      require_native_execution(root,self.client_address,self.server.server_address)
      with app.lock:
       need(len(app.requests)<128);app.requests.append(dict(method=self.command,path=self.path))
       if self.command=='GET':
        need(self.headers.get('X-Compertum-Test')=='synthetic');code,raw=200,canonical(app.read(self.path))
       else:
        client,heads=write_header(self.headers.get('X-Compertum-Test'))
        request=app.orders._record(client)['intent']['request'];method,target,body=_wire(request['operation'],request['parameters'],request['body'])
        need(self.command==method and self.path==target)
        length=int(self.headers.get('Content-Length','0'));need(0<=length<=8192);received=self.rfile.read(length)
        need(received==body and (not received or canonical(strict_json(received))==received))
        require_native_execution(root,self.client_address,self.server.server_address)
        code,raw=app.orders.execute(client_id=client,operation=request['operation'],parameters=request['parameters'],body=request['body'],expected_heads=heads)
        app.writes.append(dict(client_order_id=client,operation=request['operation']))
        if app.lose_buy_reply and not app.lost and request['operation']=='SUBMIT_ORDER' and request['body']['type']=='market' and request['body']['side']=='buy':
         app.lost=True;self.close_connection=True;self.connection.shutdown(socket.SHUT_RDWR);return
      self.send_response(code);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
     except (RuntimeRefused,ValueError,KeyError,OSError) as error:
      with app.lock:
       if len(app.errors)<32:app.errors.append(dict(error_type=type(error).__name__,reason=getattr(error,'code',None)))
      self.close_connection=True
    do_GET=do_POST=do_DELETE=handle_request
   class Server(ThreadingHTTPServer):
    allow_reuse_address=False;daemon_threads=True
    def server_bind(self):
     self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);super().server_bind()
   self.server=Server(('127.0.0.1',0),Handler);self.thread=Thread(target=self.server.serve_forever,daemon=True)
  except BaseException:
   if hasattr(self,'orders'):self.orders.close()
   self.economic.close();raise
 def read(self,target):
  url=urlparse(target);path=url.path;now=market_now()
  if path=='/v2/account':
   observed=self.orders.observations();snapshot=self.economic.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=stamp());orders=self.orders.snapshot()
   need(self.supervisor is not None);s=self.supervisor.supervisor
   peer=dict(project_id=self.project.project_id,generation=s.generation,identity=asdict(s.identity),logon_sid=self.project.logon_sid)
   equity=Decimal(observed['cash'])+sum((Decimal(p['qty'])*Decimal(ASK) for p in observed['positions']),Decimal(0))
   return dict(id='11111111-1111-4111-8111-111111111111',status='ACTIVE',currency='USD',cash=observed['cash'],equity=str(equity),buying_power='4000',
    trading_blocked=False,account_blocked=False,trade_suspended_by_user=False,
    compertum_fixture_source=dict(version=1,producer_id=snapshot['producer_id'],genesis_sha256=snapshot['genesis_sha256'],ledger=snapshot['ledger'],served_by=peer,
     order_source={k:orders[k] for k in ('producer_id','genesis_sha256','journal_sha256')}))
  if path in {'/v2/positions','/v2/orders','/v2/account/activities'}:
   observed=self.orders.observations();return observed[{'/v2/positions':'positions','/v2/orders':'orders','/v2/account/activities':'activities'}[path]]
  if path in {'/v2/clock','/v2/calendar'}:return clock_reply(now)[int(path=='/v2/calendar')]
  if path=='/v2/assets/MSFT':
   value=dict(id=self.economic._header['asset_id'],symbol='MSFT',exchange='NASDAQ',status='active',tradable=True);value['class']='us_equity';return value
  if path=='/v2/stocks/quotes/latest':return dict(quotes={'MSFT':dict(t=now.isoformat(),bp=float(BID),ap=float(ASK),bs=10,**{'as':20},bx='V',ax='V')})
  need(path=='/v2/stocks/bars')
  if self._history is None:
   plan=prepare_market_plan(project_id=self.project.project_id,account_alias='fixture',symbol='MSFT',session_date=now.astimezone(NY).date().isoformat(),created_at=now.isoformat()).to_payload()
   self._history=[dict(t=t,o=90,h=91,l=89,c=90,v=20000) for t in plan['daily_labels']]
  index=int(parse_qs(url.query).get('page_token',['0'])[0]);need(index in (0,1,2))
  return dict(bars={'MSFT':self._history[index*100:(index+1)*100]},next_page_token=str(index+1) if index<2 else None)
 def start(self):self.thread.start()
 def close(self):
  self.server.shutdown();self.server.server_close();self.thread.join(2);self.orders.close();self.economic.close()
