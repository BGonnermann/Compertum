"""Private native activity collection. Missing accounting evidence stays blocking."""
import base64,json,re,time
from uuid import uuid4
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier,strict_json,utc
from compertum.paper_activity_records import prepare_activity_request,parse_activity_page,activity_traversal,sha
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_account_context import _PaperAccountContext
from .paper_portfolio_context import _portfolio_context,_journal_snapshot
from .paper_opening import _original
from .paper_preflight import _measure
from .paper_input_context import _final_account
from .paper_final_proof import _health_finish,_health_state
from .paper_credential_slot import load_paper_slot
from .paper_credentials import ProtectedPaperCredentials,open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from .service_budget import producer_permit,bind_producer_permit,cancel_producer
from ._winhttp_activity import _OwnedActivityGet

_PREFIX='paper_activity:'
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,UnicodeError,RecursionError)


def _need(value,code='PAPER_ACTIVITY_INVALID'):
    if not value:raise RuntimeRefused(code)


class _ActivityProducer:
    def __init__(self,owner,context,activity_id,*,_test_port=None):
        _need(type(context) is _PaperAccountContext and context._owner is owner and owner._account_context is context)
        _need(_test_port is None or type(_test_port) is int and 1<=_test_port<=65535)
        self._owner=owner;self._lease=owner.lease;self._context_input=context;self._portfolio=_portfolio_context(context)
        self._port=_test_port;self._id=identifier(activity_id);self._closed=False;self._pending=None;self._request=None
        self._pages=[];self._attempts=[];self._state='READY';self._reason=None;self._provenance=None
        self._start_wall,self._start_mono=_measure();self._started_ns=time.monotonic_ns();self._deadline_ns=self._started_ns+20*10**9
        self._last_wall=self._start_wall;self._last_mono=self._start_mono
        v=context.diagnostic();self._alias=v['account_alias'];self._protected=load_paper_slot(owner.lease,self._alias)
        self._credential=sha(self._protected.ciphertext);self._generation=owner.lease.generation
        self._instance=owner.lease.identity.process_instance_id;self._account=owner.preflight(context._packet)._account_id
        opening,_=_original(owner,self._alias);self._opening=opening['sha256'];self._history=_journal_snapshot(owner)['sha256']
        self._context_binding=context._binding
        self._seed=dict(project_id=owner.lease.project_id,account_alias=self._alias,opening_sha256=self._opening,
            account_context_sha256=self._context_binding,history_sha256=self._history,credential_sha256=self._credential,
            after=utc(opening['reference']['confirmed_at']),until=utc(self._start_wall.isoformat()),started_at=utc(self._start_wall.isoformat()))
        self._anchor=sha(canonical(self._anchor_value()))
        self._seal();self._check()
    def __repr__(self):return '<PrivateActivityProducer redacted>'
    def __reduce_ex__(self,p):raise RuntimeRefused('PAPER_ACTIVITY_SERIALIZATION_FORBIDDEN')
    def _signature(self):
        return sha(canonical(dict(pages=[dict(request=p.request.sha256,raw=sha(p.raw),parsed=sha(p.content)) for p in self._pages],
            attempts=self._attempts,state=self._state,reason=self._reason,provenance=self._provenance,
            request=None if self._request is None else self._request.sha256,pending=None if self._pending is None else id(self._pending))))
    def _seal(self):self._signature_sha=self._signature()
    def _anchor_value(self):
        return dict(seed=self._seed,activity_id=self._id,account=sha(self._account.encode()),port=self._port,
            generation=self._generation,instance=self._instance,started_ns=self._started_ns,deadline_ns=self._deadline_ns,start_mono=self._start_mono)
    def _integrity(self):
        require_live_owner(self._lease,'execution')
        _need(type(self._protected) is ProtectedPaperCredentials and self._protected.project_id==self._lease.project_id
            and self._protected.account_alias==self._alias and sha(self._protected.ciphertext)==self._credential==self._seed['credential_sha256'],
            'PAPER_ACTIVITY_CREDENTIAL_CHANGED')
        _need(self._signature()==self._signature_sha,'PAPER_ACTIVITY_EVIDENCE_CHANGED')
        _need(self._generation==self._lease.generation and self._instance==self._lease.identity.process_instance_id)
        _need(self._anchor==sha(canonical(self._anchor_value())))
    def _check(self,full=True):
        self._integrity();o=self._owner;c=self._context_input
        _need(not self._closed and o._account_context is c and c._owner is o and not c._closed,'PAPER_ACTIVITY_CONTEXT_CHANGED')
        _need(c._binding==self._context_binding and self._protected.account_alias==self._alias)
        if full:
            _need(sha(load_paper_slot(self._lease,self._alias).ciphertext)==self._credential)
            self._portfolio._prepare_proof()._verify()
        else:
            _need(o.health.reason is None and not o._closed)
            _final_account(o._preflight);_health_finish(o,o.health,_health_state(o.health))
        now,mono=_measure()
        _need(now>=self._last_wall and mono>=self._last_mono,'PAPER_ACTIVITY_CLOCK')
        wall=(now-self._start_wall).total_seconds();elapsed=mono-self._start_mono
        _need(abs(wall-elapsed)<=5 and max(wall,elapsed)<20 and time.monotonic_ns()<self._deadline_ns,'PAPER_ACTIVITY_DEADLINE')
        self._last_wall=now;self._last_mono=mono
        return utc(now.isoformat()),min(10,20-max(wall,elapsed),(self._deadline_ns-time.monotonic_ns())/10**9)
    def _attach(self,native):
        _need(type(native) is _OwnedActivityGet and self._pending is None)
        self._pending=native;self._seal()
    def _before_send(self,native):
        _need(native is self._pending and native._source_request is self._request)
        self._check();self._attempts[-1]['pre_send_ns']=time.monotonic_ns();self._seal()
    def _committed(self,native):
        _need(native is self._pending);self._check(full=False)
        self._attempts[-1]['committed_ns']=time.monotonic_ns();self._seal()
    def _cleanup(self):
        cancel_producer(self)
        if self._pending is not None:
            self._attempts[-1]['status']=self._pending.status_code
            self._pending.close()
            _need(self._pending.native_closed,'HTTP_CLEANUP_UNVERIFIED')
            self._attempts[-1]['native_closed']=True;self._pending._result=None;self._pending=None;self._seal()
    def stop(self,reason,state='INCOMPLETE'):
        clean=True
        try:self._cleanup()
        except RuntimeRefused:reason='NATIVE_CLEANUP_UNVERIFIED';state='INCOMPLETE';clean=False
        finally:self._state=state;self._reason=reason;self._seal()
        return clean
    def dispatch(self):
        try:
            at,budget=self._check();_need(self._state=='READY' and len(self._attempts)<8)
            permit=producer_permit(self)
            if permit is None:return
            token=None if not self._pages else self._pages[-1].to_payload()['rows'][-1]['id']
            self._request=prepare_activity_request(expected_account_id=self._account,**self._seed,
                created_at=at,request_id=str(uuid4()),page_token=token)
            self._state='PENDING';self._attempts.append(dict(request=json.loads(self._request.content),request_sha256=self._request.sha256,pre_send_ns=None,
                committed_ns=None,native_closed=False,status=None));self._seal();bind_producer_permit(self,permit)
            with open_paper_credentials(self._lease,self._protected) as opened:
                values=tuple(opened.headers().values());_reject_reflections(self._request.content,values)
                _,remaining=self._check(full=False);budget=min(budget,remaining,self._request.to_payload()['timeout_ms']/1000)
                _OwnedActivityGet(self,self._request,opened.headers() if self._port is None else {'X-Compertum-Test':'synthetic'},permit,budget)
        except BaseException as error:self.stop(getattr(error,'code','DISPATCH_FAILED'));raise
    def poll(self):
        try:
            self._check(full=False);_need(self._state=='PENDING' and type(self._pending) is _OwnedActivityGet)
            native=self._pending;result=native.poll()
            if result is None:return
            at,_=self._check();_need(native._result is result and native.native_closed and native._source_request is self._request)
            _need(native._request_bytes==self._request.content and native._origin==native._activity_origin)
            with open_paper_credentials(self._lease,self._protected) as opened:_reject_reflections(result.body,tuple(opened.headers().values()))
            page=parse_activity_page(self._request,result.body,received_at=at)
            summary=activity_traversal(tuple([*self._pages,page]));self._check()
            self._pages.append(page);self._attempts[-1]['status']=result.status_code
            self._provenance='PAPER_TLS' if self._port is None else 'LOOPBACK_FIXTURE';self._cleanup()
            self._state='COMPLETE' if summary['traversal_complete'] else 'INCOMPLETE' if len(self._pages)==8 else 'READY'
            self._reason='ACTIVITIES_TRUNCATED' if self._state=='INCOMPLETE' else None;self._seal()
        except BaseException as error:self.stop(getattr(error,'code','RESPONSE_FAILED'));raise
    def summary(self):
        _need(self._signature()==self._signature_sha,'PAPER_ACTIVITY_EVIDENCE_CHANGED')
        value=activity_traversal(tuple(self._pages)) if self._pages else dict(status='BLOCKED',traversal_complete=False,pages=0,rows=0,
            raw_bytes=0,deficiencies=['NO_ACTIVITY_RESPONSE','OWNERSHIP_UNVERIFIED','ECONOMIC_COVERAGE_UNVERIFIED',
                'FEE_LIABILITIES_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED','NATIVE_PROVENANCE_UNVERIFIED'],
            native_transport_verified=False,financial_accepted=False,transport_authorized=False,actual_flat=None)
        return dict(value,attempts=len(self._attempts),native_closed=self._pending is None or self._pending.native_closed,reason=self._reason)
    def snapshot(self):
        self._integrity()
        summary=self.summary();_need(self._state in {'COMPLETE','INCOMPLETE','CANCELED'})
        return dict(version=1,purpose='HISTORICAL_ACTIVITY_ONLY',activity_id=self._id,bindings=self._seed,binding=self._anchor_value(),plan_sha256=self._anchor,
            account_identity_sha256=sha(self._account.encode()),expected_account_id=self._account,
            execution_generation=self._generation,execution_instance=self._instance,attempts=self._attempts,
            provenance=self._provenance or 'NO_RESPONSE',state=self._state,reason=self._reason,summary=summary,
            pages=[dict(request=json.loads(p.request.content),raw_utf8=p.raw.decode('utf-8'),parsed=json.loads(p.content)) for p in self._pages])
    def close(self):
        with _MUTEX:
            self._cleanup();self._closed=True;self._portfolio.close()


