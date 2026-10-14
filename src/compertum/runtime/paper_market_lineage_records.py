"""Durable capture identity in the execution owner's existing state table."""
from uuid import NAMESPACE_URL,uuid5
import re
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.paper_contracts import strict_json
from .errors import RuntimeRefused
from .paper_market_grants import MarketGrant

PREFIX='paper_market_lineage_capture:'
VERSION='paper_market_lineage_capture_version'
PURPOSE='COMPERTUM_MARKET_LINEAGE_CAPTURE_V1'
IMMUTABLE={'version','purpose','capture_id','task_id','reservation_id','project_id','subject_key',
           'account_alias','job_id','grant_sha256','history','owner_instance','owner_generation'}
_FIELDS=IMMUTABLE|{'state','reason','lineage_sha256','evidence','manifest'}
_NEXT={'CAPTURING':{'READY','FAILED','INTERRUPTED'},'READY':{'PUBLISHED','FAILED','INTERRUPTED'},
       'FAILED':{'PUBLISHED'},'INTERRUPTED':{'PUBLISHED'},'PUBLISHED':set()}
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError)


def _need(value,code='MARKET_LINEAGE_RECORD_INVALID'):
    if not value:raise RuntimeRefused(code)


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def task_id(project_id,capture_id):
    _need(_hash(project_id));uuid(capture_id)
    return str(uuid5(NAMESPACE_URL,project_id+'/paper-market-lineage/'+capture_id))


def validate_manifest(value,task,capture):
    _need(type(value) is dict and set(value)=={'artifact_id','task_id','path','size_bytes','sha256'})
    uuid(value['artifact_id']);_need(value['task_id']==task)
    _need(value['path']==f'artifacts/runs/{task}/market-lineage-{capture}.bin')
    _need(type(value['size_bytes']) is int and 0<value['size_bytes']<=3*1024**2 and _hash(value['sha256']))


def initial_capture(grant,*,capture_id,reservation_id):
    _need(type(grant) is MarketGrant);grant.__post_init__();g=grant.to_payload()
    _need(g['mode']=='FRESH');uuid(capture_id);uuid(reservation_id)
    value={k:g[k] for k in ('project_id','subject_key','account_alias','job_id','history','owner_instance','owner_generation')}
    value.update(version=1,purpose=PURPOSE,capture_id=capture_id,task_id=task_id(g['project_id'],capture_id),
                 reservation_id=reservation_id,grant_sha256=grant.sha256,state='CAPTURING',reason=None,
                 lineage_sha256=None,evidence=None,manifest=None)
    return value


