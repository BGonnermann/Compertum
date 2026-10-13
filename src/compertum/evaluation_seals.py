"""Evaluation-owned immutable synthetic seals with an append-preserved journal.

This records rules only. Development admission, final access and promotion need
separate trusted transitions; a copied receipt is not an authority capability.
"""
from datetime import datetime,timezone
from uuid import uuid4
import hashlib
import json
import os
import sqlite3
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import read_protocol,digest,identifier,MAX_PROTOCOL_BYTES
from .persistence import checked_path,_active_store_path
from .runtime.errors import RuntimeRefused
from .runtime.owners import require_live_owner
from .runtime.identity_pins import runtime_identity

MAX_SEALS=128
MAX_EVENTS=256
MAX_EVENT_BYTES=32*1024
ZERO='0'*64
REASONS=frozenset({'POLICY_CHANGED','INPUT_CHANGED','STATUS_UNCERTAIN','OPERATOR_INVALIDATED'})


def _flush(path,raw):
    with path.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


def _read(path,maximum):
    checked_path(path.parent,path)
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    if len(raw)>maximum:raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
    value=json.loads(raw)
    if canonical(value)!=raw:raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
    return value


def _directory(project):return checked_path(project.root_path,project.root_path/'state/evaluation-seals')


def replay_seal_events(project_id,items,head):
    """One shared validator for immutable files and frozen database mirrors."""
    try:
        digest(project_id)
        if type(head) is not dict or set(head)!={'sequence','sha256'} or type(head['sequence']) is not int or not 0<=head['sequence']<=MAX_EVENTS:raise ValueError()
        digest(head['sha256'])
        if type(items) is not list or len(items)!=head['sequence']:raise ValueError()
        events=[];seals={};runs=set();previous=ZERO
        for sequence in range(1,head['sequence']+1):
            item=items[sequence-1]
            if len(canonical(item))>MAX_EVENT_BYTES:raise ValueError()
            if set(item)!={'schema','sequence','previous_sha256','record'} or item['schema']!='synthetic-seal-event-v1' or type(item['sequence']) is not int or item['sequence']!=sequence or item['previous_sha256']!=previous:raise ValueError()
            record=item['record'];identifier(record['seal_id']);identifier(record['owner_instance'])
            if type(record['owner_generation']) is not int or record['owner_generation']<1:raise ValueError()
            created=datetime.fromisoformat(record['created_at'])
            if created.tzinfo is None or created.utcoffset().total_seconds()!=0:raise ValueError()
            seal_id=record['seal_id']
            common={'operation','seal_id','created_at','owner_instance','owner_generation'}
            if record['operation']=='CREATE':
                if set(record)!=common|{'protocol','protocol_sha256'} or seal_id in seals or len(seals)>=MAX_SEALS:raise ValueError()
                protocol=read_protocol(canonical(record['protocol']),expected_sha256=record['protocol_sha256'])
                run_id=protocol['development_run_id']
                if run_id in runs:raise ValueError()
                runs.add(run_id);seals[seal_id]={'creation':record,'creation_sequence':sequence,'status':'SEALED','invalidation':None,'admission':None,'admission_sequence':None,'freeze':None,'freeze_sequence':None,'final':None,'final_sequence':None,'final_complete':None,'final_complete_sequence':None}
            elif record['operation']=='ADMIT_DEVELOPMENT':
                if set(record)!=common|{'ticket_sha256'} or seal_id not in seals or seals[seal_id]['status']!='SEALED' or seals[seal_id]['admission'] is not None:raise ValueError()
                digest(record['ticket_sha256']);seals[seal_id].update(admission=record,admission_sequence=sequence)
            elif record['operation']=='FREEZE_SHORTLIST':
                if set(record)!=common|{'ticket','ticket_sha256'} or seal_id not in seals or seals[seal_id]['freeze'] is not None:raise ValueError()
                _freeze_ticket(project_id,seals,seal_id,record['ticket'],record['ticket_sha256'])
                seals[seal_id].update(freeze=record,freeze_sequence=sequence)
            elif record['operation']=='PREPARE_FINAL':
                if set(record)!=common|{'plan','plan_sha256'} or seal_id not in seals:raise ValueError()
                from .final_transaction import replay_prepare
                replay_prepare(project_id,seals,seal_id,record,sequence)
            elif record['operation']=='COMPLETE_EMPTY_FINAL':
                if set(record)!=common|{'result','result_sha256'} or seal_id not in seals:raise ValueError()
                from .final_transaction import replay_complete
                replay_complete(seals,seal_id,record,sequence)
            elif record['operation'] in {'START_FINAL_BATCH','INTERRUPT_FINAL_BATCH','TERMINATE_FINAL_BATCH','ABANDON_FINAL_BATCH','ABANDON_FINAL_PREPARATION'}:
                from .final_attempts import replay_attempt
                replay_attempt(seals,seal_id,record,sequence)
            elif record['operation']=='INVALIDATE':
                if set(record)!=common|{'reason'} or record['reason'] not in REASONS or seal_id not in seals or seals[seal_id]['status']!='SEALED':raise ValueError()
                seals[seal_id].update(status='INVALIDATED',invalidation=record)
            else:raise ValueError()
            previous=hashlib.sha256(canonical(item)).hexdigest();events.append(item)
        if previous!=head['sha256']:raise ValueError()
        return {'status':'VERIFIED','sequence':head['sequence'],'sha256':previous,'events':events,'seals':seals}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,RuntimeRefused,DataError):
        return {'status':'SEAL_JOURNAL_COMPROMISED','sequence':None,'sha256':None,'events':[],'seals':{}}


