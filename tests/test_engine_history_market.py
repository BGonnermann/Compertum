"""History markets (30 October 2026): years of one symbol's daily closes from retained Alpaca evidence, any ticker, up to MAX_SESSIONS.

Product lane, no sandbox. The envelopes are built like the provider-snapshot fixtures, for one symbol outside the paper universe.
"""
from datetime import datetime,time,timezone
import hashlib
import json
import pytest
from test_provider_snapshot import build,encode,envelopes  # noqa: F401  (fixture)
from compertum.ai.engine import history_market,real_market
from compertum.ai.engine.history_market import MIN_HISTORY_SESSIONS
from compertum.ai.engine.market import MAX_SESSIONS
from compertum.data.alpaca import SYMBOLS,read_bar_evidence
from compertum.data.calendar import NY,session_times
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused

SYMBOL='QQQ'


def sessions_from(start,count):
    out=[start]
    while len(out)<count: out.append(session_times(out[-1]).next_date)
    return out


def envelope(symbol,days,closes,*,adjustment='split',feed='sip',ident=None,start=None,end=None):
    start=start or days[0];end=end or days[-1]
    params={'symbols':symbol,'start':start+'T00:00:00Z','end':end+'T23:59:59Z','timeframe':'1Day','adjustment':adjustment,'feed':feed,'asof':end,'sort':'asc','currency':'USD','limit':100}
    bars=[{'t':datetime.combine(datetime.fromisoformat(day).date(),time(),NY).astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
           'o':close,'h':close+1,'l':close-1,'c':close,'v':1000,'n':10,'vw':close} for day,close in zip(days,closes)]
    pages=[]
    for index in range(0,max(len(bars),1),100):
        number=index//100;chunk=bars[index:index+100];token=str(number+1) if index+100<len(bars) else None
        raw=json.dumps({'bars':{symbol:chunk} if chunk else {},'next_page_token':token},separators=(',',':'))
        sent=dict(params)
        if number: sent['page_token']=str(number)
        pages.append({'request_id':ident or f'{symbol}-{start[:4]}','page':number,'params':sent,'status':200,'started_utc':f'2026-10-30T14:{number:02}:00Z',
                      'received_utc':f'2026-10-30T14:{number:02}:01Z','body_utf8':raw,'body_sha256':hashlib.sha256(raw.encode()).hexdigest()})
    return {'schema_version':'alpaca-bars-v1','host':'https://data.alpaca.markets','requests':[{'id':ident or f'{symbol}-{start[:4]}','path':'/v2/stocks/bars','params':params}],'pages':pages}


