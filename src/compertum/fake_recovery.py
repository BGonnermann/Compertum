"""Bounded fake-attempt lineage across current, prior and recovery databases.

Surviving newer evidence can prove rollback. No local-only scheme can detect
replacement of every database, append-only record and retained receipt at once.
"""
import hashlib,json,os,sqlite3
from contextlib import closing
from .data.encoding import canonical
from .events import uuid
from .domain import ExecutionIntent,ExecutionDecision,RecoveryManifest,ContractError
from .execution_contracts import record_sha256
from .execution_risk import client_order_id
from .attempt_records import validate_pair,is_paper
from .paper_intent_records import STATES as PAPER_STATES,UNCONSUMED as PAPER_UNCONSUMED
from .fake_attempt_guard import MAX_ATTEMPTS,MAX_BYTES,ZERO
from .persistence import checked_path
from .runtime.errors import RuntimeRefused
from .fake_economic_opening import validate_pin,verify_opening

FAKE_UNATTEMPTED=frozenset({'CHECKED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED'})
UNATTEMPTED=FAKE_UNATTEMPTED|PAPER_UNCONSUMED
FAKE_STATES=FAKE_UNATTEMPTED|{'SUBMITTING','UNKNOWN','ACKNOWLEDGED','PARTIALLY_FILLED','FILLED','CANCELED','EXPIRED','REJECTED'}
STATES=FAKE_STATES|PAPER_STATES


def _state(conn,key):
 row=conn.execute("SELECT CASE WHEN length(CAST(value AS BLOB))<=1024 THEN value END,length(CAST(value AS BLOB)) FROM state WHERE key=?",(key,)).fetchone()
 if row is None:return None
 if row[0] is None or not 0<row[1]<=1024:raise RuntimeRefused('EXECUTION_COMPROMISED')
 return json.loads(row[0])


def _head(value):
 if (type(value) is not dict or set(value)!={'sequence','sha256'} or type(value['sequence']) is not int
     or not 0<=value['sequence']<=MAX_ATTEMPTS or type(value['sha256']) is not str or len(value['sha256'])!=64
     or any(c not in '0123456789abcdef' for c in value['sha256']) or value['sequence']==0 and value['sha256']!=ZERO):
  raise RuntimeRefused('EXECUTION_COMPROMISED')
 return value


def snapshot_attempts(conn,project_id):
 """Read lengths before materializing bounded JSON from a retained SQLite DB."""
 try:
  identity=conn.execute('SELECT CASE WHEN length(CAST(key AS BLOB))<=128 THEN key END,CASE WHEN length(CAST(value AS BLOB))<=128 THEN value END FROM metadata LIMIT 4').fetchall()
  if len(identity)!=3 or dict(identity)!={'schema_version':'1','project_id':project_id,'role':'execution'}:raise ValueError()
  opening=_state(conn,'fake_economic_opening')
  if opening is not None:validate_pin(opening)
  head=_state(conn,'fake_attempt_guard_head')
  if head is not None:_head(head)
  compromised=_state(conn,'fake_attempt_conflict') not in (None,False) or _state(conn,'execution_status') not in (None,'VERIFIED')
  rows=[]
  if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fake_intents'").fetchone():
   values=conn.execute("SELECT CASE WHEN length(CAST(account AS BLOB))<=128 THEN account END,CASE WHEN length(CAST(intent_id AS BLOB))<=128 THEN intent_id END,CASE WHEN length(CAST(client_id AS BLOB))<=128 THEN client_id END,CASE WHEN length(CAST(state AS BLOB))<=128 THEN state END,CASE WHEN length(CAST(body AS BLOB))<=65536 THEN body END,CASE WHEN length(CAST(decision AS BLOB))<=65536 THEN decision END,length(CAST(body AS BLOB))+length(CAST(decision AS BLOB)),CASE WHEN typeof(conflict)='integer' THEN conflict END FROM fake_intents LIMIT 257").fetchall()
   if len(values)>MAX_ATTEMPTS:raise ValueError()
   for account,key,client,status,body,decision,size,conflict in values:
    if body is None or decision is None or not 0<size<=MAX_BYTES or status not in STATES or conflict not in (0,1):raise ValueError()
    compromised=compromised or conflict==1
    ip,dp,expected_client=validate_pair(json.loads(body),json.loads(decision))
    if (canonical(ip).decode()!=body or canonical(dp).decode()!=decision or account!=ip['account_alias'] or key!=ip['intent_id']
        or client!=expected_client or status not in (PAPER_STATES if is_paper(ip) else FAKE_STATES)
        or is_paper(ip) and ip['project_id']!=project_id):raise ValueError()
    rows.append(dict(intent=ip,decision=dp,client_order_id=client,attempted=status not in UNATTEMPTED))
  return dict(head=head,rows=rows,compromised=compromised,opening=opening)
 except (ValueError,TypeError,KeyError,sqlite3.Error,ContractError):raise RuntimeRefused('EXECUTION_COMPROMISED') from None