def verify_seal_journal(project):
    """Pure inspection: never provision or repair uncertain journal files."""
    try:
        directory=_directory(project)
        if _read(directory/'identity.json',1024)!={'schema':'synthetic-seal-journal-v1','project_id':project.project_id}:raise ValueError()
        head=_read(directory/'head.json',1024)
        if type(head) is not dict or set(head)!={'sequence','sha256'} or type(head['sequence']) is not int or not 0<=head['sequence']<=MAX_EVENTS:raise ValueError()
        if {p.name for p in directory.iterdir()}!={'identity.json','head.json'}|{f'{n:08}.json' for n in range(1,head['sequence']+1)}:raise ValueError()
        return replay_seal_events(project.project_id,[_read(directory/f'{n:08}.json',MAX_EVENT_BYTES) for n in range(1,head['sequence']+1)],head)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,RuntimeRefused,DataError):
        return {'status':'SEAL_JOURNAL_COMPROMISED','sequence':None,'sha256':None,'events':[],'seals':{}}


def _provision_seal_journal(lease,project):
    """Only called during first evaluation-store creation, before its database."""
    require_live_owner(lease,'evaluation');directory=_directory(project)
    if directory.exists():
        if verify_seal_journal(project)['status']!='VERIFIED':raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
        return
    directory.mkdir()  # Any interrupted provisioning remains uncertain.
    _flush(directory/'identity.json',canonical({'schema':'synthetic-seal-journal-v1','project_id':project.project_id}))
    _flush(directory/'head.json',canonical({'sequence':0,'sha256':ZERO}))


def reserve_seal_append(manager):
    """Coordinator reserves the exact next journal event before owner RPC."""
    require_live_owner(manager.lease,'coordinator')
    with manager.store._live() as guard:
        directory=_directory(guard.project)
        if directory.exists():
            evidence=verify_seal_journal(guard.project)
            if evidence['status']!='VERIFIED':raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
            sequence=evidence['sequence']+1
        else:sequence=1
        if sequence>MAX_EVENTS:raise RuntimeRefused('SEAL_COUNT_BOUND')
        path=f'state/evaluation-seals/{sequence:08}.json'
        old=manager.store.conn.execute("SELECT maximum,category,status FROM reservations WHERE path=?",(path,)).fetchall()
        if old:
            if old!=[(MAX_EVENT_BYTES,'records','RUNTIME')]:raise RuntimeRefused('SEAL_STORAGE_UNRESERVED')
            return path
        grant=manager.reserve_bytes(str(uuid4()),'records',MAX_EVENT_BYTES)
        with manager.store.conn:manager.store.conn.execute("UPDATE reservations SET status='RUNTIME',path=? WHERE id=?",(path,grant.grant_id))
        return path


def _require_reservation(project,path,minimum):
    dbpath=_active_store_path(project.root_path,project.project_id,'coordinator')
    try:
        db=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True,timeout=0.2)
        try:
            metadata=dict(db.execute('SELECT key,value FROM metadata'))
            if metadata!={'schema_version':'1','project_id':project.project_id,'role':'coordinator'}:raise RuntimeRefused('SEAL_STORAGE_UNRESERVED')
            rows=db.execute("SELECT maximum FROM reservations WHERE path=? AND category='records' AND status='RUNTIME'",(path,)).fetchall()
            if len(rows)!=1 or type(rows[0][0]) is not int or rows[0][0]<minimum:raise RuntimeRefused('SEAL_STORAGE_UNRESERVED')
        finally:db.close()
    except (sqlite3.Error,OSError):raise RuntimeRefused('SEAL_STORAGE_UNRESERVED') from None


