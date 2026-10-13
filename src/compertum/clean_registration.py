"""Coordinator-owned pair preregistration; no campaign creation or admission."""
import hashlib,sqlite3,json
from compertum.clean_pair import PairRecord,read_pair,MAX_PAIR_BYTES
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime.owners import require_live_owner
from compertum.runtime.identity_pins import runtime_identity
from compertum.evaluation_protocol import identifier

MAX_PAIRS=32

def _check(ok):
    if not ok:raise DataError('CLEAN_REGISTRATION_UNVERIFIED')

def _tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('clean_campaign_pairs','clean_campaign_members')").fetchall()}


def _head(rows):
    pins=sorted((pid,record.sha256) for pid,(record,_) in rows.items())
    return canonical({'schema':'clean-registration-head-v1','count':len(pins),'sha256':hashlib.sha256(canonical(pins)).hexdigest()}).decode()


def _stored_head(db):
    rows=db.execute('SELECT '+_text('value',256)+" FROM state WHERE key='clean_registration_head'").fetchall()
    _check(not rows or (len(rows)==1 and type(rows[0][0]) is str))
    return rows[0][0] if rows else None


def initialize(store):
    with store._live() as guard,store.conn:
        require_live_owner(store.lease,'coordinator')
        tables=_tables(store.conn);head=_stored_head(store.conn)
        if not tables and head is None:
            store.conn.execute('CREATE TABLE clean_campaign_pairs(pair_id TEXT PRIMARY KEY,body TEXT NOT NULL,sha256 TEXT NOT NULL)')
            store.conn.execute('CREATE TABLE clean_campaign_members(member_id TEXT PRIMARY KEY,pair_id TEXT NOT NULL,lane TEXT NOT NULL,kind TEXT NOT NULL)')
            store.conn.execute("INSERT INTO state VALUES('clean_registration_head',?)",(_head({}),))
        _records(store.conn,guard.project)


def _records(db,project):
    # Preserve one read snapshot even when evaluation opens the connection.
    try:
        db.execute('SAVEPOINT clean_registration_read')
        try:return _snapshot_records(db,project)
        finally:db.execute('RELEASE SAVEPOINT clean_registration_read')
    except sqlite3.Error:raise DataError('CLEAN_REGISTRATION_UNVERIFIED') from None


def _text(column,limit):
    # Bound values inside SQLite before allocating Python strings.
    return f"CASE WHEN typeof({column})='text' AND length(CAST({column} AS BLOB))<={limit} THEN {column} ELSE NULL END"


