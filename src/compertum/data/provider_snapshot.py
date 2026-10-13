"""Calendar-complete real-provider observations, distinct from synthetic admission.

This reader verifies transport evidence and reports missing inputs. It deliberately
cannot certify action coverage, historical identity, fees or a trading strategy.
"""
from dataclasses import dataclass
from datetime import timedelta
import hashlib,json

from .alpaca import BarEvidence,SYMBOLS,_date,_profile,read_bar_evidence
from .calendar import NY,session_times,utc_time
from .encoding import canonical
from .errors import DataError

MAX_TOTAL=16*1024*1024
MAX_CHUNKS=64
MAX_SESSIONS=1024
MAX_ROWS=32768


@dataclass(frozen=True)
class ProviderSnapshot:
    content:bytes
    sha256:str
    evidence:tuple[BarEvidence,...]
    start:str
    end:str
    feed:str


def _calendar(start,end):
    _date(start);_date(end)
    session_times(start);session_times(end)
    if end<start:raise DataError('PROVIDER_WINDOW')
    warmup=[session_times(start).previous_date]
    for _ in range(251):warmup.insert(0,session_times(warmup[0]).previous_date)
    _date(warmup[0])
    scored=[start]
    while scored[-1]!=end:
        if len(warmup)+len(scored)>=MAX_SESSIONS:raise DataError('INPUT_BOUND')
        scored.append(session_times(scored[-1]).next_date)
    return tuple(warmup),tuple(scored)


def build_provider_snapshot(chunks,*,start,end,feed):
    """Revalidate every chunk and normalize without filling or excluding gaps."""
    if feed!='sip':raise DataError('PROVIDER_PROFILE')
    warmup,scored=_calendar(start,end)
    if (type(chunks) not in (tuple,list) or not 1<=len(chunks)<=MAX_CHUNKS
            or any(type(c) is not BarEvidence for c in chunks)
            or sum(len(c.content) for c in chunks)>MAX_TOTAL):raise DataError('INPUT_BOUND')
    rows={};hashes=[];daily=set(warmup+scored);scoring=set(scored)
    for chunk in chunks:
        if read_bar_evidence(chunk.content)!=chunk:raise DataError('PROVIDER_EVIDENCE_CORRUPT')
        if chunk.feed!=feed:raise DataError('PROVIDER_MIXED_FEEDS')
        envelope=json.loads(chunk.content);hashes.append(chunk.sha256)
        for request in envelope['requests']:
            params=request['params']
            if params['asof']!=end:raise DataError('PROVIDER_ASOF')
            _,requested,_,_=_profile(params)
            allowed=daily if params['timeframe']=='1Day' else scoring
            if any(utc_time(t).astimezone(NY).date().isoformat() not in allowed for t in requested):
                raise DataError('PROVIDER_SCOPE')
        pages={(p['request_id'],p['body_sha256']):p for p in envelope['pages']}
        for bar in chunk.rows:
            stamp=utc_time(bar.timestamp);day=stamp.astimezone(NY).date().isoformat();times=session_times(day)
            if bar.timeframe=='1Day':
                if day not in daily:raise DataError('PROVIDER_SCOPE')
                reference='daily';available=session_times(times.next_date).decision
            else:
                if day not in scoring:raise DataError('PROVIDER_SCOPE')
                reference='entry' if stamp==times.entry else 'close'
                available=stamp+timedelta(minutes=16) if reference=='entry' else session_times(times.next_date).decision
            key=(bar.symbol,day,reference,bar.adjustment)
            if key in rows:raise DataError('DUPLICATE_PROVIDER_ROW')
            page=pages[(bar.request_id,bar.body_sha256)];received=utc_time(page['received_utc']).isoformat()
            rows[key]={'symbol':bar.symbol,'session_date':day,'reference':reference,'adjustment':bar.adjustment,'feed':feed,
                'bar_label_time':stamp.isoformat(),'session_open':times.open.isoformat(),'session_close':times.close.isoformat(),
                'provider_timestamp':None,'provider_timestamp_basis':'NOT_REPORTED_SEPARATELY_FROM_BAR_LABEL',
                'retrieved_at':received,'first_seen_at':received,'first_seen_basis':'RETAINED_ENVELOPE_RECEIPT_NOT_FIRST_EVER',
                'feature_available_at':None,'actual_availability_basis':'VALIDATION_ADMISSION_TIME_NOT_RECORDED',
                'simulated_available_at':available.isoformat(),'simulated_revision_available_at':available.isoformat(),
                'revision_id':bar.body_sha256,'source_evidence_sha256':chunk.sha256,'source_body_sha256':bar.body_sha256,
                'source_request_id':bar.request_id,**{k:getattr(bar,k) for k in ('open','high','low','close','volume','trades','vwap')}}
            if len(rows)>MAX_ROWS:raise DataError('INPUT_BOUND')
    expected={(symbol,day,'daily',adjustment) for symbol in SYMBOLS for day in daily for adjustment in ('raw','split')}
    expected.update((symbol,day,reference,adjustment) for symbol in SYMBOLS for day in scored for reference in ('entry','close') for adjustment in ('raw','split'))
    missing=sorted(expected-set(rows))
    if set(rows)-expected:raise DataError('PROVIDER_SCOPE')
    coverage={}
    for symbol in sorted(SYMBOLS):
        def count(days,reference,adjustment):return sum((symbol,day,reference,adjustment) in rows for day in days)
        coverage[symbol]={'warmup_daily_expected':len(warmup),'scored_daily_expected':len(scored),'references_expected':2*len(scored),
            'warmup_daily_raw':count(warmup,'daily','raw'),'warmup_daily_split':count(warmup,'daily','split'),
            'scored_daily_raw':count(scored,'daily','raw'),'scored_daily_split':count(scored,'daily','split'),
            'references_raw':sum(count(scored,ref,'raw') for ref in ('entry','close')),
            'references_split':sum(count(scored,ref,'split') for ref in ('entry','close'))}
    value={'schema_version':'provider-snapshot-v1','provider':'alpaca','feed':feed,'symbols':sorted(SYMBOLS),
        'availability_basis':'CURRENT_VINTAGE_SIMULATED_AVAILABILITY','financial_accepted':False,
        'status':'INPUT_EVIDENCE_VALIDATED_QUALIFICATION_PENDING','start':start,'end':end,'warmup_start':warmup[0],'warmup_sessions':252,
        'source_evidence_sha256':sorted(hashes),'rows':[rows[k] for k in sorted(rows)],'missing':missing,
        'coverage':{'complete':not missing,'symbols':coverage,'denominator_basis':'FROZEN_UNIVERSE_CALENDAR_PENDING_HISTORICAL_LISTING_QUALIFICATION'},
        'pending':['ACTION_COVERAGE_AND_KNOWLEDGE','HISTORICAL_IDENTITY_AND_ELIGIBILITY','SPLIT_ADJUSTMENT_BASIS','DATED_FEES','PROTOCOL_SEAL']}
    content=canonical(value)
    if len(content)>MAX_TOTAL:raise DataError('INPUT_BOUND')
    return ProviderSnapshot(content,hashlib.sha256(content).hexdigest(),tuple(chunks),start,end,feed)


def verify_provider_snapshot(snapshot):
    if type(snapshot) is not ProviderSnapshot:raise DataError('PROVIDER_SNAPSHOT_CORRUPT')
    verified=build_provider_snapshot(snapshot.evidence,start=snapshot.start,end=snapshot.end,feed=snapshot.feed)
    if verified!=snapshot:raise DataError('PROVIDER_SNAPSHOT_CORRUPT')
    return verified