def _new_producer(*args,**kwargs):return _ActivityProducer(*args,**kwargs)


class _ActivityOwner:
    def __init__(self,owner):
        _need(not owner.db.in_transaction,'PAPER_ACTIVITY_TRANSACTION_OPEN')
        self.o=owner;self._producer=None;self._cipher=None;self._active=None
        for aid in self._keys():
            v=self._read(aid)
            if v['state'] in {'PREPARED','AUTHORIZED','RUNNING','EVIDENCE_READY'}:
                v.update(state='INTERRUPTED',reason='OWNER_RESTARTED');self._save(v)
    def _keys(self):
        rows=self.o.db.execute('SELECT key FROM state WHERE substr(key,1,?)=? LIMIT 33',(len(_PREFIX),_PREFIX)).fetchall()
        _need(len(rows)<=32);return [row[0][len(_PREFIX):] for row in rows]
    def _validate(self,v):
        _need(type(v) is dict and set(v)=={'version','activity_id','subject','packet_id','task_id','reservation_id','account_alias','plan_sha256','binding','state','reason','evidence','manifest','summary'})
        _need(type(v['version']) is int and v['version']==1)
        for k in ('activity_id','packet_id','task_id','reservation_id'):identifier(v[k])
        _need(type(v['subject']) is str and re.fullmatch('[0-9a-f]{64}',v['subject']) is not None)
        _need(type(v['plan_sha256']) is str and re.fullmatch('[0-9a-f]{64}',v['plan_sha256']) is not None)
        from .paper_activity_evidence import validate_binding,validate_summary,_manifest,_evidence
        validate_binding(v['binding'],self.o.lease.project_id,v['account_alias'],v['activity_id'])
        _need(v['plan_sha256']==sha(canonical(v['binding'])))
        _need(type(v['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v['account_alias']) is not None)
        _need(v['reason'] is None or type(v['reason']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',v['reason']) is not None)
        if v['evidence'] is not None:_evidence(v['evidence'])
        if v['manifest'] is not None:
            _manifest(v['manifest'],v['task_id'],v['activity_id'])
            _need(v['evidence']==dict(size_bytes=v['manifest']['size_bytes'],sha256=v['manifest']['sha256']))
        if v['summary'] is not None:validate_summary(v['summary'])
        if v['state']=='PUBLISHED':_need(v['manifest'] is not None and v['evidence'] is not None)
        _need(v['state'] in {'PREPARED','AUTHORIZED','RUNNING','EVIDENCE_READY','PUBLISHED','ABORTED','CANCELED','INTERRUPTED'})
        _need(len(canonical(v))<=16384)
        return v
    def _read(self,aid):
        identifier(aid);row=self.o.db.execute('SELECT CASE WHEN length(CAST(value AS BLOB))<=16384 THEN value END FROM state WHERE key=?',(_PREFIX+aid,)).fetchone()
        _need(row is not None and row[0] is not None,'PAPER_ACTIVITY_UNKNOWN')
        v=self._validate(strict_json(row[0].encode()));_need(v['activity_id']==aid);return v
    def _save(self,v,new=False):
        _need(not self.o.db.in_transaction,'PAPER_ACTIVITY_TRANSACTION_OPEN')
        self._validate(v);raw=canonical(v).decode();key=_PREFIX+v['activity_id']
        with self.o.db:
            if new:c=self.o.db.execute('INSERT INTO state VALUES(?,?)',(key,raw))
            else:
                old=self._read(v['activity_id'])
                _need(all(old[k]==v[k] for k in ('activity_id','subject','packet_id','task_id','reservation_id','account_alias','plan_sha256','binding')))
                c=self.o.db.execute('UPDATE state SET value=? WHERE key=? AND value=?',(raw,key,canonical(old).decode()))
            _need(c.rowcount==1 and self._read(v['activity_id'])==v,'PAPER_ACTIVITY_WRITE_UNVERIFIED')
    def _public(self,v):
        return {k:value for k,value in v.items() if k not in {'subject','binding'}}
    def handle(self,packet):
        try:
            _need(not self.o.db.in_transaction,'PAPER_ACTIVITY_TRANSACTION_OPEN')
            _need(type(packet) is dict and set(packet)=={'subject_key','command'})
            subject=packet['subject_key'];c=packet['command'];_need(type(c) is dict);op=c.get('operation');aid=c.get('activity_id');identifier(aid)
            fields={'prepare':{'packet_id','task_id','reservation_id'},'authorize':{'plan_sha256'},'start':{'plan_sha256'},'status':set(),'cancel':set()}
            _need(op in fields and set(c)==fields[op]|{'operation','activity_id'})
            if op=='prepare' and aid not in self._keys():
                _need(self._active is None and len(self._keys())<32,'PAPER_ACTIVITY_BUSY')
                ctx=self.o._account_context
                if ctx is None:ctx=self.o.account_context(subject=subject,packet_id=c['packet_id'])
                _need(type(ctx) is _PaperAccountContext and ctx._subject==subject and ctx._packet==c['packet_id'])
                producer=_new_producer(self.o,ctx,aid)
                self.o._reservation(dict(reservation_id=c['reservation_id'],task_id=c['task_id']))
                v=dict(version=1,activity_id=aid,subject=subject,packet_id=c['packet_id'],task_id=c['task_id'],reservation_id=c['reservation_id'],
                    account_alias=producer._alias,plan_sha256=producer._anchor,binding=producer._anchor_value(),state='PREPARED',reason=None,evidence=None,manifest=None,summary=None)
                self._save(v,new=True);self._producer=producer;self._active=aid
            else:
                v=self._read(aid);_need(v['subject']==subject,'PAPER_ACTIVITY_SUBJECT_CHANGED')
                if op=='prepare':_need(all(v[k]==c[k] for k in fields['prepare']))
                if op in {'authorize','start'}:
                    _need(c['plan_sha256']==v['plan_sha256'])
                    if v['state'] not in {'RUNNING','EVIDENCE_READY','PUBLISHED'}:
                        _need(self._active==aid and self._producer is not None)
                        self._producer._check()
                        if op=='authorize':_need(v['state'] in {'PREPARED','AUTHORIZED'});v['state']='AUTHORIZED'
                        else:_need(v['state']=='AUTHORIZED');v['state']='RUNNING'
                        self._save(v)
                if op=='cancel' and v['state'] in {'PREPARED','AUTHORIZED','RUNNING'}:
                    _need(self._active==aid);clean=self._producer.stop('CANCELED','CANCELED');v['state']='CANCELED';self._finish(v)
                    if not clean:raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')
            return self._public(v)
        except _INVALID:raise RuntimeRefused('PAPER_ACTIVITY_INVALID') from None
    def _finish(self,v):
        from .paper_activity_evidence import protect_activity_evidence
        v['summary']=self._producer.summary();v['reason']=self._producer._reason
        self._cipher=protect_activity_evidence(self.o.lease,v['account_alias'],v['task_id'],v['activity_id'],self._producer)
        v['evidence']=dict(size_bytes=len(self._cipher.ciphertext),sha256=sha(self._cipher.ciphertext));self._save(v)
    def tick(self):
        if self._active is None:return
        v=self._read(self._active)
        if v['state']!='RUNNING':return
        try:
            p=self._producer
            if p._state=='READY':p.dispatch()
            elif p._state=='PENDING':p.poll()
            if p._state in {'COMPLETE','INCOMPLETE'}:
                v['state']='EVIDENCE_READY' if p._state=='COMPLETE' else 'ABORTED';self._finish(v)
        except (RuntimeRefused,*_INVALID) as error:
            self._producer.stop(self._producer._reason or getattr(error,'code','COLLECTION_FAILED'));v['state']='ABORTED';self._finish(v)
    def transfer(self,c):
        _need(not self.o.db.in_transaction,'PAPER_ACTIVITY_TRANSACTION_OPEN')
        from .paper_activity_evidence import verify_activity_publication
        _need(type(c) is dict and c.get('operation') in {'chunk','ack'});v=self._read(c.get('activity_id'))
        if c['operation']=='ack':
            _need(set(c)=={'operation','activity_id','manifest'} and v['evidence'] is not None)
            history=verify_activity_publication(self.o.lease,v['account_alias'],v['activity_id'],v['task_id'],c['manifest'],v['evidence'])['collection']
            _need(history['plan_sha256']==v['plan_sha256'] and history['binding']==v['binding'] and history['summary']==v['summary'],
                'PAPER_ACTIVITY_PUBLICATION_CHANGED')
            _need(v['manifest'] is None or v['manifest']==c['manifest'])
            v.update(state='PUBLISHED',manifest=c['manifest']);self._save(v)
            if self._active==v['activity_id']:self._cipher=None;self._active=None
            return self._public(v)
        _need(set(c)=={'operation','activity_id','offset','sha256'} and self._active==v['activity_id'] and self._cipher is not None)
        raw=self._cipher.ciphertext;offset=c['offset']
        _need(type(offset) is int and 0<=offset<len(raw) and offset%32768==0 and c['sha256']==sha(raw))
        return dict(project_id=self.o.lease.project_id,account_alias=v['account_alias'],task_id=v['task_id'],activity_id=v['activity_id'],
            sha256=sha(raw),total_bytes=len(raw),offset=offset,data=base64.b64encode(raw[offset:offset+32768]).decode())
    def require_checkpoint(self):
        _need(self._active is None and (self._producer is None or self._producer.summary()['native_closed']),'PAPER_ACTIVITY_CHECKPOINT_BUSY')
    def close(self):
        if self._producer is not None:self._producer.close()
        self._cipher=None;self._active=None