def _snapshot_records(db,project):
    try:
        rows=db.execute('SELECT '+','.join(_text(k,n) for k,n in [('pair_id',36),('body',MAX_PAIR_BYTES),('sha256',64)])+' FROM clean_campaign_pairs ORDER BY pair_id LIMIT ?',(MAX_PAIRS+1,)).fetchall()
        _check(len(rows)<=MAX_PAIRS);result={};expected=[];used=set()
        for pid,raw,pin in rows:
            _check(type(raw) is str and len(raw)<=MAX_PAIR_BYTES);record=PairRecord(raw.encode(),pin);v=read_pair(record.content,expected_sha256=pin)
            _check(v['project_id']==project.project_id and v['pair_id']==pid);result[pid]=(record,v)
            for lane in ('source','wheel'):
                for kind in ('run_id','seal_id'):
                    member=v[lane][kind];_check(member not in used);used.add(member);expected.append((member,pid,lane,kind))
        actual=db.execute('SELECT '+','.join(_text(k,n) for k,n in [('member_id',36),('pair_id',36),('lane',6),('kind',7)])+' FROM clean_campaign_members ORDER BY member_id LIMIT ?',(MAX_PAIRS*4+1,)).fetchall()
        _check(actual==sorted(expected) and _stored_head(db)==_head(result));return result
    except (sqlite3.Error,ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('CLEAN_REGISTRATION_UNVERIFIED') from None


def read_registration(db,project,pair_id):
    identifier(pair_id);row=_records(db,project).get(pair_id)
    if row is None:raise DataError('CLEAN_REGISTRATION_REQUIRED')
    return row[0]


def member_registration(db,project,run_id,*,kind=None):
    identifier(run_id)
    for record,value in _records(db,project).values():
        for lane in ('source','wheel'):
            if any(value[lane][k]==run_id for k in (('run_id','seal_id') if kind is None else (kind,))):return record,lane
    return None


def register_pair(runs,pair):
    _check(type(pair) is PairRecord);value=read_pair(pair.content,expected_sha256=pair.sha256)
    initialize(runs.store)
    with runs.store._live() as guard:
        require_live_owner(runs.store.lease,'coordinator')
        _check(value['project_id']==guard.project.project_id and canonical(value['runtime'])==canonical(runtime_identity()))
        rows=_records(runs.store.conn,guard.project);prior=rows.get(value['pair_id'])
        if prior is not None:
            _check(prior[0]==pair);return pair
        _check(len(rows)<MAX_PAIRS)
        used={v[l][k] for _,v in rows.values() for l in ('source','wheel') for k in ('run_id','seal_id')}
        proposed={value[l][k] for l in ('source','wheel') for k in ('run_id','seal_id')};_check(not used.intersection(proposed))
        from compertum.development_seals import _evidence
        evidence=_evidence(guard.project)
        for lane in ('source','wheel'):
            run=value[lane]['run_id'];seal=value[lane]['seal_id']
            for table in ('baseline_runs','baseline_history','sealed_campaigns'):
                _check(runs.store.conn.execute('SELECT 1 FROM '+table+' WHERE run_id=? LIMIT 1',(run,)).fetchone() is None)
            _check(runs.store.conn.execute('SELECT 1 FROM sealed_campaigns WHERE seal_id=? LIMIT 1',(seal,)).fetchone() is None)
            if evidence:
                _check(all(sid!=seal and row['creation']['protocol']['development_run_id']!=run for sid,row in evidence['seals'].items()))
        try:
            with runs.store.conn:
                runs.store.conn.execute('INSERT INTO clean_campaign_pairs VALUES(?,?,?)',(value['pair_id'],pair.content.decode(),pair.sha256))
                runs.store.conn.executemany('INSERT INTO clean_campaign_members VALUES(?,?,?,?)',[(value[l][k],value['pair_id'],l,k) for l in ('source','wheel') for k in ('run_id','seal_id')])
                runs.store.conn.execute("UPDATE state SET value=? WHERE key='clean_registration_head'",(_head({**rows,value['pair_id']:(pair,value)}),))
        except sqlite3.Error:raise DataError('CLEAN_REGISTRATION_UNVERIFIED') from None
        return read_registration(runs.store.conn,guard.project,value['pair_id'])



def require_protocol(db,project,protocol,seal_id):
    """Both owners resolve membership from a committed database snapshot."""
    from .evaluation_protocol import read_protocol
    import hashlib
    raw=canonical(protocol);read_protocol(raw,expected_sha256=hashlib.sha256(raw).hexdigest())
    identifier(seal_id);binding=protocol.get('clean_pair');tables=_tables(db)
    if not tables:
        _check(binding is None and _stored_head(db) is None);return None  # Unprovisioned legacy store.
    rows=_records(db,project);members={}
    for record,value in rows.values():
        for lane in ('source','wheel'):
            for kind in ('run_id','seal_id'):members[value[lane][kind]]=(record,lane,kind)
    run=members.get(protocol['development_run_id']);seal=members.get(seal_id)
    if run is None and seal is None:
        _check(binding is None);return None
    _check(run is not None and seal is not None and run[:2]==seal[:2] and run[2]=='run_id' and seal[2]=='seal_id')
    record,lane,_=run;value=read_pair(record.content,expected_sha256=record.sha256)
    _check(binding=={'record':value,'sha256':record.sha256,'lane':lane})
    return record,lane


def owner_protocol(project,protocol,seal_id):
    """Evaluation reads coordinator state; caller-supplied registration is insufficient."""
    from .persistence import _active_store_path
    path=_active_store_path(project.root_path,project.project_id,'coordinator')
    try:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:
            db.execute('BEGIN')
            _check(dict(db.execute('SELECT key,value FROM metadata'))=={'schema_version':'1','project_id':project.project_id,'role':'coordinator'})
            return require_protocol(db,project,protocol,seal_id)
        finally:db.close()
    except (sqlite3.Error,OSError):raise DataError('CLEAN_REGISTRATION_UNVERIFIED') from None
