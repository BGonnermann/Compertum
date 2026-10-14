"""Immutable original-consumption observations in the execution state table."""
import math
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import strict_json,timestamp
from .errors import RuntimeRefused
from .paper_market_grants import MarketGrant

PREFIX='paper_market_consumption:'
_PURPOSE='COMPERTUM_MARKET_CONSUMPTION_V1'
_BINDINGS=('project_id','job_id','owner_instance','owner_generation')
_FIELDS={'version','purpose',*_BINDINGS,'grant_sha256','consumed_at','monotonic_at','elapsed_seconds'}
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError)


def _need(value,code='MARKET_CONSUMPTION_INVALID'):
    if not value:raise RuntimeRefused(code)


def validate_consumption(value,grant):
    """Check an original observation; it never renews the grant's lifetime."""
    try:
        _need(type(grant) is MarketGrant);grant.__post_init__();g=grant.to_payload()
        _need(type(value) is dict and set(value)==_FIELDS and len(canonical(value))<=4096)
        expected=dict(version=1,purpose=_PURPOSE,grant_sha256=grant.sha256,**{k:g[k] for k in _BINDINGS})
        _need(canonical({k:value[k] for k in expected})==canonical(expected))
        at=timestamp(value['consumed_at']);created=timestamp(g['created_at'])
        _need(at.isoformat()==value['consumed_at'])
        mono=value['monotonic_at'];elapsed=value['elapsed_seconds']
        _need(all(type(x) in (int,float) and math.isfinite(x) for x in (mono,elapsed)))
        _need(0<=mono<1e15 and elapsed==mono-g['prepared_mono'] and 0<=elapsed<60)
        _need(created<=at<timestamp(g['start_expires_at']) and abs((at-created).total_seconds()-elapsed)<=5)
        return value
    except _INVALID:raise RuntimeRefused('MARKET_CONSUMPTION_INVALID') from None


def build_consumption(grant,*,consumed_at,monotonic_at):
    try:
        _need(type(grant) is MarketGrant);grant.__post_init__();g=grant.to_payload()
        _need(type(monotonic_at) in (int,float))
        value=dict(version=1,purpose=_PURPOSE,grant_sha256=grant.sha256,**{k:g[k] for k in _BINDINGS},
                   consumed_at=consumed_at,monotonic_at=monotonic_at,elapsed_seconds=monotonic_at-g['prepared_mono'])
        return validate_consumption(value,grant)
    except _INVALID:raise RuntimeRefused('MARKET_CONSUMPTION_INVALID') from None


class ConsumptionRecords:
    """A missing old proof stays missing; no timestamp is inferred or backfilled."""
    def __init__(self,records):
        self.records=records;self.db=records.db
        _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
        self.all()

    def all(self):
        rows=self.db.execute('SELECT key FROM state WHERE substr(key,1,?)=? ORDER BY key LIMIT 33',(len(PREFIX),PREFIX)).fetchall()
        _need(len(rows)<=32,'MARKET_HISTORY_BOUND')
        return [self.read(key[len(PREFIX):]) for (key,) in rows]

    def read(self,job_id):
        job=self.records.read(job_id)
        row=self.db.execute('SELECT CASE WHEN length(value)<=4096 THEN value END FROM state WHERE key=?',(PREFIX+job_id,)).fetchone()
        _need(row is not None,'MARKET_CONSUMPTION_MISSING')
        try:
            raw=row[0].encode();value=validate_consumption(strict_json(raw),MarketGrant(canonical(job['grant'])))
            _need(job['consumed'] and canonical(value)==raw)
            return value
        except _INVALID:raise RuntimeRefused('MARKET_CONSUMPTION_INVALID') from None

    def write(self,value):
        _need(self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
        try:job=self.records.read(value['job_id'])
        except _INVALID:raise RuntimeRefused('MARKET_CONSUMPTION_INVALID') from None
        validate_consumption(value,MarketGrant(canonical(job['grant'])))
        _need(job['state']=='RUNNING' and job['consumed'])
        _need(len(self.all())<32,'MARKET_HISTORY_BOUND')
        key=PREFIX+value['job_id']
        _need(self.db.execute('SELECT 1 FROM state WHERE key=?',(key,)).fetchone() is None,'MARKET_CONSUMPTION_ALREADY_RECORDED')
        raw=canonical(value).decode();cursor=self.db.execute('INSERT INTO state VALUES(?,?)',(key,raw))
        _need(cursor.rowcount==1 and self.read(value['job_id'])==value,'MARKET_WRITE_UNVERIFIED')
