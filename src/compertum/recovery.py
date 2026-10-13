"""Synthetic recovery only. Publication is a barrier; activation is disarmed."""
from contextlib import ExitStack
import json, os, sqlite3, time,sys,platform,importlib.metadata
from pathlib import Path
from .domain import ContractError,atomic_json,now,new_id,file_hash,within,validate_record,digest,canonical
from .persistence import DB_NAMES
from .consumption import verify_consumption_guard
from .runtime.owners import verify_prior_exit

def collect_recovery_set(project,owners,manager):
    stores=sorted(owners,key=lambda s:s.role)
    if {s.role for s in stores}!=set(DB_NAMES) or len(stores)!=3:raise ContractError('RECOVERY_OWNERS_INCOMPLETE')
    rid=new_id();barrier=new_id();base='backups/'+rid;started=time.monotonic()
    snapshots=[];artifacts=[];pending=[]
    with ExitStack() as stack:
        for store in stores:
            store.lease.verify()
            if store.lease.project.project_id!=project.project_id:raise ContractError('RECOVERY_PROJECT_MISMATCH')
            if not store.lock.acquire(timeout=max(0,30-(time.monotonic()-started))):raise ContractError('BARRIER_DEADLINE')
            stack.callback(store.lock.release)
        # Delivery/mutation uses these same locks. Each high-water belongs to one barrier.
        refs={}
        for store in stores:
            for raw, in store.db.execute("SELECT payload FROM events WHERE kind='ARTIFACT_REGISTERED'"):
                event=json.loads(raw);ref=event['payload'];refs[ref['path']]=ref
        queue=list(refs.values());seen=set()
        while queue:
            ref=queue.pop()
            if ref['path'] in seen:continue
            seen.add(ref['path']);source=within(project.root_path,ref['path'])
            if not source.is_file() or file_hash(source)!=ref['sha256']:raise ContractError('RECOVERY_ARTIFACT_INVALID')
            target=base+'/artifacts/'+str(len(artifacts));grant=manager.reserve_bytes(rid,'backups',max(1,source.stat().st_size))
            writer=manager.open_artifact(grant,target)
            try:
                with source.open('rb') as f:
                    while chunk:=f.read(1024**2):writer.write(chunk)
                manifest=writer.publish()
            finally:writer.close()
            artifacts.append({'original_path':ref['path'],**manifest})
            queue.extend(ref.get('references',[]))
        for store in stores:
            if time.monotonic()-started>=30:raise ContractError('BARRIER_DEADLINE')
            # Reserve before SQLite backup; max_page_count bounds every store to 1 GiB.
            pages=store.db.execute('PRAGMA page_count').fetchone()[0];size=pages*store.db.execute('PRAGMA page_size').fetchone()[0]
            stage_grant=manager.reserve_bytes(rid,'backups',max(4096,size+4096))
            grant=manager.reserve_bytes(rid,'backups',max(1,size))
            temp=within(project.root_path,base+'/'+store.role+'.snapshot')
            snap=store.checkpoint(barrier,temp)
            if temp.stat().st_size>stage_grant.maximum:raise ContractError('SNAPSHOT_CAPACITY')
            with manager.store.transaction():manager.store.db.execute('UPDATE storage_grants SET state=?,written=?,path=? WHERE grant_id=?',('PUBLISHED',temp.stat().st_size,str(temp.relative_to(project.root_path)),stage_grant.grant_id))
            writer=manager.open_artifact(grant,base+'/'+DB_NAMES[store.role])
            try:
                with temp.open('rb') as f:
                    while chunk:=f.read(1024**2):writer.write(chunk)
                saved=writer.publish()
            finally:writer.close()
            # Retain staging too; allocation is independently counted.
            snap.update(path=saved['path'],sha256=saved['sha256']);snapshots.append(snap)
            pending.extend({'sender':store.role,**event} for event in snap['pending_messages'])
        guard=verify_consumption_guard(project)
        guard_files=[]
        directory=project.root_path/'state/evaluation-consumption'
        if directory.exists():
            for source in sorted(directory.glob('*.json')):
                grant=manager.reserve_bytes(rid,'backups',max(1,source.stat().st_size));writer=manager.open_artifact(grant,base+'/guard/'+source.name)
                try:writer.write(source.read_bytes());guard_files.append(writer.publish())
                finally:writer.close()
        guard['files']=guard_files
        source=Path(__file__).resolve().parent
        result={'schema_version':1,'recovery_id':rid,'project_id':project.project_id,'at':now(),'barrier_id':barrier,'databases':snapshots,'artifacts':artifacts,'consumption_guard':guard,'generations':{s.role:s.lease.generation for s in stores},'pending_messages':pending,'halted':True,'reserve_bytes':0,'code_hash':digest({str(p.relative_to(source)):file_hash(p) for p in source.rglob('*.py')}),'environment_hash':digest({'python':sys.version,'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),'httpx':importlib.metadata.version('httpx'),'jsonschema':importlib.metadata.version('jsonschema')}),'config_hash':file_hash(source/'resources/default.toml')}
        validate_record('recovery_manifest',result)
        # Ack must refer to an inbox of identical content. Unacked messages may already be accepted.
        all_inbox={item['event_id']:item['hash'] for s in snapshots for item in s['inbox']}
        for store in stores:
            for eid,h in store.db.execute('SELECT e.event_id,e.hash FROM events e JOIN outbox o USING(event_id) WHERE o.acked=1'):
                if all_inbox.get(eid)!=h:raise ContractError('BARRIER_ACK_WITHOUT_INBOX')
        if time.monotonic()-started>=30:raise ContractError('BARRIER_DEADLINE')
        destination=within(project.root_path,base+'/manifest.json');payload=canonical(result);g=manager.reserve_bytes(rid,'backups',len(payload));writer=manager.open_artifact(g,str(destination.relative_to(project.root_path)))
        try:writer.write(payload);writer.publish()
        finally:writer.close()
        validate_recovery_set(project,destination)
        return result

def validate_recovery_set(project,manifest_path):
    path=Path(manifest_path).resolve()
    if not path.is_relative_to(project.root_path):raise ContractError('RECOVERY_PATH')
    m=validate_record('recovery_manifest',json.loads(path.read_text()))
    if m['project_id']!=project.project_id or {s['role'] for s in m['databases']}!=set(DB_NAMES) or len(m['databases'])!=3:raise ContractError('RECOVERY_PROJECT_OR_ROLES')
    for ref in m['databases']+m['artifacts']+m['consumption_guard'].get('files',[]):
        source=within(project.root_path,ref['path'])
        if not source.is_file() or file_hash(source)!=ref['sha256']:raise ContractError('RECOVERY_HASH_INVALID')
    for ref in m['databases']:
        if ref['barrier_id']!=m['barrier_id'] or ref['generation']!=m['generations'][ref['role']]:raise ContractError('RECOVERY_BARRIER_MISMATCH')
        db=sqlite3.connect('file:'+str(within(project.root_path,ref['path']))+'?mode=ro',uri=True)
        try:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ContractError('RECOVERY_SQLITE_CORRUPT')
            high=db.execute('SELECT coalesce(max(seq),0) FROM events').fetchone()[0]
            inbox=[{'event_id':r[0],'hash':r[1]} for r in db.execute('SELECT event_id,hash FROM inbox ORDER BY event_id')]
            pending=[json.loads(r[0]) for r in db.execute('SELECT e.payload FROM events e JOIN outbox o USING(event_id) WHERE o.acked=0 ORDER BY e.seq')]
            if high!=ref['outbox_high_water'] or inbox!=ref['inbox'] or pending!=ref['pending_messages']:raise ContractError('RECOVERY_MESSAGE_MISMATCH')
        finally:db.close()
    expected=[{'sender':s['role'],**e} for s in m['databases'] for e in s['pending_messages']]
    if expected!=m['pending_messages']:raise ContractError('RECOVERY_MESSAGE_MISMATCH')
    return m

def restore_recovery_set(lease,manifest_path,destination=None,fail_after=None):
    lease.verify()
    if lease.role!='recovery':raise ContractError('RECOVERY_OWNER_REQUIRED')
    root=lease.project.root_path
    # Take native exclusive handles and prove previous process exit before touching state.
    from .runtime import win32 as w
    handles=[]
    try:
        for role in DB_NAMES:
            lock=root/'state/locks'/(role+'.lock')
            h=w.CreateFile(str(lock),0xC0000000,0,None,4,0,None)
            if h==w.INVALID:raise ContractError('RESTORE_WRITER_LIVE')
            handles.append(h)
            meta=root/'state/runtime'/(role+'.json')
            if meta.exists():verify_prior_exit(json.loads(meta.read_text()))
        m=validate_recovery_set(lease.project,manifest_path);guard=verify_consumption_guard(lease.project)
        known=dict(guard['consumed']);latest=guard.get('head',{}).get('sequence',-1)
        def mirror(path):
            if not path.exists():return
            db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
            try:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ContractError('CONSUMPTION_MIRROR_UNVERIFIED')
                for seal,status,eid in db.execute('SELECT seal_id,status,evaluation_id FROM seals'):
                    if not seal.startswith('synthetic-'):raise ContractError('M0_ONLY_SYNTHETIC_GUARD')
                    if status=='CONSUMED':known[seal]=eid
            finally:db.close()
        pointer=root/'state/active-recovery.json'
        active=within(root,json.loads(pointer.read_text())['path']) if pointer.exists() else root/'state'
        mirror(active/DB_NAMES['evaluation'])
        # Retained, complete later backups are independent sticky consumption evidence.
        for candidate in (root/'backups').glob('*/manifest.json'):
            try:other=validate_recovery_set(lease.project,candidate)
            except (OSError,ValueError):continue
            latest=max(latest,other['consumption_guard'].get('head',{}).get('sequence',-1))
            for ref in other['databases']:
                if ref['role']=='evaluation':mirror(within(root,ref['path']))
        established=guard['verified'] and guard['head']['sequence']>=latest and all(guard['consumed'].get(s)==eid for s,eid in known.items())
        # All store owners are stopped; recovery owns this separate reservation record.
        # Charge simultaneous databases + rollback journals + bounded metadata BEFORE writing.
        from .storage import sample_storage,CAPS
        if len(known)>4096:raise ContractError('RESTORE_CONSUMPTION_CAPACITY')
        reserved=2*sum(within(root,r['path']).stat().st_size for r in m['databases'])+len(known)*8192+1024**2
        observation=sample_storage(root)
        if observation['unexpected_reparse'] or observation['used']['records']+reserved>CAPS['records'] or observation['total']+reserved>50*1024**3 or observation['free_bytes']-reserved<50*1024**3:raise ContractError('RESTORE_STORAGE_LIMIT')
        atomic_json(root/'state/recovery-reservation.json',{'recovery_id':m['recovery_id'],'reserved_bytes':reserved,'owner_generation':lease.generation,'state':'RESERVED','at':now()})
        target=within(root,destination or ('state/restores/'+new_id()))
        target.mkdir(parents=True,exist_ok=False)
        journal=root/'state/restore-operation.json'
        pointer=root/'state/active-recovery.json';previous=json.loads(pointer.read_text()) if pointer.exists() else None
        atomic_json(journal,{'state':'STAGING','path':str(target.relative_to(root)),'recovery_id':m['recovery_id'],'previous':previous,'at':now()})
        for index,ref in enumerate(m['databases']):
            src=sqlite3.connect('file:'+str(within(root,ref['path']))+'?mode=ro',uri=True);dst=sqlite3.connect(target/DB_NAMES[ref['role']])
            try:
                src.backup(dst)
                dst.execute("INSERT OR REPLACE INTO kv VALUES('arms','false')")
                dst.execute("INSERT OR REPLACE INTO kv VALUES('approved_plans','null')")
                if ref['role']=='evaluation':
                    # No external anti-rollback witness is provisioned in M0. Never
                    # advertise a restored unused seal as unused, even with a valid
                    # internally older chain. Known consumed evidence still wins.
                    dst.execute("UPDATE seals SET status='EVALUATION_COMPROMISED' WHERE status!='CONSUMED'")
                    for seal,eid in known.items():dst.execute('INSERT OR REPLACE INTO seals VALUES(?,?,?)',(seal,'CONSUMED',eid))
                dst.commit()
            finally:src.close();dst.close()
            if fail_after==index:raise ContractError('SYNTHETIC_RESTORE_INTERRUPTION')
        # One pointer publishes all databases at once; never replace stores one by one.
        atomic_json(target/'complete.json',{'recovery_id':m['recovery_id'],'databases':{r:file_hash(target/n) for r,n in DB_NAMES.items()},'at':now()})
        result={'state':'COMMITTED_DISARMED','path':str(target.relative_to(root)),'recovery_id':m['recovery_id'],'consumption':'VERIFIED' if established else 'EVALUATION_COMPROMISED','restored_unconsumed_seals':'EVALUATION_COMPROMISED','side_effect_replay':False,'previous':previous,'at':now()}
        atomic_json(pointer,{'path':result['path'],'recovery_id':result['recovery_id']})
        atomic_json(journal,result);return result
    finally:
        for h in handles:w.CloseHandle(h)

def restore_admission(root):
    path=Path(root)/'state/restore-operation.json'
    if not path.exists():return True
    try:
        journal=json.loads(path.read_text())
        if journal['state']=='ABORTED':return not (Path(root)/'state/active-recovery.json').exists()
        pointer=json.loads((Path(root)/'state/active-recovery.json').read_text())
        complete=json.loads(within(root,pointer['path']).joinpath('complete.json').read_text())
        return journal['state']=='COMMITTED_DISARMED' and pointer['recovery_id']==journal['recovery_id']==complete['recovery_id'] and pointer['path']==journal['path']
    except (OSError,ValueError,KeyError):return False

def abort_incomplete_restore(lease):
    lease.verify()
    if lease.role!='recovery':raise ContractError('RECOVERY_OWNER_REQUIRED')
    root=lease.project.root_path;path=root/'state/restore-operation.json';journal=json.loads(path.read_text())
    if journal['state']!='STAGING':raise ContractError('RESTORE_NOT_STAGING')
    from .runtime import win32 as w
    handles=[]
    try:
        for role in DB_NAMES:
            h=w.CreateFile(str(root/'state/locks'/(role+'.lock')),0xC0000000,0,None,4,0,None)
            if h==w.INVALID:raise ContractError('RESTORE_WRITER_LIVE')
            handles.append(h)
            meta=root/'state/runtime'/(role+'.json')
            if meta.exists():verify_prior_exit(json.loads(meta.read_text()))
        atomic_json(root/'state/restore-history'/(new_id()+'.json'),{**journal,'state':'ABORTED','at':now()})
        pointer=root/'state/active-recovery.json'
        if journal['previous']:
            atomic_json(pointer,journal['previous']);prior=journal['previous']
            atomic_json(path,{'state':'COMMITTED_DISARMED','path':prior['path'],'recovery_id':prior['recovery_id'],'aborted':journal['path'],'at':now()})
        else:
            if pointer.exists():pointer.unlink()
            atomic_json(path,{'state':'ABORTED','path':journal['path'],'at':now()})
        return {'state':'ABORTED','preserved_path':journal['path']}
    finally:
        for h in handles:w.CloseHandle(h)
