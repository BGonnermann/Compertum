"""Committed coordinator shortlist tickets and independent owner validation."""
import json,sqlite3,time
from .data.encoding import canonical
from .data.errors import DataError
from .shortlist_ticket import MAX_TICKET_BYTES,read_ticket,build_ticket,review_pin
from .clean_registration import _text,read_registration
from .persistence import _active_store_path
from .runtime.errors import RuntimeRefused
from .runtime.owners import require_live_owner
from .review_evidence import check,sha


def owner_ticket(project,seal_id,ticket_sha256,evidence):
    from .shortlist_evidence import validate_committed
    deadline=time.monotonic()+4
    path=_active_store_path(project.root_path,project.project_id,'coordinator')
    try:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:
            db.execute('BEGIN')
            check(dict(db.execute('SELECT key,value FROM metadata'))=={'schema_version':'1','project_id':project.project_id,'role':'coordinator'})
            row=db.execute('SELECT '+','.join(_text(k,n) for k,n in [('pair_id',36),('body',MAX_TICKET_BYTES),('sha256',64)])+' FROM shortlist_tickets WHERE seal_id=?',(seal_id,)).fetchone()
            check(row is not None and type(row[1]) is str and row[2]==ticket_sha256)
            v=read_ticket(row[1].encode(),expected_sha256=ticket_sha256)
            check(v['pair']['source']['seal_id']==seal_id and v['pair']['pair_id']==row[0])
            registration=read_registration(db,project,row[0]);check(registration.content==canonical(v['pair']) and registration.sha256==v['pair_sha256'])
            validate_committed(db,project,v,evidence,deadline=deadline)
            return v
        finally:db.close()
    except (sqlite3.Error,OSError,ValueError,TypeError,KeyError,AttributeError):raise RuntimeRefused('SHORTLIST_TICKET_UNVERIFIED') from None


def prepare_shortlist(reviews,comparison_task):
    """Coordinator validates complete evidence before committing compact pins."""
    from .shortlist_evidence import history
    from .development_seals import read_ticket as development_ticket
    from .review_evidence import published
    with reviews.store._live() as guard:
        require_live_owner(reviews.store.lease,'coordinator');db=reviews.store.conn
        comparison=reviews.completed(comparison_task);check(comparison['kind']=='pair_compare')
        header,metadata=reviews.bundle(comparison);meta=json.loads(metadata)
        pair=read_registration(db,guard.project,meta['pair']['pair_id']);check(pair.content==canonical(meta['pair']) and pair.sha256==meta['pair_sha256'])
        p=meta['pair'];pins={};protocols={}
        states={'comparison':comparison}
        rows=db.execute("SELECT task_id FROM campaign_reviews WHERE source_run_id=? AND kind='scorecard' LIMIT 2",(p['source']['run_id'],)).fetchall();check(len(rows)==1)
        states['scorecard']=reviews.completed(rows[0][0])
        for lane,entry in zip(('source','wheel'),meta['lanes']):
            states[lane+'_aggregate']=reviews.completed(entry['aggregate']['task_id'])
            admitted=development_ticket(db,guard.project,p[lane]['run_id']);check(admitted is not None)
            protocols[lane]=admitted['body']['protocol_sha256']
        for name,state in states.items():pins[name]=review_pin(state,history(db,state['task_id']))
        raw=published(reviews.storage,comparison['artifact'],128*1024,read=True).split(b'\n',1)[1]
        ticket=build_ticket(project_id=guard.project.project_id,pair=p,pair_sha256=pair.sha256,protocol_sha256=protocols,reviews=pins,comparison=raw)
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS shortlist_tickets(pair_id TEXT PRIMARY KEY,seal_id TEXT UNIQUE NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL,receipt TEXT)')
            prior=db.execute('SELECT '+','.join(_text(k,n) for k,n in [('seal_id',36),('body',MAX_TICKET_BYTES),('sha256',64)])+' FROM shortlist_tickets WHERE pair_id=?',(p['pair_id'],)).fetchone()
            expected=(p['source']['seal_id'],ticket.content.decode(),ticket.sha256)
            if prior is None:
                check(db.execute('SELECT count(*) FROM shortlist_tickets').fetchone()[0]<32)
                db.execute('INSERT INTO shortlist_tickets VALUES(?,?,?,?,NULL)',(p['pair_id'],*expected))
            else:check(prior==expected)
        return ticket


def freeze_shortlist(reviews,comparison_task,*,evaluation):
    from .development_seals import _caller,_mirror
    from .evaluation_seals import reserve_seal_append,verify_seal_journal,shortlist_receipt
    ticket=prepare_shortlist(reviews,comparison_task);v=read_ticket(ticket.content,expected_sha256=ticket.sha256);sid=v['pair']['source']['seal_id']
    with reviews.store._live() as guard:
        require_live_owner(reviews.store.lease,'coordinator');call=_caller(evaluation,guard.project)
        evidence=verify_seal_journal(guard.project);check(evidence['status']=='VERIFIED')
        if evidence['seals'].get(sid,{}).get('freeze') is None:reserve_seal_append(reviews.storage)
        result=call(dict(operation='freeze',seal_id=sid,ticket_sha256=ticket.sha256))
        evidence=verify_seal_journal(guard.project);check(evidence['status']=='VERIFIED')
        genuine=shortlist_receipt(guard.project.project_id,evidence,sid)
        check(result==genuine and result['status']=='FROZEN' and result['ticket_sha256']==ticket.sha256)
        _mirror(guard.project,evidence)
        with reviews.store.conn:
            raw=canonical(result).decode()
            changed=reviews.store.conn.execute('UPDATE shortlist_tickets SET receipt=? WHERE seal_id=? AND sha256=?',(raw,sid,ticket.sha256))
            check(changed.rowcount==1)
            saved=reviews.store.conn.execute('SELECT '+_text('receipt',4096)+' FROM shortlist_tickets WHERE seal_id=? AND sha256=?',(sid,ticket.sha256)).fetchall()
            check(saved==[(raw,)])
        return result