def seal_receipt(project_id,evidence,seal_id):
    if seal_id not in evidence['seals']:raise RuntimeRefused('SEAL_NOT_FOUND')
    row=evidence['seals'][seal_id];c=row['creation'];p=c['protocol']
    return {'schema':'synthetic-seal-receipt-v1','project_id':project_id,'seal_id':seal_id,
        'status':row['status'],'protocol_sha256':c['protocol_sha256'],'development_run_id':p['development_run_id'],
        'development_sha256':p['development_sha256'],'created_at':c['created_at'],'creation_sequence':row['creation_sequence'],
        'creation_event_sha256':hashlib.sha256(canonical(evidence['events'][row['creation_sequence']-1])).hexdigest(),
        'invalidation':row['invalidation'],'development_admitted':row['admission'] is not None,
        'ticket_sha256':row['admission']['ticket_sha256'] if row['admission'] else None,
        'admission_sequence':row['admission_sequence'],
        'admission_event_sha256':hashlib.sha256(canonical(evidence['events'][row['admission_sequence']-1])).hexdigest() if row['admission'] else None,'financial_accepted':False}


def _freeze_ticket(project_id,seals,seal_id,ticket,pin):
    from .shortlist_ticket import read_ticket
    v=read_ticket(canonical(ticket),expected_sha256=pin);p=v['pair']
    if v['project_id']!=project_id or p['source']['seal_id']!=seal_id:raise RuntimeRefused('SHORTLIST_SOURCE_REQUIRED')
    for lane in ('source','wheel'):
        row=seals.get(p[lane]['seal_id'])
        if row is None or row['status']!='SEALED' or row['admission'] is None:raise RuntimeRefused('SHORTLIST_SEAL_UNVERIFIED')
        c=row['creation'];protocol=c['protocol']
        if c['protocol_sha256']!=v['protocol_sha256'][lane] or protocol['development_run_id']!=p[lane]['run_id'] or protocol.get('clean_pair')!={'record':p,'sha256':v['pair_sha256'],'lane':lane}:raise RuntimeRefused('SHORTLIST_SEAL_UNVERIFIED')
    return v


def shortlist_receipt(project_id,evidence,seal_id):
    row=evidence['seals'].get(seal_id)
    if row is None or row['freeze'] is None:raise RuntimeRefused('SHORTLIST_NOT_FROZEN')
    record=row['freeze'];v=record['ticket'];sequence=row['freeze_sequence']
    active=all(evidence['seals'][v['pair'][lane]['seal_id']]['status']=='SEALED' for lane in ('source','wheel'))
    return dict(schema='synthetic-shortlist-receipt-v1',project_id=project_id,seal_id=seal_id,
        pair_id=v['pair']['pair_id'],pair_sha256=v['pair_sha256'],status='FROZEN' if active else 'INVALIDATED',
        ticket_sha256=record['ticket_sha256'],shortlist_sha256=v['shortlist_sha256'],freeze_sequence=sequence,
        freeze_event_sha256=hashlib.sha256(canonical(evidence['events'][sequence-1])).hexdigest(),financial_accepted=False)


def _pending_freeze(row):
    return row['status']=='SEALED' and row['freeze'] is None and row['creation']['protocol'].get('clean_pair',{}).get('lane')=='source'