def project(tmp_path,chunks,*,symbol=SYMBOL,adjustment='split',feed='sip'):
    folder=tmp_path/'data'/'history'/symbol;folder.mkdir(parents=True);records=[]
    for index,value in enumerate(chunks):
        raw=encode(value);(folder/f'{index}.json').write_bytes(raw);records.append({'path':f'data/history/{symbol}/{index}.json','sha256':hashlib.sha256(raw).hexdigest()})
    manifest={'schema_version':'1','kind':'history','symbol':symbol,'feed':feed,'adjustment':adjustment,'chunks':records}
    (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return tmp_path,f'data/history/{symbol}/manifest.json'


@pytest.fixture(scope='module')
def history_days():
    days=sessions_from('2023-01-03',120);closes=[100+i*0.5+(i%7) for i in range(120)]
    return days,closes


def test_the_evidence_reader_accepts_any_ticker_only_when_asked(history_days):
    days,closes=history_days;raw=encode(envelope(SYMBOL,days[:50],closes[:50]))
    with pytest.raises(DataError,match='^PROVIDER_PROFILE$'): read_bar_evidence(raw)
    assert len(read_bar_evidence(raw,universe=None).rows)==50 and SYMBOL not in SYMBOLS
    with pytest.raises(DataError,match='^PROVIDER_PROFILE$'): read_bar_evidence(encode(envelope('qqq',days[:50],closes[:50])),universe=None)
    with pytest.raises(DataError,match='^PROVIDER_PROFILE$'): read_bar_evidence(encode(envelope('TOOLONGX',days[:50],closes[:50])),universe=None)
    assert len(read_bar_evidence(encode(envelope('BRK.B',days[:50],closes[:50])),universe=None).rows)==50


def test_a_history_manifest_builds_a_market_from_every_retained_session(tmp_path,history_days):
    days,closes=history_days
    root,path=project(tmp_path,[envelope(SYMBOL,days[:60],closes[:60]),envelope(SYMBOL,days[60:],closes[60:])])
    market,vault=real_market.load_market_manifest(root,path)
    assert market['provenance']['symbol']==SYMBOL and market['provenance']['sessions_available']==119 and market['provenance']['financial_accepted'] is False
    assert market['provenance']['market_start']==days[1] and market['provenance']['market_end']==days[-1] and len(market['provenance']['chunks_sha256'])==2
    assert market['label'].startswith(f'history alpaca/sip {SYMBOL}, {days[1]} to {days[-1]}, 119 sessions') and market['vault_sessions']==len(vault)
    train=market['train_csv'].splitlines();assert train[0]=='session,close,return' and train[1].startswith(days[1]+',')
    assert len(train)-1+len(market['validation_rows'])+len(vault)==119
    shorter,_=real_market.load_market_manifest(root,path,sessions=MIN_HISTORY_SESSIONS);assert shorter['provenance']['market_end']==days[-1] and 'sessions' in shorter['label']
    assert history_market.history_market({'symbol':SYMBOL,'feed':'sip','adjustment':'split','chunks_sha256':[],'closes':[(d,str(c)) for d,c in zip(days,closes)]})[0]['provenance']['sessions_available']==119


def test_history_refusals(tmp_path,history_days):
    days,closes=history_days
    root,path=project(tmp_path,[envelope(SYMBOL,days[:60],closes[:60]),envelope(SYMBOL,days[60:],closes[60:])])
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_COVERAGE_INCOMPLETE$'): real_market.load_market_manifest(root,path,sessions=200)
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): real_market.load_market_manifest(root,path,sessions=MIN_HISTORY_SESSIONS-1)
    manifest_path=root/path;manifest=json.loads(manifest_path.read_text())
    manifest['adjustment']='raw';manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_MANIFEST_INVALID$'): real_market.load_market_manifest(root,path)
    manifest['adjustment']='split';manifest['chunks'][0]['sha256']='0'*64;manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_EVIDENCE_CHANGED$'): real_market.load_market_manifest(root,path)
    gap=days[:60]+days[61:];gap_closes=closes[:60]+closes[61:]
    root2,path2=project(tmp_path/'gap',[envelope(SYMBOL,gap,gap_closes,start=days[0],end=days[-1])])
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_COVERAGE_INCOMPLETE$'): real_market.load_market_manifest(root2,path2)
    root3,path3=project(tmp_path/'dup',[envelope(SYMBOL,days[:60],closes[:60]),envelope(SYMBOL,days[59:],closes[59:])])
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_MANIFEST_INVALID$'): real_market.load_market_manifest(root3,path3)
    root4,path4=project(tmp_path/'short',[envelope(SYMBOL,days[:MIN_HISTORY_SESSIONS],closes[:MIN_HISTORY_SESSIONS])])
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_COVERAGE_INCOMPLETE$'): real_market.load_market_manifest(root4,path4)


def test_provider_markets_may_now_reach_the_calibrated_length(envelopes):
    snapshot=build(envelopes)
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_COVERAGE_INCOMPLETE$'): real_market.provider_market(snapshot,'AAPL',sessions=MAX_SESSIONS)
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): real_market.provider_market(snapshot,'AAPL',sessions=MAX_SESSIONS+1)
    assert real_market.provider_market(snapshot,'AAPL',sessions=MIN_HISTORY_SESSIONS)[0]['provenance']['symbol']=='AAPL'
