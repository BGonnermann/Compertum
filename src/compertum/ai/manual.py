"""Sanitized, bounded manual packets. No hosted request or source execution."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import re
from compertum.domain import TaskSpec,validate_record,_schema,ContractError
from compertum.events import canonical,uuid
from compertum.persistence import checked_path
from compertum.runtime.errors import RuntimeRefused

SECRET=re.compile(r'(?i)(?:\b(?:api[_-]?key|access[_-]?token|authorization|password|broker_credentials)\b|\bsk-[a-z0-9_-]{8,}|-----BEGIN .*PRIVATE KEY|PROTECTED_SENTINEL|PROTECTED_OUTCOME)')
MAX_PACKET=128*1024


def sanitized(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_PACKET: raise RuntimeRefused('AI_INPUT_BOUND')
    try: text=raw.decode('utf-8')
    except UnicodeError: raise RuntimeRefused('AI_INPUT_ENCODING') from None
    if SECRET.search(text): raise RuntimeRefused('AI_SENSITIVE_INPUT_DENIED')
    return text


def read_json(raw):
    def pairs(items):
        obj={}
        for key,value in items:
            if key in obj: raise ValueError()
            obj[key]=value
        return obj
    try: return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except (ValueError,RecursionError): raise RuntimeRefused('AI_JSON_INVALID') from None


class ManualBridge:
    def __init__(self,storage):
        self.storage=storage;self.store=storage.store
        with self.store._live(),self.store.conn:
            self.store.conn.execute('''CREATE TABLE IF NOT EXISTS ai_tasks(
                task_id TEXT PRIMARY KEY,task TEXT NOT NULL,prompt_sha256 TEXT NOT NULL,
                packet TEXT NOT NULL,status TEXT NOT NULL,deadline TEXT NOT NULL,response TEXT)''')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS ai_budgets(task_id TEXT PRIMARY KEY,maximum INTEGER NOT NULL)')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS ai_daily_tasks(task_id TEXT PRIMARY KEY,day TEXT NOT NULL)')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS ai_requests(request_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL)')

    def bind_budget(self,task):
        p=task.to_payload();task_id=p['task_id'];maximum=p['budget']['output_bytes']
        with self.store._live(),self.store.conn:
            old=self.store.conn.execute('SELECT maximum FROM ai_budgets WHERE task_id=?',(task_id,)).fetchone()
            if old and old[0]!=maximum: raise RuntimeRefused('AI_TASK_CONFLICT')
            self.store.conn.execute('INSERT OR IGNORE INTO ai_budgets VALUES(?,?)',(task_id,maximum))

    def _retain(self,task_id,name,raw):
        if len(raw)>MAX_PACKET: raise RuntimeRefused('AI_INPUT_BOUND')
        relative=f'artifacts/runs/{task_id}/ai/{name}'
        with self.store._live():
            old=self.store.conn.execute("SELECT manifest FROM reservations WHERE path=? AND status='PUBLISHED'",(relative,)).fetchone()
            if old:
                item=json.loads(old[0]);path=checked_path(self.store.root,self.store.root/relative)
                if item['sha256']!=hashlib.sha256(raw).hexdigest() or item['size_bytes']!=len(raw): raise RuntimeRefused('AI_ARTIFACT_CONFLICT')
                with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
                if digest!=item['sha256']: raise RuntimeRefused('AI_ARTIFACT_CONFLICT')
                return item
            budget=self.store.conn.execute('SELECT maximum FROM ai_budgets WHERE task_id=?',(task_id,)).fetchone()
            used=self.store.conn.execute("SELECT COALESCE(sum(CASE WHEN status IN ('PUBLISHED','ABANDONED') THEN written ELSE maximum END),0) FROM reservations WHERE task=? AND category='records' AND status!='SPLIT'",(task_id,)).fetchone()[0]
            if budget is None or used+max(1,len(raw))>budget[0]: raise RuntimeRefused('AI_OUTPUT_BUDGET')
            grant=self.storage.reserve_bytes(task_id,'records',max(1,len(raw)))
            writer=self.storage.open_artifact(grant,relative)
            try: writer.write(raw);return writer.publish()
            finally: writer.close()

    def admit_task(self,task_id):
        with self.store._live(),self.store.conn:
            day=datetime.now().astimezone().date().isoformat()
            if self.store.conn.execute('SELECT 1 FROM ai_daily_tasks WHERE task_id=?',(task_id,)).fetchone(): return
            if self.store.conn.execute('SELECT count(*) FROM ai_daily_tasks WHERE day=?',(day,)).fetchone()[0]>=8:
                raise RuntimeRefused('AI_DAILY_TASK_BUDGET')
            self.store.conn.execute('INSERT INTO ai_daily_tasks VALUES(?,?)',(task_id,day))

    def admit_request(self,task_id,maximum,kind):
        from uuid import uuid4
        with self.store._live(),self.store.conn:
            day=datetime.now().astimezone().date().isoformat()
            if (self.store.conn.execute('SELECT count(*) FROM ai_requests WHERE day=?',(day,)).fetchone()[0]>=40
                    or self.store.conn.execute('SELECT count(*) FROM ai_requests WHERE task_id=?',(task_id,)).fetchone()[0]>=maximum):
                raise RuntimeRefused('AI_REQUEST_BUDGET')
            request_id=str(uuid4())
            self.store.conn.execute("INSERT INTO ai_requests VALUES(?,?,?,?,'RESERVED')",(request_id,task_id,day,kind))
            return request_id

    def export_subscription_task(self,task,*,prompt,files=()):
        if not isinstance(task,TaskSpec): raise RuntimeRefused('AI_TASK_DENIED')
        p=task.to_payload();task_id=p['task_id']
        if p['kind']!='AI_PROPOSAL' or p['model_identity']['provider']!='manual_subscription': raise RuntimeRefused('AI_TASK_DENIED')
        sanitized(prompt.encode());inputs=[];observed=[]
        for relative in files:
            if relative not in p['permissions']['filesystem_bundle']: raise RuntimeRefused('AI_BUNDLE_DENIED')
            if not relative.startswith((f'artifacts/ai/{task_id}/input/',f'artifacts/runs/{task_id}/input/','artifacts/fixtures/')):
                raise RuntimeRefused('AI_BUNDLE_DENIED')
            path=checked_path(self.store.root,self.store.root/relative)
            with path.open('rb') as stream: raw=stream.read(MAX_PACKET+1)
            text=sanitized(raw);digest=hashlib.sha256(raw).hexdigest();observed.append(digest)
            inputs.append({'path':relative,'sha256':digest,'text':text})
        if sorted(observed)!=sorted(p['input_hashes']): raise RuntimeRefused('AI_INPUT_IDENTITY_MISMATCH')
        prompt_hash=hashlib.sha256(canonical({'prompt':prompt,'inputs':inputs})).hexdigest()
        import copy
        waiting=copy.deepcopy(p);started=datetime.now(timezone.utc)
        waiting['deadline_at']=None
        waiting['clock']={'state':'WAITING_FOR_OPERATOR','active_elapsed_seconds':0,'active_started_at':None,
            'manual_wait_started_at':started.isoformat(),'manual_deadline_at':(started+timedelta(hours=24)).isoformat(),
            'process_lease_id':None,'cpu_reserved':False}
        TaskSpec(waiting,project_root=self.store.root)
        packet={'schema_version':'1','task':waiting,'prompt':prompt,'inputs':inputs,'prompt_sha256':prompt_hash,
                'response_schema':_schema('ai_proposal.v1'),'authority':'PROPOSAL_ONLY','usage_status':'UNKNOWN'}
        raw=canonical(packet)
        with self.store._live():
            old=self.store.conn.execute('SELECT task,prompt_sha256,packet FROM ai_tasks WHERE task_id=?',(task_id,)).fetchone()
            if old:
                if old[:2]!=(canonical(p).decode(),prompt_hash): raise RuntimeRefused('AI_TASK_CONFLICT')
                return json.loads(old[2])
            self.bind_budget(task);self.admit_task(task_id);self.admit_request(task_id,p['budget']['ai_requests'],'MANUAL_PACKET')
            artifact=self._retain(task_id,'packet.json',raw)
            deadline=waiting['clock']['manual_deadline_at']
            with self.store.conn:
                self.store.conn.execute("INSERT INTO ai_tasks VALUES(?,?,?,?,'WAITING_FOR_OPERATOR',?,NULL)",(task_id,canonical(p).decode(),prompt_hash,canonical(artifact).decode(),deadline))
            return artifact

    def import_proposal(self,task_id,response_path,metadata):
        uuid(task_id)
        if not isinstance(metadata,dict) or set(metadata)!={'provider','model_label','received_at','provenance'} or metadata['provider']!='manual_subscription' or metadata['provenance'] not in {'OPERATOR_SUPPLIED','SYNTHETIC_FIXTURE'}:
            raise RuntimeRefused('AI_PROVENANCE_DENIED')
        sanitized(canonical(metadata))
        path=checked_path(self.store.root,Path(response_path))
        if not (path.is_relative_to(self.store.root/'artifacts/ai'/task_id/'input') or path.is_relative_to(self.store.root/'artifacts/inbox')): raise RuntimeRefused('AI_BUNDLE_DENIED')
        with self.store._live():
            row=self.store.conn.execute('SELECT task,prompt_sha256,deadline,response FROM ai_tasks WHERE task_id=?',(task_id,)).fetchone()
            if not row: raise RuntimeRefused('AI_TASK_UNKNOWN')
            task=json.loads(row[0]);now=datetime.now(timezone.utc)
            try: received=datetime.fromisoformat(metadata['received_at'])
            except (ValueError,TypeError): raise RuntimeRefused('AI_PROVENANCE_DENIED') from None
            if received.tzinfo is None or received.utcoffset()!=timedelta(0) or received>now or received<datetime.fromisoformat(task['created_at']): raise RuntimeRefused('AI_PROVENANCE_DENIED')
            if now>datetime.fromisoformat(row[2]): raise RuntimeRefused('MANUAL_DEADLINE_EXCEEDED')
            with path.open('rb') as stream: raw=stream.read(MAX_PACKET+1)
            sanitized(raw);digest=hashlib.sha256(raw).hexdigest()
            if row[3]:
                old=json.loads(row[3])
                if old['original']['sha256']!=digest: raise RuntimeRefused('AI_RESPONSE_CONFLICT')
                return old
            original=self._retain(task_id,'response-'+digest+'.json',raw)
            try: proposal=validate_record('ai_proposal.v1',read_json(raw))
            except (ContractError,RuntimeRefused): raise RuntimeRefused('AI_PROPOSAL_INVALID') from None
            if (proposal['task_id']!=task_id or proposal['role']!=task['role'] or proposal['prompt_sha256']!=row[1]
                    or proposal['input_hashes']!=task['input_hashes'] or proposal['provider']['name']!='manual_subscription'
                    or proposal['provider']['model_label']!=metadata['model_label'] or proposal['provider']['usage_status']=='MEASURED'):
                raise RuntimeRefused('AI_RESPONSE_MISMATCH')
            receipt={'status':'PROPOSAL_ONLY','task_id':task_id,'original':original,'metadata':dict(metadata),
                     'proposal':proposal,'executed':False,'usage_status':'UNKNOWN','hosted_response_observed':False,'operator_reports_hosted_response':metadata['provenance']=='OPERATOR_SUPPLIED'}
            retained=self._retain(task_id,'receipt.json',canonical(receipt));receipt['receipt_artifact']=retained
            with self.store.conn: self.store.conn.execute("UPDATE ai_tasks SET status='PROPOSAL_ONLY',response=? WHERE task_id=?",(canonical(receipt).decode(),task_id))
            return receipt


def provider_status():
    return {'primary':'manual_subscription','subscription_access':'OPERATOR_CONTROLLED','subscription_quota':'UNKNOWN',
            'local_qualification':'UNVERIFIED','automatic_codex':'DISABLED','broker_capability':'CAPABILITY_UNAVAILABLE'}



def export_fixture_packet(bridge,task_id):
    """M0's terminal template: only one fixed synthetic development input."""
    from compertum.foundation import fixture_spec
    uuid(task_id)
    with bridge.store._live():
        old=bridge.store.conn.execute('SELECT task FROM ai_tasks WHERE task_id=?',(task_id,)).fetchone()
        if old: p=json.loads(old[0])
        else:
            bridge.admit_task(task_id)
            p=fixture_spec(bridge.store.root,task_id).to_payload()
            p.update(kind='AI_PROPOSAL',role='research_proposer',model_identity={'provider':'manual_subscription','model_label':'operator supplied','sha256':None})
            p['permissions']['tools']=[];p['budget'].update(output_bytes=256*1024,ai_requests=2,input_tokens=16384,output_tokens=2048,request_deadline_seconds=120)
            raw=b'M0 synthetic arithmetic fixture: 2 + 2 = 4. No market or protected data.'
            relative=f'artifacts/runs/{task_id}/input/fixture.txt'
            grant=bridge.storage.reserve_bytes(task_id,'records',len(raw));writer=bridge.storage.open_artifact(grant,relative)
            try: writer.write(raw);writer.publish()
            finally: writer.close()
            p['input_hashes']=[hashlib.sha256(raw).hexdigest()];p['permissions']['filesystem_bundle']=[relative]
        task=TaskSpec(p,project_root=bridge.store.root)
        return bridge.export_subscription_task(task,prompt='Review the synthetic fixture. Return only an AIProposal matching the supplied schema and identities. Proposed text is never executed.',files=p['permissions']['filesystem_bundle'])