def validate_capture(value,grant):
    try:
        _need(type(value) is dict and set(value)==_FIELDS and len(canonical(value))<=16384)
        original=initial_capture(grant,capture_id=value['capture_id'],reservation_id=value['reservation_id'])
        _need(type(value['version']) is int and type(value['owner_generation']) is int)
        _need(all(value[k]==original[k] for k in IMMUTABLE))
        state=value['state'];reason=value['reason'];evidence=value['evidence'];manifest=value['manifest']
        _need(type(state) is str and state in _NEXT)
        _need(reason is None or type(reason) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',reason) is not None)
        _need((reason is not None)==(state in {'FAILED','INTERRUPTED'}))
        if evidence is None:_need(value['lineage_sha256'] is None and state not in {'READY','PUBLISHED'})
        else:
            _need(state!='CAPTURING' and _hash(value['lineage_sha256']))
            _need(type(evidence) is dict and set(evidence)=={'size_bytes','sha256'})
            _need(type(evidence['size_bytes']) is int and 0<evidence['size_bytes']<=3*1024**2 and _hash(evidence['sha256']))
        if manifest is not None:
            _need(state=='PUBLISHED' and evidence is not None)
            validate_manifest(manifest,value['task_id'],value['capture_id'])
            _need(all(manifest[k]==evidence[k] for k in ('size_bytes','sha256')))
        else:_need(state!='PUBLISHED')
        return value
    except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_RECORD_INVALID') from None


class LineageCaptureRecords:
    def __init__(self,records):
        self.records=records;self.db=records.db;self.project_id=records.project_id
        _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
        with self.db:
            row=self.db.execute('SELECT value FROM state WHERE key=?',(VERSION,)).fetchone()
            present=self.db.execute('SELECT 1 FROM state WHERE substr(key,1,?)=? LIMIT 1',(len(PREFIX),PREFIX)).fetchone()
            _need(row==('1',) or row is None and present is None)
            if row is None:
                c=self.db.execute('INSERT INTO state VALUES(?,?)',(VERSION,'1'))
                _need(c.rowcount==1,'MARKET_LINEAGE_WRITE_UNVERIFIED')
            self.all()

    def _version(self):
        _need(self.db.execute('SELECT value FROM state WHERE key=?',(VERSION,)).fetchone()==('1',))

    def _validate(self,value):
        try:
            fresh=self.records.read(value['job_id'])
            _need(fresh['consumed'] and fresh['state'] in {'COMPLETE','CANCELED','INTERRUPTED'}
                  and fresh['summary'] is not None and fresh['summary']['state']=='PAIR_COMPLETE')
            return validate_capture(value,MarketGrant(canonical(fresh['grant'])))
        except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_RECORD_INVALID') from None

    def read(self,capture_id):
        self._version();uuid(capture_id)
        row=self.db.execute('SELECT CASE WHEN length(value)<=16384 THEN value END FROM state WHERE key=?',(PREFIX+capture_id,)).fetchone()
        _need(row is not None,'MARKET_LINEAGE_UNKNOWN')
        try:
            value=self._validate(strict_json(row[0].encode()));_need(value['capture_id']==capture_id)
            return value
        except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_RECORD_INVALID') from None

    def all(self):
        self._version()
        rows=self.db.execute('SELECT key FROM state WHERE substr(key,1,?)=? ORDER BY key LIMIT 33',(len(PREFIX),PREFIX)).fetchall()
        _need(len(rows)<=32,'MARKET_LINEAGE_HISTORY_BOUND')
        values=[self.read(key[len(PREFIX):]) for (key,) in rows]
        for field in ('task_id','reservation_id'):
            _need(len({v[field] for v in values})==len(values),'MARKET_STORAGE_REUSED')
        _need(sum(v['state'] in {'CAPTURING','READY'} for v in values)<=1,'MARKET_LINEAGE_CAPACITY')
        return values

    def write(self,value,*,new=False):
        self._version();self._validate(value);raw=canonical(value).decode();key=PREFIX+value['capture_id']
        lock=self.db.execute("UPDATE state SET value=value WHERE key=? AND value='1'",(VERSION,))
        _need(lock.rowcount==1,'MARKET_LINEAGE_WRITE_UNVERIFIED');self._version()
        if new:
            _need(value['state']=='CAPTURING')
            _need(self.records.read(value['job_id'])['state']=='COMPLETE','MARKET_FRESH_UNAVAILABLE')
            previous=self.all();_need(len(previous)<32,'MARKET_LINEAGE_HISTORY_BOUND')
            _need(not any(v['state'] in {'CAPTURING','READY'} for v in previous),'MARKET_LINEAGE_CAPACITY')
            _need(all(v['task_id']!=value['task_id'] and v['reservation_id']!=value['reservation_id'] for v in previous),'MARKET_STORAGE_REUSED')
            _need(all(v['grant']['task_id']!=value['task_id'] and v['grant']['reservation_id']!=value['reservation_id'] for v in self.records.all()),'MARKET_STORAGE_REUSED')
            _need(self.db.execute('SELECT 1 FROM state WHERE key=?',(key,)).fetchone() is None,'MARKET_LINEAGE_CONFLICT')
            c=self.db.execute('INSERT INTO state VALUES(?,?)',(key,raw))
        else:
            before=self.read(value['capture_id'])
            _need(all(before[k]==value[k] for k in IMMUTABLE),'MARKET_LINEAGE_WRITE_UNVERIFIED')
            _need(value['state']==before['state'] or value['state'] in _NEXT[before['state']],'MARKET_LINEAGE_WRITE_UNVERIFIED')
            for field in ('lineage_sha256','evidence','manifest'):
                _need(before[field] is None or value[field]==before[field],'MARKET_LINEAGE_WRITE_UNVERIFIED')
            if before['state'] in {'FAILED','INTERRUPTED','PUBLISHED'}:
                _need(value==before or value['state']=='PUBLISHED' and before['evidence'] is not None,'MARKET_LINEAGE_WRITE_UNVERIFIED')
            c=self.db.execute('UPDATE state SET value=? WHERE key=? AND value=?',(raw,key,canonical(before).decode()))
        _need(c.rowcount==1 and self.read(value['capture_id'])==value,'MARKET_LINEAGE_WRITE_UNVERIFIED')

    def interrupt_unfinished(self):
        _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
        with self.db:
            for value in self.all():
                if value['state'] in {'CAPTURING','READY'}:
                    value.update(state='INTERRUPTED',reason='OWNER_RESTARTED');self.write(value)
