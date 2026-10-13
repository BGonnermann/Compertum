"""Merge bounded synthetic snapshots and expose only cutoff-available features."""
from dataclasses import dataclass
from decimal import Decimal as D
import hashlib,json

from compertum.data.calendar import session_times,utc_time
from compertum.data.errors import DataError
from compertum.data.snapshot import Snapshot,validate_snapshot,canonical,_id

WATCHLIST=('AAPL','MSFT','AMZN','GOOGL','META','NVDA','JPM','XOM','JNJ','PG','UNH','HD')


@dataclass
class Market:
    symbols:tuple
    sectors:dict
    rows:dict
    actions:tuple
    sha256:str

    def trade_fee(self,day,quantity,price,side):return D(0)

    def replay_metadata(self):return {}

    def reference(self,symbol,day,reference):
        row=self.rows.get((symbol,day,reference))
        if row is None:raise DataError('MISSING_REFERENCE')
        final_cutoff=session_times(session_times(day).next_date).decision
        if max(utc_time(row['simulated_available_at']),utc_time(row['simulated_revision_available_at']))>final_cutoff:
            raise DataError('REFERENCE_UNAVAILABLE')
        return D(row['open' if reference=='entry' else 'close'])

    def liquidity(self,symbol,day):
        times=session_times(day);date=times.previous_date;values=[]
        for _ in range(20):
            row=self.rows.get((symbol,date,'daily'))
            if row is None or max(utc_time(row['simulated_available_at']),utc_time(row['simulated_revision_available_at']))>times.decision:
                raise DataError('LIQUIDITY_UNAVAILABLE')
            values.append(D(row['close'])*D(row['volume']));date=session_times(date).previous_date
        return sum(values)/20

    def features(self,symbol,day,horizon):
        times=session_times(day);date=times.previous_date;history=[]
        for _ in range(252):
            row=self.rows.get((symbol,date,'daily'))
            if row is None:return None,'FEATURE_COVERAGE'
            if max(utc_time(row['simulated_available_at']),utc_time(row['simulated_revision_available_at']))>times.decision:
                return None,'FEATURE_UNAVAILABLE'
            history.append(row);date=session_times(date).previous_date
        for a in self.actions:
            if a['symbol']==symbol and a['effective_session']<=day and utc_time(a['simulated_known_at'])>times.decision:
                return None,'ACTION_UNAVAILABLE'
        price=D(history[0]['close'])
        dollar_volume=sum(D(b['close'])*D(b['volume']) for b in history[:20])/20
        if price<5 or dollar_volume<D('1000000'):return None,'INELIGIBLE_PRICE_OR_VOLUME'
        factor=D(1)
        for a in self.actions:
            if a['symbol']==symbol and a['kind']=='SPLIT' and history[21]['session_date']<a['effective_session']<=history[0]['session_date']:
                factor*=D(a['factor'])
        prediction=D(horizon)*(price*factor/D(history[21]['close'])-1)/21
        return {'prediction':prediction,'dollar_volume':dollar_volume},None


def load_market(chunks,sectors):
    if not isinstance(chunks,(tuple,list)) or not 1<=len(chunks)<=64:raise DataError('INPUT_BOUND')
    if any(not isinstance(c,Snapshot) for c in chunks):raise DataError('INVALID_SNAPSHOT')
    if sum(len(c.content) for c in chunks)>16*1024*1024:raise DataError('INPUT_BOUND')
    rows={};assets={};reverse={};actions={};semantic={};hashes=[];source=None
    for chunk in chunks:
        verified=validate_snapshot(chunk.content)
        if verified!=chunk:raise DataError('SNAPSHOT_CORRUPT')
        v=json.loads(chunk.content);hashes.append(chunk.sha256)
        if source is None:source=v['source']
        if v['source']!=source:raise DataError('MIXED_SOURCE')
        for a in v['assets']:
            key=a['asset_id'];s=a['symbol']
            if s not in WATCHLIST+('SPY',) or assets.get(key,s)!=s or reverse.get(s,key)!=key:raise DataError('ASSET_MAPPING')
            assets[key]=s;reverse[s]=key
        for b in v['bars']:
            if b['adjustment']!='raw':continue
            key=(assets[b['asset_id']],b['session_date'],b['reference'])
            if key in rows:raise DataError('DUPLICATE_BAR')
            rows[key]=b
        for action in v['actions']:
            a=dict(action,symbol=assets[action['asset_id']]);key=a['action_id']
            if key in actions and actions[key]!=a:raise DataError('ACTION_CONFLICT')
            sk=(a['symbol'],a['effective_session'],a['kind'])
            if sk in semantic and semantic[sk]!=key:raise DataError('ACTION_CONFLICT')
            actions[key]=a;semantic[sk]=key
    symbols=tuple(sorted(reverse))
    if 'SPY' not in symbols or len(symbols)<2:raise DataError('BENCHMARK_COVERAGE')
    if not isinstance(sectors,dict) or set(sectors)!=set(symbols):raise DataError('SECTOR_MAPPING')
    for value in sectors.values():_id(value)
    if len({date for _,date,_ in rows})>1024:raise DataError('INPUT_BOUND')
    action_rows=tuple(sorted(actions.values(),key=lambda a:(a['effective_session'],a['symbol'],a['kind'],a['action_id'])))
    for a in action_rows:
        other='DIVIDEND' if a['kind']=='SPLIT' else 'SPLIT'
        if (a['symbol'],a['effective_session'],other) in semantic:raise DataError('AMBIGUOUS_ACTION_ORDER')
    identity=hashlib.sha256(canonical({'chunks':sorted(hashes),'sectors':sectors})).hexdigest()
    return Market(symbols,dict(sectors),rows,action_rows,identity)
