"""Bounded coordinator lineage routes; records do not reconstruct storage grants."""
import re
from compertum.data.encoding import canonical
from compertum.events import uuid
from compertum.paper_contracts import strict_json
from .errors import RuntimeRefused
from .paper_market_grants import _manifest as history_manifest
from .paper_market_lineage_records import IMMUTABLE,task_id,validate_manifest,_hash,_INVALID

PREFIX='paper_market_lineage_route:'
VERSION='paper_market_lineage_route_version'
PURPOSE='COMPERTUM_MARKET_LINEAGE_ROUTE_V1'
_FIELDS=IMMUTABLE|{'state','reason','lineage_sha256','evidence','manifest'}


def _need(value,code='MARKET_LINEAGE_ROUTE_INVALID'):
    if not value:raise RuntimeRefused(code)


def validate_route(v,project_id):
    try:
        _need(type(v) is dict and set(v)==_FIELDS and len(canonical(v))<=16384)
        _need(type(v['version']) is int and v['version']==1 and v['purpose']==PURPOSE)
        _need(v['project_id']==project_id and _hash(project_id))
        for field in ('capture_id','task_id','reservation_id','job_id','owner_instance'):uuid(v[field])
        for field in ('subject_key','grant_sha256'):_need(_hash(v[field]))
        _need(v['task_id']==task_id(project_id,v['capture_id']))
        _need(type(v['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v['account_alias']) is not None)
        _need(type(v['owner_generation']) is int and 0<v['owner_generation']<2**63)
        h=v['history'];_need(type(h) is dict and set(h)=={'job_id','task_id','grant_sha256','manifest'})
        uuid(h['job_id']);uuid(h['task_id']);_need(_hash(h['grant_sha256']))
        _need(h['job_id']!=v['job_id'] and h['task_id']!=v['task_id']);history_manifest(h['manifest'],h['task_id'],h['job_id'])
        state=v['state'];_need(type(state) is str and state in {'WAITING','TRANSFERRING','PUBLISHED','FAILED'})
        reason=v['reason'];_need(reason is None or type(reason) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',reason) is not None)
        _need((reason is not None)==(state=='FAILED'))
        e=v['evidence'];m=v['manifest']
        if e is None:_need(v['lineage_sha256'] is None and state in {'WAITING','FAILED'} and m is None)
        else:
            _need(state!='WAITING' and _hash(v['lineage_sha256']) and type(e) is dict and set(e)=={'size_bytes','sha256'})
            _need(type(e['size_bytes']) is int and 0<e['size_bytes']<=3*1024**2 and _hash(e['sha256']))
        if m is not None:
            validate_manifest(m,v['task_id'],v['capture_id']);_need(all(m[k]==e[k] for k in ('size_bytes','sha256')))
        if state=='PUBLISHED':_need(m is not None)
        return v
    except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_ROUTE_INVALID') from None


class LineageRoutes:
    def __init__(self,db,project_id):
        self.db=db;self.project_id=project_id;_need(_hash(project_id))
        _need(not db.in_transaction,'MARKET_TRANSACTION_OPEN')
        with db:
            row=db.execute('SELECT value FROM state WHERE key=?',(VERSION,)).fetchone()
            present=db.execute('SELECT 1 FROM state WHERE substr(key,1,?)=? LIMIT 1',(len(PREFIX),PREFIX)).fetchone()
            _need(row==('1',) or row is None and present is None)
            if row is None:
                c=db.execute('INSERT INTO state VALUES(?,?)',(VERSION,'1'));_need(c.rowcount==1,'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED')
            self.all()

    def _version(self):
        _need(self.db.execute('SELECT value FROM state WHERE key=?',(VERSION,)).fetchone()==('1',))

    def read(self,capture_id):
        self._version();uuid(capture_id)
        row=self.db.execute('SELECT CASE WHEN length(value)<=16384 THEN value END FROM state WHERE key=?',(PREFIX+capture_id,)).fetchone()
        _need(row is not None,'MARKET_LINEAGE_UNKNOWN')
        try:
            v=validate_route(strict_json(row[0].encode()),self.project_id);_need(v['capture_id']==capture_id);return v
        except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_ROUTE_INVALID') from None

    def all(self):
        self._version();rows=self.db.execute('SELECT key FROM state WHERE substr(key,1,?)=? ORDER BY key LIMIT 33',(len(PREFIX),PREFIX)).fetchall()
        _need(len(rows)<=32,'MARKET_LINEAGE_HISTORY_BOUND')
        values=[self.read(key[len(PREFIX):]) for (key,) in rows]
        for field in ('task_id','reservation_id'):_need(len({v[field] for v in values})==len(values),'MARKET_STORAGE_REUSED')
        _need(sum(v['state'] in {'WAITING','TRANSFERRING'} for v in values)<=1,'MARKET_LINEAGE_CAPACITY')
        return values

    def write(self,v,*,new=False):
        self._version();validate_route(v,self.project_id);raw=canonical(v).decode();key=PREFIX+v['capture_id']
        lock=self.db.execute("UPDATE state SET value=value WHERE key=? AND value='1'",(VERSION,))
        _need(lock.rowcount==1,'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED');self._version()
        if new:
            _need(v['state']=='WAITING')
            previous=self.all();_need(len(previous)<32,'MARKET_LINEAGE_HISTORY_BOUND')
            _need(not any(r['state'] in {'WAITING','TRANSFERRING'} for r in previous),'MARKET_LINEAGE_CAPACITY')
            _need(all(r['task_id']!=v['task_id'] and r['reservation_id']!=v['reservation_id'] for r in previous),'MARKET_STORAGE_REUSED')
            _need(self.db.execute('SELECT 1 FROM state WHERE key=?',(key,)).fetchone() is None,'MARKET_LINEAGE_CONFLICT')
            c=self.db.execute('INSERT INTO state VALUES(?,?)',(key,raw))
        else:
            before=self.read(v['capture_id']);_need(all(before[k]==v[k] for k in IMMUTABLE),'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED')
            for field in ('lineage_sha256','evidence','manifest'):
                _need(before[field] is None or v[field]==before[field],'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED')
            allowed={'WAITING':{'WAITING','TRANSFERRING','FAILED'},'TRANSFERRING':{'TRANSFERRING','PUBLISHED','FAILED'},'FAILED':{'FAILED','TRANSFERRING','PUBLISHED'},'PUBLISHED':{'PUBLISHED'}}
            _need(v['state'] in allowed[before['state']],'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED')
            if before['state']=='PUBLISHED':_need(v==before,'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED')
            if before['state']=='FAILED':
                _need(v==before or v['state'] in {'TRANSFERRING','PUBLISHED'} and v['manifest'] is not None and before['evidence'] is not None,'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED')
            c=self.db.execute('UPDATE state SET value=? WHERE key=? AND value=?',(raw,key,canonical(before).decode()))
        _need(c.rowcount==1 and self.read(v['capture_id'])==v,'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED');self.all()