def matches_head(head,evidence):
 if evidence.get('status')!='VERIFIED':return False
 try:
  _head(head);n=head['sequence']
  return n<=evidence['sequence'] and head['sha256']==(ZERO if n==0 else evidence['hashes'][n-1])
 except (RuntimeRefused,KeyError,IndexError,TypeError):return False


def matches_snapshot(snapshot,evidence):
 if evidence.get('status')!='VERIFIED' or snapshot['compromised']:return False
 if snapshot['head'] is not None and not matches_head(snapshot['head'],evidence):return False
 records={(r['intent']['account_alias'],r['intent']['intent_id']):r for r in evidence['records']}
 for row in snapshot['rows']:
  prior=records.get((row['intent']['account_alias'],row['intent']['intent_id']))
  if prior is None:
   if row['attempted']:return False
  elif any(row[k]!=prior[k] for k in ('intent','decision','client_order_id')):return False
 return True


def matches_opening_snapshot(snapshot,opening):
 if opening['status'] not in {'VERIFIED','UNRECORDED'}:return False
 pin=snapshot.get('opening')
 return pin is None or opening['status']=='VERIFIED' and pin==opening['pin']


def validate_snapshot_boundary(snapshot,manifest):
 if snapshot.get('opening')!=manifest.get('fake_economic_opening'):raise RuntimeRefused('RECOVERY_LINEAGE_MISMATCH')
 declared=manifest.get('fake_attempt_guard')
 # A missing legacy field is unrecorded evidence, never a synthetic zero head.
 if declared!=snapshot['head'] or declared is None and any(r['attempted'] for r in snapshot['rows']):
  raise RuntimeRefused('RECOVERY_LINEAGE_MISMATCH')
 if declared is not None:_head(declared)


def _small_file(root,path,maximum):
 with checked_path(root,path).open('rb') as stream:raw=stream.read(maximum+1)
 if len(raw)>maximum:raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
 return raw


def _current_execution(root,project_id):
 pointer=root/'state/active-generation.json'
 if not pointer.exists():return root/'state/execution.sqlite',None
 value=json.loads(_small_file(root,pointer,1024))
 if (type(value) is not dict or set(value)!={'schema_version','project_id','generation','operation_id'}
     or type(value['schema_version']) is not int or value['schema_version']!=1 or value['project_id']!=project_id):raise ValueError()
 uuid(value['generation']);uuid(value['operation_id'])
 return root/'state/generations'/value['generation']/'execution.sqlite',value['generation']