class EvaluationSeals:
    """All mutations require the native evaluation lease and matching runtime."""
    def __init__(self,store):
        self.store=store
        with store._live() as guard:
            require_live_owner(store.lease,'evaluation')
            self.project=guard.project
            # Existing stores never infer unused authority from a missing table.
            evidence=self._evidence()
            with store.conn:store.conn.execute('CREATE TABLE IF NOT EXISTS evaluation_seal_events(sequence INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL)')
            self._mirror(evidence)

    def _evidence(self):
        if self.store.get_state('evaluation_status')=='EVALUATION_COMPROMISED':raise RuntimeRefused('EVALUATION_COMPROMISED')
        evidence=verify_seal_journal(self.project)
        if evidence['status']!='VERIFIED':raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
        return evidence

    def _mirror(self,evidence):
        from .clean_registration import _text
        query='SELECT sequence,'+_text('sha256',64)+','+_text('body',MAX_EVENT_BYTES)+' FROM evaluation_seal_events ORDER BY sequence LIMIT ?'
        rows=self.store.conn.execute(query,(MAX_EVENTS+1,)).fetchall()
        if len(rows)>evidence['sequence']:raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
        for n,row in enumerate(rows,1):
            raw=canonical(evidence['events'][n-1]);expected=(n,hashlib.sha256(raw).hexdigest(),raw.decode())
            if row!=expected:raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
        try:
            with self.store.conn:
                for item in evidence['events'][len(rows):]:
                    raw=canonical(item)
                    self.store.conn.execute('INSERT INTO evaluation_seal_events VALUES(?,?,?)',(item['sequence'],hashlib.sha256(raw).hexdigest(),raw.decode()))
                saved=self.store.conn.execute(query,(MAX_EVENTS+1,)).fetchall()
                expected=[(item['sequence'],hashlib.sha256(canonical(item)).hexdigest(),canonical(item).decode()) for item in evidence['events']]
                if saved!=expected:raise RuntimeRefused('SEAL_MIRROR_UNVERIFIED')
        except sqlite3.Error:raise RuntimeRefused('SEAL_MIRROR_UNVERIFIED') from None

    def _receipt(self,evidence,seal_id):return seal_receipt(self.project.project_id,evidence,seal_id)

    def _append(self,evidence,record,guard):
        sequence=evidence['sequence']+1
        live=sum(r['status']=='SEALED' for r in evidence['seals'].values())
        if record['operation']=='CREATE':live+=1
        if record['operation']=='INVALIDATE':live-=1
        pending=sum(_pending_freeze(r) for r in evidence['seals'].values())
        if record['operation']=='CREATE' and record['protocol'].get('clean_pair',{}).get('lane')=='source':pending+=1
        if record['operation']=='FREEZE_SHORTLIST' or record['operation']=='INVALIDATE' and _pending_freeze(evidence['seals'][record['seal_id']]):pending-=1
        from .final_transaction import remaining_events,FINAL_REMAINING_EVENTS
        final_pending=sum(remaining_events(r) for r in evidence['seals'].values())
        if record['operation']=='PREPARE_FINAL':final_pending+=FINAL_REMAINING_EVENTS
        if record['operation'] in ('COMPLETE_EMPTY_FINAL','INVALIDATE'):final_pending-=remaining_events(evidence['seals'][record['seal_id']])
        from .final_attempts import OPERATIONS,replay_attempt
        if record['operation'] in OPERATIONS:
            # Prove the transition before touching immutable files. Capacity is
            # charged against the post-transition state, including invalidations.
            from copy import deepcopy
            projected=dict(evidence['seals']);projected[record['seal_id']]=deepcopy(projected[record['seal_id']])
            replay_attempt(projected,record['seal_id'],record,sequence)
            final_pending=sum(remaining_events(r) for r in projected.values())
            live=sum(r['status']=='SEALED' for r in projected.values())
            pending=sum(_pending_freeze(r) for r in projected.values())
        if sequence>MAX_EVENTS or MAX_EVENTS-sequence<live+pending+final_pending:raise RuntimeRefused('SEAL_COUNT_BOUND')
        item={'schema':'synthetic-seal-event-v1','sequence':sequence,'previous_sha256':evidence['sha256'],'record':record}
        raw=canonical(item)
        if len(raw)>MAX_EVENT_BYTES:raise RuntimeRefused('SEAL_RECORD_BOUND')
        directory=_directory(self.project)
        _require_reservation(self.project,f'state/evaluation-seals/{sequence:08}.json',MAX_EVENT_BYTES)
        try:
            with guard.api.open_directory(directory):
                _flush(directory/f'{sequence:08}.json',raw)
                guard.api.publish_metadata(directory/'head.json',canonical({'sequence':sequence,'sha256':hashlib.sha256(raw).hexdigest()}))
        except (OSError,RuntimeRefused):raise RuntimeRefused('SEAL_APPEND_UNVERIFIED') from None
        evidence=self._evidence();self._mirror(evidence)
        return self._receipt(evidence,record['seal_id'])

    def _record(self,seal_id,operation):
        return {'operation':operation,'seal_id':seal_id,'created_at':datetime.now(timezone.utc).isoformat(),
            'owner_instance':self.store.lease.identity.process_instance_id,'owner_generation':self.store.lease.generation}

    def create(self,seal_id,protocol_raw,protocol_sha256):
        identifier(seal_id);protocol=read_protocol(protocol_raw,expected_sha256=protocol_sha256)
        with self.store._live() as guard:
            require_live_owner(self.store.lease,'evaluation')
            if protocol['runtime']!=json.loads(canonical(runtime_identity())):raise RuntimeRefused('SEAL_RUNTIME_CHANGED')
            from .clean_registration import owner_protocol
            owner_protocol(self.project,protocol,seal_id)
            evidence=self._evidence();self._mirror(evidence)
            if seal_id in evidence['seals']:
                row=evidence['seals'][seal_id]
                if row['creation']['protocol_sha256']!=protocol_sha256:raise RuntimeRefused('SEAL_CONFLICT')
                if row['status']!='SEALED':raise RuntimeRefused('SEAL_INVALIDATED')
                return self._receipt(evidence,seal_id)
            if len(evidence['seals'])>=MAX_SEALS:raise RuntimeRefused('SEAL_COUNT_BOUND')
            if any(r['creation']['protocol']['development_run_id']==protocol['development_run_id'] for r in evidence['seals'].values()):
                raise RuntimeRefused('SEAL_RUN_CONFLICT')
            record=self._record(seal_id,'CREATE');record.update(protocol=protocol,protocol_sha256=protocol_sha256)
            return self._append(evidence,record,guard)

    def admit(self,seal_id,ticket_sha256):
        from .development_seals import owner_ticket
        identifier(seal_id);digest(ticket_sha256)
        with self.store._live() as guard:
            require_live_owner(self.store.lease,'evaluation')
            evidence=self._evidence();self._mirror(evidence)
            if seal_id not in evidence['seals']:raise RuntimeRefused('SEAL_NOT_FOUND')
            row=evidence['seals'][seal_id];protocol=row['creation']['protocol']
            if row['status']!='SEALED':raise RuntimeRefused('SEAL_INVALIDATED')
            if protocol['runtime']!=json.loads(canonical(runtime_identity())):raise RuntimeRefused('SEAL_RUNTIME_CHANGED')
            owner_ticket(self.project,seal_id,protocol,ticket_sha256,fresh=row['admission'] is None)
            if row['admission']:
                if row['admission']['ticket_sha256']!=ticket_sha256:raise RuntimeRefused('SEAL_CONFLICT')
                return self._receipt(evidence,seal_id)
            record=self._record(seal_id,'ADMIT_DEVELOPMENT');record['ticket_sha256']=ticket_sha256
            return self._append(evidence,record,guard)

    def freeze(self,seal_id,ticket_sha256):
        from .shortlist_freeze import owner_ticket
        from .consumption import verify_consumption_guard
        identifier(seal_id);digest(ticket_sha256)
        with self.store._live() as guard:
            require_live_owner(self.store.lease,'evaluation')
            evidence=self._evidence();self._mirror(evidence);row=evidence['seals'].get(seal_id)
            if row is None:raise RuntimeRefused('SEAL_NOT_FOUND')
            if row['creation']['protocol'].get('clean_pair',{}).get('lane')!='source':raise RuntimeRefused('SHORTLIST_SOURCE_REQUIRED')
            if row['creation']['protocol']['runtime']!=json.loads(canonical(runtime_identity())):raise RuntimeRefused('SEAL_RUNTIME_CHANGED')
            if row['freeze'] is not None and row['freeze']['ticket_sha256']!=ticket_sha256:raise RuntimeRefused('SHORTLIST_CONFLICT')
            ticket=owner_ticket(self.project,seal_id,ticket_sha256,evidence)
            _freeze_ticket(self.project.project_id,evidence['seals'],seal_id,ticket,ticket_sha256)
            guard_state=verify_consumption_guard(self.project)
            if guard_state['status']!='VERIFIED':raise RuntimeRefused('EVALUATION_COMPROMISED')
            if any(ticket['pair'][lane]['seal_id'] in guard_state['consumed'] for lane in ('source','wheel')):raise RuntimeRefused('SEAL_ALREADY_CONSUMED')
            if row['freeze'] is None:
                record=self._record(seal_id,'FREEZE_SHORTLIST');record.update(ticket=ticket,ticket_sha256=ticket_sha256)
                self._append(evidence,record,guard);evidence=self._evidence()
            return shortlist_receipt(self.project.project_id,evidence,seal_id)

    def inspect_shortlist(self,seal_id):
        identifier(seal_id)
        with self.store._live():
            require_live_owner(self.store.lease,'evaluation')
            evidence=self._evidence();self._mirror(evidence)
            return shortlist_receipt(self.project.project_id,evidence,seal_id)

    def inspect(self,seal_id):
        identifier(seal_id)
        with self.store._live():
            require_live_owner(self.store.lease,'evaluation')
            evidence=self._evidence();self._mirror(evidence)
            return self._receipt(evidence,seal_id)

    def invalidate(self,seal_id,reason):
        identifier(seal_id)
        if type(reason) is not str or reason not in REASONS:raise RuntimeRefused('SEAL_INVALIDATION_DENIED')
        with self.store._live() as guard:
            require_live_owner(self.store.lease,'evaluation')
            evidence=self._evidence();self._mirror(evidence)
            receipt=self._receipt(evidence,seal_id)
            if receipt['status']=='INVALIDATED':
                if receipt['invalidation']['reason']!=reason:raise RuntimeRefused('SEAL_CONFLICT')
                return receipt
            record=self._record(seal_id,'INVALIDATE');record['reason']=reason
            return self._append(evidence,record,guard)

    def handle(self,payload):
        """Typed private owner RPC; malformed data cannot crash the owner loop."""
        try:
            if type(payload) is not dict:raise RuntimeRefused('SEAL_COMMAND_DENIED')
            op=payload.get('operation')
            if op=='create' and set(payload)=={'operation','seal_id','protocol_utf8','protocol_sha256'}:
                raw=payload['protocol_utf8']
                if type(raw) is not str or len(raw)>MAX_PROTOCOL_BYTES:raise RuntimeRefused('SEAL_RECORD_BOUND')
                return self.create(payload['seal_id'],raw.encode('utf-8'),payload['protocol_sha256'])
            if op=='admit' and set(payload)=={'operation','seal_id','ticket_sha256'}:return self.admit(payload['seal_id'],payload['ticket_sha256'])
            if op=='freeze' and set(payload)=={'operation','seal_id','ticket_sha256'}:return self.freeze(payload['seal_id'],payload['ticket_sha256'])
            if op=='prepare_final' and set(payload)=={'operation','seal_id','evaluation_id'}:
                from .final_transaction import prepare_final
                return prepare_final(self,payload['seal_id'],payload['evaluation_id'])
            if op=='start_final' and set(payload)=={'operation','seal_id','attempt_id','dispatch_sha256'}:
                from .final_dispatch import start_final
                return start_final(self,payload['seal_id'],payload['attempt_id'],payload['dispatch_sha256'])
            if op=='close_final' and set(payload)=={'operation','seal_id','attempt_id','closure_sha256'}:
                from .final_completion import close_final
                return close_final(self,payload['seal_id'],payload['attempt_id'],payload['closure_sha256'])
            if op=='abandon_final_preparation' and set(payload)=={'operation','seal_id','attempt_id'}:
                from .final_completion import abandon_preparation
                return abandon_preparation(self,payload['seal_id'],payload['attempt_id'])
            if op=='abandon_final' and set(payload)=={'operation','seal_id','attempt_id'}:
                from .final_completion import abandon_final
                return abandon_final(self,payload['seal_id'],payload['attempt_id'])
            if op=='inspect_final' and set(payload)=={'operation','seal_id'}:
                from .final_transaction import inspect_final
                return inspect_final(self,payload['seal_id'])
            if op=='inspect_shortlist' and set(payload)=={'operation','seal_id'}:return self.inspect_shortlist(payload['seal_id'])
            if op=='inspect' and set(payload)=={'operation','seal_id'}:return self.inspect(payload['seal_id'])
            if op=='invalidate' and set(payload)=={'operation','seal_id','reason'}:return self.invalidate(payload['seal_id'],payload['reason'])
            raise RuntimeRefused('SEAL_COMMAND_DENIED')
        except DataError as error:raise RuntimeRefused(error.code) from None
        except OSError:raise RuntimeRefused('SEAL_IO_UNVERIFIED') from None
        except (UnicodeError,ValueError,TypeError,KeyError,sqlite3.Error):raise RuntimeRefused('SEAL_COMMAND_UNVERIFIED') from None