def _aborted_generations(root,current):
 # An incomplete, never-admitted copy cannot have acquired execution authority.
 # Only the durable ABORTED history proves that exclusion; retain all its bytes.
 aborted=set();published=set();bindings={};references={};count=0
 with os.scandir(checked_path(root,root/'state')) as entries:
  for total,entry in enumerate(entries,1):
   if total>512:raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
   if not(entry.name.startswith('restore-') and entry.name.endswith('.jsonl')):continue
   count+=1
   if count>128:raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
   operation=entry.name[8:-6];uuid(operation)
   rows=_small_file(root,root/'state'/entry.name,65536).splitlines()
   if not 1<=len(rows)<=16:raise ValueError()
   records=[json.loads(row) for row in rows];last=records[-1]
   generation=last['generation'];uuid(generation)
   if generation in bindings and bindings[generation]!=operation:raise ValueError()
   bindings[generation]=operation
   if records[0]['status']!='PREPARING' or any(r['operation_id']!=operation or r['generation']!=generation or r.get('prior_active')!=last.get('prior_active') for r in records):raise ValueError()
   if any(r['status']=='PUBLISHED' for r in records):published.add(generation)
   prior=last.get('prior_active')
   if prior is not None:
    uuid(prior['generation']);uuid(prior['operation_id']);published.add(prior['generation'])
    if prior['generation'] in references and references[prior['generation']]!=prior['operation_id']:raise ValueError()
    references[prior['generation']]=prior['operation_id']
   if last['status']!='ABORTED' or generation==current:continue
   allowed={'PREPARING','STAGING_COORDINATOR','STAGING_EVALUATION','STAGING_EXECUTION','READY','ABORTED'}
   if any(r['status'] not in allowed for r in records):continue
   aborted.add(generation)
 for generation,operation in references.items():
  if generation in bindings and bindings[generation]!=operation:raise ValueError()
 return aborted-published


def preserved_attempt_evidence(project,evidence):
 """Read only; never repair or synthesize missing external attempt files."""
 if evidence.get('status')!='VERIFIED':return False
 root=project.root_path;opening=verify_opening(project)
 if opening['status'] not in {'VERIFIED','UNRECORDED'}:return False
 def read(path):
  path=checked_path(root,path)
  with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:snapshot=snapshot_attempts(conn,project.project_id)
  if not matches_opening_snapshot(snapshot,opening):raise RuntimeRefused('EXECUTION_COMPROMISED')
  return snapshot
 try:
  current,current_generation=_current_execution(root,project.project_id)
  if not current.is_file() or not matches_snapshot(read(current),evidence):return False
  aborted=_aborted_generations(root,current_generation)
  original=root/'state/execution.sqlite'
  if original.exists() and not matches_snapshot(read(original),evidence):return False
  generations=root/'state/generations'
  if generations.exists():
   with os.scandir(checked_path(root,generations)) as entries:
    for count,entry in enumerate(entries,1):
     if count>128:raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
     if entry.name in aborted:continue
     path=checked_path(root,generations/entry.name/'execution.sqlite')
     if path.exists() and not matches_snapshot(read(path),evidence):return False
  for count,path in enumerate((root/'backups').glob('*/*/manifest.json'),1):
   if count>128:raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
   with checked_path(root,path).open('rb') as stream:raw=stream.read(1048577)
   if len(raw)>1048576:raise ValueError()
   manifest=RecoveryManifest(json.loads(raw),project_root=root).to_payload()
   if manifest['project_id']!=project.project_id:raise ValueError()
   item=next(s for s in manifest['snapshots'] if s['owner_role']=='execution');source=checked_path(root,root/item['path'])
   if source.stat().st_size!=item['size_bytes'] or item['size_bytes']>16*1024**2:raise ValueError()
   with source.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
   if digest!=item['sha256']:raise ValueError()
   snapshot=read(source);validate_snapshot_boundary(snapshot,manifest)
   if not matches_snapshot(snapshot,evidence):return False
  return verify_opening(project)==opening
 except (OSError,ValueError,TypeError,KeyError,StopIteration,sqlite3.Error,ContractError,RuntimeRefused):return False
