"""Owner-held recovery barriers and append-preserved staged generations."""
from contextlib import ExitStack,contextmanager
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
from uuid import uuid4,uuid5,NAMESPACE_URL
from .consumption import verify_consumption_guard
from .domain import RecoveryManifest,ContractError
from .data.errors import DataError
from .events import canonical
from .persistence import checked_path,STORE_NAMES
from .runtime.errors import RuntimeRefused
from .runtime.identity import resolve_project
from .runtime.owners import _owner_scope,acquire_owner,release_owner,require_live_owner
from .storage import owner_of_grant,sample_storage,GIB


def utc(): return datetime.now(timezone.utc).isoformat()


def _hash(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def _read(path,maximum=1048576):
    with path.open('rb') as stream: raw=stream.read(maximum+1)
    if len(raw)>maximum: raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
    return json.loads(raw)


def _package_hash():
    digest=hashlib.sha256()
    for path in sorted(Path(__file__).parent.rglob('*.py')):
        digest.update(path.relative_to(Path(__file__).parent).as_posix().encode());digest.update(path.read_bytes())
    return digest.hexdigest()


@contextmanager
def _barrier_budget(manager,seconds):
    deadline=time.monotonic()+seconds;previous=manager.health_probe
    def check():
        if time.monotonic()>=deadline:raise RuntimeRefused('RECOVERY_BARRIER_TIMEOUT')
    def progress():
        check()
        if previous is not None:previous()
        check()
    manager.health_probe=progress
    try:
        check();yield check
    finally:manager.health_probe=previous


def _write(manager,parent,path,raw,*,before_publish=None):
    child=manager.split_grant(parent,max(len(raw),1))
    writer=manager.open_artifact(child,path)
    try:
        for offset in range(0,len(raw),8*1024**2): writer.write(raw[offset:offset+8*1024**2])
        return writer.publish(before_publish=before_publish)
    finally: writer.close()


def collect_recovery_set(project,owners,grant,*,recovery_lease,watchdog_lease,reserve,artifacts=()):
    require_live_owner(recovery_lease,'recovery')
    from .runtime.owner_channel import RemoteRoleEndpoint,_remote_scope
    from .runtime.owner_rpc import call_owner
    remote_watchdog=isinstance(watchdog_lease,RemoteRoleEndpoint)
    if remote_watchdog:
        watchdog_remote=watchdog_lease
        from .runtime.recovery_adapter import RemoteLease
        r=watchdog_remote.descriptor.registration
        if r.identity.role!='watchdog': raise RuntimeRefused('RECOVERY_OWNERS_REQUIRED')
        watchdog_lease=RemoteLease(r.project_id,r.generation,r.identity)
    else: require_live_owner(watchdog_lease,'watchdog')
    manager=owner_of_grant(grant);stores={store.role:store for store in owners}
    if (set(stores)!=set(STORE_NAMES) or len(owners)!=3 or grant.category!='backups'
            or any(s.lease.project_id!=project.project_id for s in owners)
            or recovery_lease.project_id!=project.project_id or watchdog_lease.project_id!=project.project_id
            or reserve.lease is not stores['execution'].lease): raise RuntimeRefused('RECOVERY_OWNERS_REQUIRED')
    barrier_id=str(uuid4());recovery_id=str(uuid4());base=f'backups/{grant.task_id}/{recovery_id}'
    started=utc()
    with ExitStack() as stack:
        stack.enter_context(_owner_scope(recovery_lease))
        check_deadline=stack.enter_context(_barrier_budget(manager,manager.config.resources['recovery_barrier_seconds']))
        if remote_watchdog:
            stack.enter_context(_remote_scope(watchdog_remote))
            ack=call_owner(watchdog_remote,'checkpoint',{'barrier_id':barrier_id})
            if ack!={'barrier_id':barrier_id,'generation':watchdog_lease.generation,'process_instance_id':watchdog_lease.identity.process_instance_id}:
                raise RuntimeRefused('RECOVERY_OWNER_MISMATCH')
        else: stack.enter_context(_owner_scope(watchdog_lease))
        for role in sorted(stores): stack.enter_context(stores[role]._live())
        from .final_audit_recovery import snapshot,closed
        closed(snapshot(stores['coordinator'].conn))
        observed=manager.observation();reserve_info=reserve.receipt()
        if reserve_info['capacity_bytes']!=GIB or reserve_info['unused_bytes']<256*1024**2 or reserve_info['allocated_bytes']<reserve_info['unused_bytes']:
            raise RuntimeRefused('RESERVE_UNVERIFIED')
        snapshots=[];checkpoints={};all_artifacts=[];pending=[];dedup=[]
        # Publish sharing receipts before the coordinator snapshot. Restoring
        # this first set must retain the authority to reuse its backup files.
        config_hash=hashlib.sha256(canonical(manager.config.to_payload())).hexdigest()
        lineage=_recovery_lineage(stores['coordinator'].conn,stores['evaluation'].conn,project,config_hash)
        from .recovery_lineage import verify_file_dependencies
        verify_file_dependencies(stores['coordinator'].conn,lineage,project.root_path)
        artifact_map={a['artifact_id']:a for a in artifacts}
        for item in lineage['artifacts']:
            if item['artifact_id'] in artifact_map and artifact_map[item['artifact_id']]!=item: raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID')
            artifact_map[item['artifact_id']]=item
        if len(artifact_map)>1024:raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
        from .backup_artifacts import shared_backup_artifacts
        all_artifacts.extend(stack.enter_context(shared_backup_artifacts(
            manager,grant,artifact_map.values(),check=check_deadline)))
        # One owner lock order serializes delivery and every database transaction
        # across this in-process barrier. Remote adapters must provide this same
        # acknowledged barrier; they are not inferred from three loose snapshots.
        for role,store in stores.items():
            from .runtime.recovery_adapter import RemoteStore
            maximum=16*1024**2 if isinstance(store,RemoteStore) else min(16*1024**2,store.conn.execute('PRAGMA page_count').fetchone()[0]*store.conn.execute('PRAGMA page_size').fetchone()[0]+65536)
            child=manager.split_grant(grant,maximum)
            checkpoint=manager.checkpoint(child,store,barrier_id,f'{base}/{role}.sqlite')
            checkpoints[role]=checkpoint
            snapshots.append({'owner_role':role,'path':checkpoint['path'].replace('\\','/'),'size_bytes':checkpoint['size_bytes'],
                              'sha256':checkpoint['sha256'],'schema_version':'1','checkpoint_id':checkpoint['checkpoint_id']})
            for message in checkpoint['pending']:
                raw=canonical(message);artifact=_write(manager,grant,f"{base}/messages/{message['event_id']}.json",raw)
                all_artifacts.append({key:artifact[key] for key in ('artifact_id','path','size_bytes','sha256')}|{'parent_artifact_ids':[]})
                seq=store.conn.execute('SELECT seq FROM events WHERE event_id=?',(message['event_id'],)).fetchone()[0]
                pending.append({'event_id':message['event_id'],'sender_role':role,'receiver_role':message['target_role'],
                                'payload_path':artifact['path'],'payload_sha256':artifact['sha256'],'sequence':seq})
            for row in checkpoint['deduplication']:
                dedup.append({'event_id':row['event_id'],'receiver_role':role,'payload_sha256':row['sha256'],'ack_sequence':row['sequence']})
        from .evaluation_seals import verify_seal_journal
        from .recovery_lineage import snapshot_seals,snapshot_consumption,seal_references
        guard=verify_consumption_guard(project);seals=verify_seal_journal(project)
        from .fake_attempt_guard import verify_attempt_guard
        from .fake_recovery import snapshot_attempts,matches_snapshot,matches_opening_snapshot
        from .fake_economic_opening import verify_opening
        attempts=verify_attempt_guard(project);opening=verify_opening(project);execution_snapshot=snapshot_attempts(stores['execution'].conn,project.project_id)
        if not matches_opening_snapshot(execution_snapshot,opening):raise RuntimeRefused('EXECUTION_COMPROMISED')
        if not matches_snapshot(execution_snapshot,attempts) or execution_snapshot['head']!={k:attempts.get(k) for k in ('sequence','sha256')}:raise RuntimeRefused('EXECUTION_COMPROMISED')
        if guard['status']!='VERIFIED' or seals['status']!='VERIFIED':raise RuntimeRefused('EVALUATION_COMPROMISED')
        if snapshot_seals(stores['evaluation'].conn,project.project_id)!=seals or snapshot_consumption(stores['evaluation'].conn)!=guard['consumed']:raise RuntimeRefused('RECOVERY_JOURNAL_BOUNDARY_MISMATCH')
        # Every persisted acknowledgement must have its receiver transition.
        for role,store in stores.items():
            for event_id,body in store.conn.execute('SELECT event_id,ack FROM outbox WHERE ack IS NOT NULL'):
                ack=json.loads(body);receiver=stores[ack['role']]
                row=receiver.conn.execute('SELECT sha256,seq FROM inbox WHERE event_id=?',(event_id,)).fetchone()
                if row!=(ack['sha256'],ack['sequence']): raise RuntimeRefused('RECOVERY_MESSAGE_MISMATCH')
        if _recovery_lineage(stores['coordinator'].conn,stores['evaluation'].conn,project,config_hash)!=lineage:
            raise RuntimeRefused('RECOVERY_LINEAGE_MISMATCH')
        verify_file_dependencies(stores['coordinator'].conn,lineage,project.root_path)
        remaining=manager.store.conn.execute('SELECT maximum-written FROM reservations WHERE id=?',(grant.grant_id,)).fetchone()[0]
        if len(all_artifacts)>1024 or 1024**2>remaining:raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
        check_deadline()
        completed=utc()
        manifest={'schema_version':'1','record_type':'RecoveryManifest','recovery_set_id':recovery_id,'project_id':project.project_id,
            'created_at':completed,'code_sha256':_package_hash(),
            'environment_sha256':hashlib.sha256(canonical(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions()))).hexdigest(),
            'config_sha256':hashlib.sha256(canonical(manager.config.to_payload())).hexdigest(),'complete':True,
            'barrier':{'barrier_id':barrier_id,'started_at':started,'completed_at':completed},
            'writers':[{'role':role,'process_instance_id':lease.identity.process_instance_id,'generation':lease.generation,'barrier_id':barrier_id}
                       for role,lease in [(r,s.lease) for r,s in stores.items()]+[('watchdog',watchdog_lease)]],
            'snapshots':snapshots,'messages':{'outbox_high_water_marks':[{'role':r,'sequence':p['event_high_water']} for r,p in checkpoints.items()],
                'inbox_high_water_marks':[{'role':r,'sequence':p['inbox_high_water']} for r,p in checkpoints.items()], 'pending':pending,'deduplication':dedup},
            'task_states':lineage['task_states'],'run_states':lineage['run_states'],'checkpoints':lineage['checkpoints'],'artifacts':all_artifacts,
            'seals':seal_references(seals,guard['consumed']),'seal_journal':{k:seals[k] for k in ('sequence','sha256')},'consumption_order':list(guard['consumed']),
            'consumption_guard':{'sequence':guard['sequence'],'sha256':guard['sha256'],'head_event_id':str(uuid5(NAMESPACE_URL,guard['sha256'])) if guard['sequence'] else None},
            'fake_attempt_guard':{k:attempts[k] for k in ('sequence','sha256')},
            'fake_economic_opening':execution_snapshot['opening'],
            'halt_state':{'admission':'DISARMED','reason':'M0 synthetic fixture'},
            'reserve_accounting':{'total_bytes':GIB,'unused_bytes':reserve_info['unused_bytes'],'allocated_verified':True}}
        manifest=RecoveryManifest(manifest,project_root=project.root_path).to_payload()
        # No publication until referenced bytes, message relationships and schema validate.
        _validate_manifest(manifest,project.root_path)
        if verify_consumption_guard(project)!=guard or verify_seal_journal(project)!=seals or verify_attempt_guard(project)!=attempts or verify_opening(project)!=opening:raise RuntimeRefused('RECOVERY_JOURNAL_BOUNDARY_MISMATCH')
        check_deadline()
        published=_write(manager,grant,f'{base}/manifest.json',canonical(manifest),before_publish=check_deadline)
        return {'status':'PUBLISHED','manifest_path':str(project.root_path/published['path']),'manifest':manifest}


def _validate_manifest(manifest,root):
    root=Path(root).resolve();manifest=RecoveryManifest(manifest,project_root=root).to_payload()
    project=resolve_project(root)
    if not manifest['complete'] or manifest['project_id']!=project.project_id: raise RuntimeRefused('RECOVERY_INVALID')
    for item in [*manifest['snapshots'],*manifest['artifacts']]:
        path=checked_path(root,root/item['path'])
        if path.stat().st_size!=item['size_bytes'] or _hash(path)!=item['sha256']: raise RuntimeRefused('RECOVERY_INVALID')
    lineage=_manifest_lineage(manifest,project)
    events={};inboxes={};acknowledgements={}
    for snapshot in manifest['snapshots']:
        role=snapshot['owner_role'];path=checked_path(root,root/snapshot['path']);conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try:
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise RuntimeRefused('RECOVERY_INVALID')
            identity=dict(conn.execute('SELECT key,value FROM metadata'))
            if identity!={'schema_version':'1','project_id':project.project_id,'role':role}: raise RuntimeRefused('RECOVERY_INVALID')
            if role=='coordinator':
                for key in ('task_states','run_states','checkpoints'):
                    if canonical(lineage[key])!=canonical(manifest[key]): raise RuntimeRefused('RECOVERY_LINEAGE_MISMATCH')
                declared={a['artifact_id']:a for a in manifest['artifacts']}
                for item in lineage['artifacts']:
                    match=declared.get(item['artifact_id'])
                    if match is None or any(match[k]!=item[k] for k in ('size_bytes','sha256','parent_artifact_ids')):
                        raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID')
            if role=='execution':
                from .fake_recovery import snapshot_attempts,validate_snapshot_boundary
                validate_snapshot_boundary(snapshot_attempts(conn,project.project_id),manifest)
            writer=next(w for w in manifest['writers'] if w['role']==role)
            stamp=conn.execute('SELECT barrier_id,generation,instance FROM db_checkpoints WHERE checkpoint_id=?',(snapshot['checkpoint_id'],)).fetchone()
            if stamp!=(manifest['barrier']['barrier_id'],writer['generation'],writer['process_instance_id']): raise RuntimeRefused('RECOVERY_INVALID')
            rows=conn.execute('SELECT seq,event_id,sha256,body FROM events ORDER BY seq LIMIT 1025').fetchall()
            inbox=conn.execute('SELECT seq,event_id,sha256,body FROM inbox ORDER BY seq LIMIT 1025').fetchall()
            if len(rows)>1024 or len(inbox)>1024: raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
            expected_event=next(r['sequence'] for r in manifest['messages']['outbox_high_water_marks'] if r['role']==role)
            expected_inbox=next(r['sequence'] for r in manifest['messages']['inbox_high_water_marks'] if r['role']==role)
            if max((r[0] for r in rows),default=0)!=expected_event or max((r[0] for r in inbox),default=0)!=expected_inbox:
                raise RuntimeRefused('RECOVERY_MESSAGE_MISMATCH')
            events[role]={r[1]:r for r in rows};inboxes[role]={r[1]:r for r in inbox}
            acknowledgements[role]=dict(conn.execute('SELECT event_id,ack FROM outbox'))
            if set(acknowledgements[role])!=set(events[role]): raise RuntimeRefused('RECOVERY_MESSAGE_MISMATCH')
            actual_pending={r[1]:(r[2],r[0],json.loads(r[3])['target_role']) for r in rows if acknowledgements[role][r[1]] is None}
            declared_pending={r['event_id']:(r['payload_sha256'],r['sequence'],r['receiver_role']) for r in manifest['messages']['pending'] if r['sender_role']==role}
            actual_inbox={r[1]:(r[2],r[0]) for r in inbox}
            declared_inbox={r['event_id']:(r['payload_sha256'],r['ack_sequence']) for r in manifest['messages']['deduplication'] if r['receiver_role']==role}
            if actual_pending!=declared_pending or actual_inbox!=declared_inbox: raise RuntimeRefused('RECOVERY_MESSAGE_MISMATCH')
        finally: conn.close()
    for role,rows in events.items():
        for event_id,row in rows.items():
            message=json.loads(row[3])
            if hashlib.sha256(canonical(message)).hexdigest()!=row[2] or message['source_role']!=role or message['project_id']!=project.project_id:
                raise RuntimeRefused('RECOVERY_MESSAGE_MISMATCH')
            ack=acknowledgements[role][event_id]
            if ack is not None:
                ack=json.loads(ack);actual=inboxes[message['target_role']].get(event_id)
                if actual is None or (actual[0],actual[2])!=(ack['sequence'],ack['sha256']): raise RuntimeRefused('RECOVERY_MESSAGE_MISMATCH')
    for role,rows in inboxes.items():
        for event_id,row in rows.items():
            message=json.loads(row[3]);original=events[message['source_role']].get(event_id)
            if original is None or original[2:]!=row[2:] or message['target_role']!=role: raise RuntimeRefused('RECOVERY_MESSAGE_MISMATCH')
    return manifest


def validate_recovery_set(manifest_path,*,project_root):
    try:
        root=Path(project_root).resolve();path=checked_path(root,manifest_path)
        manifest=_validate_manifest(_read(path),root)
        return {'status':'VERIFIED','manifest':manifest}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,StopIteration,sqlite3.Error,ContractError,DataError,RuntimeRefused):
        return {'status':'RECOVERY_INVALID'}


def restore_recovery_set(manifest_path,current_guard,destination,*,project):
    validation=validate_recovery_set(manifest_path,project_root=project.root_path)
    if validation['status']!='VERIFIED': raise RuntimeRefused('RECOVERY_INVALID')
    manifest=validation['manifest'];destination=checked_path(project.root_path,destination)
    if destination.parent!=project.root_path/'state/generations' or destination.exists(): raise RuntimeRefused('RESTORE_DESTINATION_DENIED')
    leases={};connections={};operation_id=str(uuid4());phase_path=project.root_path/'state/restore-operation.json'
    try:
        leases['recovery']=acquire_owner(project,'recovery')
        for role in (*STORE_NAMES,'watchdog'): leases[role]=acquire_owner(project,role)
        with _owner_scope(leases['recovery']) as guard:
            observed=sample_storage(project);required=sum(s['size_bytes'] for s in manifest['snapshots'])
            if observed['categories']['records']+required>5*GIB or observed['total_bytes']+required>50*GIB or observed['free_bytes']-required<50*GIB:
                raise RuntimeRefused('STORAGE_CAPACITY')
            pointer_path=project.root_path/'state/active-generation.json'
            prior_active=_read(pointer_path) if pointer_path.exists() else None
            staged_hashes={};guard_head=None;seal_head=None;attempt_head=None;opening_proof=None
            def phase(status):
                record={'operation_id':operation_id,'status':status,'generation':destination.name,'manifest_sha256':_hash(Path(manifest_path)),'prior_active':prior_active,'staged_sha256':staged_hashes,'guard_sha256':guard_head,'seal_sha256':seal_head,'fake_attempt_guard':attempt_head,'fake_economic_opening':opening_proof}
                history=project.root_path/'state'/f'restore-{operation_id}.jsonl'
                with history.open('ab') as stream: stream.write(canonical(record)+b'\n');stream.flush();os.fsync(stream.fileno())
                guard.api.publish_metadata(phase_path,canonical(record))
            actual=verify_consumption_guard(project)
            preserved,consistent=_preserved_consumption(project,actual)
            from .evaluation_seals import verify_seal_journal
            seals=verify_seal_journal(project);seal_consistent=_preserved_seals(project,seals)
            seal_head=seals.get('sha256')
            from .fake_attempt_guard import verify_attempt_guard
            from .fake_recovery import preserved_attempt_evidence,snapshot_attempts,matches_snapshot,matches_opening_snapshot
            from .fake_economic_opening import verify_opening
            opening_proof=verify_opening(project)
            attempts=verify_attempt_guard(project);execution_trusted=preserved_attempt_evidence(project,attempts)
            attempt_head={k:attempts.get(k) for k in ('sequence','sha256')}
            # Inspect the current generation while the restore owners hold every
            # writer lock, before PREPARING intentionally blocks ordinary opens.
            coordinator_snapshot=next(s for s in manifest['snapshots'] if s['owner_role']=='coordinator')
            prior=sqlite3.connect(checked_path(project.root_path,project.root_path/coordinator_snapshot['path']).as_uri()+'?mode=ro',uri=True)
            try:
                from .final_audit_recovery import require_preserved
                require_preserved(project,prior)
                final_consistent=_preserved_final_evidence(project,prior)
            finally:prior.close()
            phase('PREPARING');destination.mkdir(parents=True)
            guard_head=actual.get('sha256')
            trusted=(current_guard.get('status')=='VERIFIED' and actual['status']=='VERIFIED'
                     and current_guard.get('sequence')==actual['sequence'] and current_guard.get('sha256')==actual['sha256'] and consistent and seal_consistent)
            for snapshot in manifest['snapshots']:
                role=snapshot['owner_role'];target=destination/STORE_NAMES[role]
                with _owner_scope(leases[role]),(project.root_path/snapshot['path']).open('rb') as source,target.open('xb') as output:
                    remaining=snapshot['size_bytes']
                    while remaining:
                        chunk=source.read(min(8*1024**2,remaining))
                        if not chunk: raise RuntimeRefused('RECOVERY_INVALID')
                        output.write(chunk);remaining-=len(chunk)
                    output.flush();os.fsync(output.fileno())
                if _hash(target)!=snapshot['sha256']: raise RuntimeRefused('RECOVERY_INVALID')
                connections[role]=sqlite3.connect(target)
                connections[role].execute('PRAGMA synchronous=FULL')
                phase('STAGING_'+role.upper())
            _restore_fixture_artifacts(manifest,connections['coordinator'],project,evaluation=connections['evaluation'])
            evaluation=connections['evaluation']
            with _owner_scope(leases['evaluation']),evaluation:
                for record in preserved.values():
                    evaluation.execute('INSERT INTO consumption VALUES(?,?,?) ON CONFLICT(seal_id) DO UPDATE SET evaluation_id=excluded.evaluation_id,body=excluded.body',
                                           (record['seal_id'],record['evaluation_id'],canonical(record).decode()))
                from .recovery_lineage import reconcile_snapshot
                trusted=final_consistent and trusted
                trusted=reconcile_snapshot(connections['coordinator'],evaluation,project,seals,manifest['config_sha256']) and trusted
                evaluation.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('evaluation_status',json.dumps('VERIFIED' if trusted else 'EVALUATION_COMPROMISED')))
            execution=connections['execution']
            execution_snapshot=snapshot_attempts(execution,project.project_id)
            execution_trusted=matches_snapshot(execution_snapshot,attempts) and matches_opening_snapshot(execution_snapshot,opening_proof) and execution_trusted
            with _owner_scope(leases['execution']),execution:
                execution.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('execution_status',canonical('VERIFIED' if execution_trusted else 'EXECUTION_COMPROMISED').decode()))
                if not execution_trusted:execution.execute("INSERT INTO state VALUES('fake_attempt_conflict','true') ON CONFLICT(key) DO UPDATE SET value='true'")
                else:execution.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('fake_attempt_guard_head',canonical(attempt_head).decode()))
            # Rebuild safe delivery from stable IDs. Broker-side-effect rows remain pending.
            for role,conn in connections.items():
                for event_id,body,digest in conn.execute('SELECT event_id,body,sha256 FROM events JOIN outbox USING(event_id) WHERE ack IS NULL').fetchall():
                    message=json.loads(body)
                    if not message['replayable']: continue
                    receiver=connections[message['target_role']]
                    with _owner_scope(leases[message['target_role']]),receiver:
                        old=receiver.execute('SELECT seq,sha256 FROM inbox WHERE event_id=?',(event_id,)).fetchone()
                        if old:
                            if old[1]!=digest: raise RuntimeRefused('RECOVERY_MESSAGE_MISMATCH')
                            sequence=old[0]
                        else:
                            if message['kind'] in {'FIXTURE_TRANSITION','CONTROL'}:
                                from .persistence import validate_transition
                                payload=message['payload'];validate_transition(payload);receiver.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(payload['key'],canonical(payload['value']).decode()))
                            sequence=receiver.execute('INSERT INTO inbox(event_id,sha256,body) VALUES(?,?,?)',(event_id,digest,body)).lastrowid
                    ack={'event_id':event_id,'sha256':digest,'sequence':sequence,'role':message['target_role'],'project_id':project.project_id}
                    with _owner_scope(leases[role]),conn: conn.execute('UPDATE outbox SET ack=? WHERE event_id=?',(canonical(ack).decode(),event_id))
            for role,conn in connections.items():
                with _owner_scope(leases[role]),conn:
                    conn.execute("UPDATE attempts SET status='INTERRUPTED' WHERE status='RUNNING'")
                    for key,value in (('admission','HALTED'),('armed',False),('approved_plan',None),('research_state','PAUSED')):
                        conn.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,canonical(value).decode()))
                conn.close()
            connections.clear()
            for path in destination.iterdir():
                with path.open('r+b') as stream: stream.flush();os.fsync(stream.fileno())
            staged_hashes={name:_hash(destination/name) for name in STORE_NAMES.values()}
            if verify_consumption_guard(project)!=actual or verify_seal_journal(project)!=seals or verify_attempt_guard(project)!=attempts or verify_opening(project)!=opening_proof:raise RuntimeRefused('RESTORE_JOURNAL_CHANGED')
            phase('READY')
            guard.api.publish_metadata(project.root_path/'state/active-generation.json',canonical({'schema_version':1,'project_id':project.project_id,'generation':destination.name,'operation_id':operation_id}))
            phase('PUBLISHED')
            return {'status':'RESTORED','generation':destination.name,'seal_state':'CONSUMED' if trusted else 'EVALUATION_COMPROMISED','admission':'HALTED','execution_state':'VERIFIED' if execution_trusted else 'EXECUTION_COMPROMISED'}
    finally:
        for conn in connections.values(): conn.close()
        for lease in reversed(list(leases.values())): release_owner(lease)


def recover_interrupted_restore(project):
    """Complete a fully proved publication or conservatively retain the old set."""
    leases={}
    try:
        leases['recovery']=acquire_owner(project,'recovery')
        for role in (*STORE_NAMES,'watchdog'): leases[role]=acquire_owner(project,role)
        with _owner_scope(leases['recovery']) as guard:
            phase_path=project.root_path/'state/restore-operation.json'
            record=_read(phase_path,65536)
            if record['status'] in {'PUBLISHED','ABORTED'}: return {'status':record['status']}
            pointer_path=project.root_path/'state/active-generation.json'
            active=_read(pointer_path) if pointer_path.exists() else None
            status='ABORTED'
            if active and active.get('operation_id')==record['operation_id']:
                target=checked_path(project.root_path,project.root_path/'state/generations'/record['generation'])
                hashes=record.get('staged_sha256',{})
                evidence=verify_consumption_guard(project)
                from .evaluation_seals import verify_seal_journal
                seals=verify_seal_journal(project)
                from .fake_attempt_guard import verify_attempt_guard
                from .fake_recovery import preserved_attempt_evidence
                from .fake_economic_opening import verify_opening
                opening=verify_opening(project)
                attempts=verify_attempt_guard(project)
                complete=(record['status']=='READY' and set(hashes)==set(STORE_NAMES.values())
                          and all(_hash(target/name)==digest for name,digest in hashes.items())
                          and evidence.get('sha256')==record.get('guard_sha256')
                          and seals['status']=='VERIFIED' and seals['sha256']==record.get('seal_sha256')
                          and attempts['status']=='VERIFIED' and record.get('fake_attempt_guard')=={k:attempts[k] for k in ('sequence','sha256')}
                          and opening==record.get('fake_economic_opening')
                          and preserved_attempt_evidence(project,attempts))
                if complete:
                    from .final_audit_recovery import require_preserved
                    audit_db=sqlite3.connect((target/STORE_NAMES['coordinator']).as_uri()+'?mode=ro',uri=True)
                    try:
                        try:require_preserved(project,audit_db,prior_active=record.get('prior_active'))
                        except (RuntimeRefused,DataError,ValueError,TypeError,KeyError,sqlite3.Error):complete=False
                    finally:audit_db.close()
                if complete: status='PUBLISHED'
                elif 'prior_active' in record:
                    if record['prior_active'] is None:
                        pointer_path.rename(project.root_path/'state'/f"aborted-pointer-{record['operation_id']}.json")
                    else: guard.api.publish_metadata(pointer_path,canonical(record['prior_active']))
                else: raise RuntimeRefused('RESTORE_RECOVERY_UNVERIFIED')
            record['status']=status
            with (project.root_path/'state'/f"restore-{record['operation_id']}.jsonl").open('ab') as stream:
                stream.write(canonical(record)+b'\n');stream.flush();os.fsync(stream.fileno())
            guard.api.publish_metadata(phase_path,canonical(record))
            return {'status':status,'generation':record['generation']}
    finally:
        for lease in reversed(list(leases.values())): release_owner(lease)


def _fixture_lineage(conn,config_hash):
    result={'task_states':[],'run_states':[],'checkpoints':[],'artifacts':[]}
    table=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fixture_tasks'").fetchone()
    attempts=conn.execute('SELECT run_id,task_id,attempt,status,lineage FROM attempts LIMIT 1025').fetchall()
    if len(attempts)>1024: raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
    if not table:
        if attempts: raise RuntimeRefused('RECOVERY_LIFECYCLE_UNSUPPORTED')
        return _ai_lineage(conn,result)
    rows=conn.execute('SELECT task_id,run_id,spec,status,attempt,checkpoint,artifact FROM fixture_tasks ORDER BY task_id LIMIT 129').fetchall()
    if len(rows)>128: raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
    tasks={r[0]:r for r in rows};checkpoints={};artifacts={}
    def reference(item,task_id,run_id):
        if not item['path'].startswith(f'artifacts/runs/{task_id}/'): raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID')
        artifacts[item['artifact_id']]={key:item[key] for key in ('artifact_id','path','size_bytes','sha256')}|{'parent_artifact_ids':[]}
        if 'checkpoint_id' in item:
            checkpoints[item['checkpoint_id']]={'checkpoint_id':item['checkpoint_id'],'task_id':task_id,'run_id':run_id,
                'code_sha256':item['code_sha256'],'config_sha256':config_hash,'input_hashes':item['input_hashes'],
                'last_completed_unit':f"bytes:{item['size_bytes']}",'rng_state_artifact_id':None,'artifact_ids':[item['artifact_id']]}
    for task_id,run_id,spec,state,attempt,checkpoint,artifact in rows:
        cp=json.loads(checkpoint) if checkpoint else None
        status='UNVERIFIED' if state=='INTERRUPTED' else state
        result['task_states'].append({'task_id':task_id,'state':status,'checkpoint_id':cp['checkpoint_id'] if cp else None})
        result['run_states'].append({'run_id':run_id,'task_id':task_id,'state':status,'checkpoint_id':cp['checkpoint_id'] if cp else None})
        if cp: reference(cp,task_id,run_id)
        if artifact: reference(json.loads(artifact),task_id,run_id)
    for run_id,task_id,attempt,status,lineage in attempts:
        if task_id not in tasks or tasks[task_id][1]!=run_id: raise RuntimeRefused('RECOVERY_LIFECYCLE_UNSUPPORTED')
        item=json.loads(lineage)
        if item.get('checkpoint'): reference(item['checkpoint'],task_id,run_id)
    result['checkpoints']=sorted(checkpoints.values(),key=lambda r:r['checkpoint_id'])
    result['artifacts']=sorted(artifacts.values(),key=lambda r:r['artifact_id'])
    return _ai_lineage(conn,result)




def _restore_fixture_artifacts(manifest,coordinator,project,*,evaluation):
    lineage=_recovery_lineage(coordinator,evaluation,project,manifest['config_sha256'])
    supplied={a['artifact_id']:a for a in manifest['artifacts']}
    missing=[]
    for original in lineage['artifacts']:
        target=checked_path(project.root_path,project.root_path/original['path'])
        if target.exists():
            if target.stat().st_size!=original['size_bytes'] or _hash(target)!=original['sha256']:
                raise RuntimeRefused('RESTORE_ARTIFACT_CONFLICT')
        else: missing.append((original,target,supplied[original['artifact_id']]))
    observed=sample_storage(project);required=sum(max(4096,item[0]['size_bytes']) for item in missing)
    if observed['free_bytes']-required<50*GIB or observed['total_bytes']+required>50*GIB or observed['categories']['records']+required>5*GIB:
        raise RuntimeRefused('STORAGE_CAPACITY')
    for original,target,backup in missing:
        source=checked_path(project.root_path,project.root_path/backup['path'])
        target.parent.mkdir(parents=True,exist_ok=True)
        stage=target.with_name(target.name+'.restore-'+str(uuid4()))
        with source.open('rb') as incoming,stage.open('xb') as output:
            remaining=original['size_bytes']
            while remaining:
                chunk=incoming.read(min(8*1024**2,remaining))
                if not chunk: raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID')
                output.write(chunk);remaining-=len(chunk)
            output.flush();os.fsync(output.fileno())
        if _hash(stage)!=original['sha256']: raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID')
        stage.rename(target)


def _preserved_consumption(project,actual):
    """A self-consistent old guard is not proof that later evidence never existed."""
    from .persistence import _active_store_path
    from .consumption import _validate_record
    records=dict(actual.get('consumed',{}));consistent=actual['status']=='VERIFIED'
    def merge(path):
        nonlocal consistent
        conn=sqlite3.connect(checked_path(project.root_path,path).as_uri()+'?mode=ro',uri=True)
        try:
            if dict(conn.execute('SELECT key,value FROM metadata'))!={'schema_version':'1','project_id':project.project_id,'role':'evaluation'}:
                raise RuntimeRefused('RECOVERY_INVALID')
            status=conn.execute("SELECT value FROM state WHERE key='evaluation_status'").fetchone()
            if status and json.loads(status[0])=='EVALUATION_COMPROMISED': consistent=False
            rows=conn.execute('SELECT seal_id,evaluation_id,body FROM consumption LIMIT 1025').fetchall()
            if len(rows)>1024: raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
            for seal,evaluation,body in rows:
                record=json.loads(body);_validate_record(record)
                if (seal,evaluation)!=(record['seal_id'],record['evaluation_id']): raise RuntimeRefused('RECOVERY_INVALID')
                if actual.get('consumed',{}).get(seal)!=record: consistent=False
                if seal in records and records[seal]!=record: consistent=False
                else: records[seal]=record
        finally: conn.close()
    try:
        current=_active_store_path(project.root_path,project.project_id,'evaluation')
        if current.exists(): merge(current)
        count=0
        for path in (project.root_path/'backups').glob('*/*/manifest.json'):
            count+=1
            if count>128: raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
            # Consumption evidence survives historical checkpoint-schema changes.
            # This does not qualify the old set for a full restore.
            manifest=RecoveryManifest(_read(path),project_root=project.root_path).to_payload()
            if manifest['project_id']!=project.project_id: raise RuntimeRefused('RECOVERY_INVALID')
            head=manifest['consumption_guard']
            if actual.get('sequence') is None or head['sequence']>actual['sequence']: consistent=False
            snapshot=next(s for s in manifest['snapshots'] if s['owner_role']=='evaluation')
            source=checked_path(project.root_path,project.root_path/snapshot['path'])
            if source.stat().st_size!=snapshot['size_bytes'] or _hash(source)!=snapshot['sha256']:
                raise RuntimeRefused('RECOVERY_INVALID')
            merge(source)
    except (OSError,ValueError,KeyError,StopIteration,sqlite3.Error,ContractError,RuntimeRefused): consistent=False
    return records,consistent


def _ai_lineage(conn,result):
    """Include every retained AI output, including rejected responses and request records."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='ai_tasks'").fetchone(): return result
    rows=conn.execute('SELECT task_id,task,status,packet,response FROM ai_tasks ORDER BY task_id LIMIT 129').fetchall()
    if len(rows)>128: raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
    artifacts={a['artifact_id']:a for a in result['artifacts']}
    def reference(item,task_id):
        if not item['path'].startswith(f'artifacts/runs/{task_id}/'): raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID')
        value={key:item[key] for key in ('artifact_id','path','size_bytes','sha256')}|{'parent_artifact_ids':[]}
        if item['artifact_id'] in artifacts and artifacts[item['artifact_id']]!=value: raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID')
        artifacts[item['artifact_id']]=value
    for task_id,task,status,packet,response in rows:
        result['task_states'].append({'task_id':task_id,'state':'COMPLETED' if status=='PROPOSAL_ONLY' else 'WAITING_FOR_OPERATOR','checkpoint_id':None})
        reference(json.loads(packet),task_id)
        if response:
            receipt=json.loads(response);reference(receipt['original'],task_id);reference(receipt['receipt_artifact'],task_id)
    # Local requests can exist without a manual ai_tasks row.
    retained=conn.execute("SELECT task,manifest FROM reservations WHERE status='PUBLISHED' AND category='records' AND manifest IS NOT NULL ORDER BY id LIMIT 1025").fetchall()
    if len(retained)>1024: raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
    for task_id,raw in retained:
        item=json.loads(raw)
        if item['path'].startswith(f'artifacts/runs/{task_id}/ai/') or any(task_id==r[0] for r in rows): reference(item,task_id)
    result['task_states'].sort(key=lambda r:r['task_id'])
    result['artifacts']=sorted(artifacts.values(),key=lambda r:r['artifact_id'])
    return result


def _recovery_lineage(coordinator,evaluation,project,config_hash):
    from .recovery_lineage import extend_lineage
    return extend_lineage(coordinator,evaluation,project.project_id,config_hash,_fixture_lineage(coordinator,config_hash))


def _manifest_lineage(manifest,project):
    from .recovery_lineage import verify_boundary,seal_references
    with ExitStack() as stack:
        dbs={}
        for role in ('coordinator','evaluation'):
            snapshot=next(s for s in manifest['snapshots'] if s['owner_role']==role)
            path=checked_path(project.root_path,project.root_path/snapshot['path']);db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);stack.callback(db.close)
            if dict(db.execute('SELECT key,value FROM metadata'))!={'schema_version':'1','project_id':project.project_id,'role':role}:raise RuntimeRefused('RECOVERY_INVALID')
            dbs[role]=db
        seals,consumed=verify_boundary(dbs['evaluation'],project.project_id,manifest)
        if canonical(seal_references(seals,consumed))!=canonical(sorted(manifest['seals'],key=lambda s:s['seal_id'])):raise RuntimeRefused('RECOVERY_LINEAGE_MISMATCH')
        lineage=_recovery_lineage(dbs['coordinator'],dbs['evaluation'],project,manifest['config_sha256'])
        from .recovery_lineage import verify_file_dependencies
        verify_file_dependencies(dbs['coordinator'],lineage,project.root_path,{a['artifact_id']:a for a in manifest['artifacts']})
        return lineage


def _preserved_seals(project,actual):
    """A rolled-back journal cannot discard a newer current or archived mirror."""
    from .recovery_lineage import snapshot_seals,matches_prefix
    from .persistence import _active_store_path
    if actual['status']!='VERIFIED':return False
    def inspect(path):
        db=sqlite3.connect(checked_path(project.root_path,path).as_uri()+'?mode=ro',uri=True)
        try:
            if dict(db.execute('SELECT key,value FROM metadata'))!={'schema_version':'1','project_id':project.project_id,'role':'evaluation'}:return False
            return matches_prefix(snapshot_seals(db,project.project_id),actual)
        finally:db.close()
    try:
        current=_active_store_path(project.root_path,project.project_id,'evaluation')
        if current.exists() and not inspect(current):return False
        count=0
        for path in (project.root_path/'backups').glob('*/*/manifest.json'):
            count+=1
            if count>128:return False
            manifest=RecoveryManifest(_read(path),project_root=project.root_path).to_payload()
            if manifest['project_id']!=project.project_id:return False
            snapshot=next(s for s in manifest['snapshots'] if s['owner_role']=='evaluation');source=checked_path(project.root_path,project.root_path/snapshot['path'])
            if source.stat().st_size!=snapshot['size_bytes'] or _hash(source)!=snapshot['sha256'] or not inspect(source):return False
        return True
    except (OSError,ValueError,TypeError,KeyError,AttributeError,StopIteration,sqlite3.Error,ContractError,DataError,RuntimeRefused):return False


def _preserved_final_evidence(project,staged):
    """Preparations before START survive as evidence even when journal heads match."""
    from .recovery_lineage import final_evidence,final_evidence_prefix
    from .persistence import _active_store_path
    try:
        restored=final_evidence(staged)
        def inspect(path):
            db=sqlite3.connect(checked_path(project.root_path,path).as_uri()+'?mode=ro',uri=True)
            try:
                if dict(db.execute('SELECT key,value FROM metadata'))!={'schema_version':'1','project_id':project.project_id,'role':'coordinator'}:return False
                return final_evidence_prefix(final_evidence(db),restored)
            finally:db.close()
        current=_active_store_path(project.root_path,project.project_id,'coordinator')
        if current.exists() and not inspect(current):return False
        count=0
        for path in (project.root_path/'backups').glob('*/*/manifest.json'):
            count+=1
            if count>128:return False
            manifest=RecoveryManifest(_read(path),project_root=project.root_path).to_payload()
            if manifest['project_id']!=project.project_id:return False
            snapshot=next(s for s in manifest['snapshots'] if s['owner_role']=='coordinator');source=checked_path(project.root_path,project.root_path/snapshot['path'])
            if source.stat().st_size!=snapshot['size_bytes'] or _hash(source)!=snapshot['sha256'] or not inspect(source):return False
        return True
    except (OSError,ValueError,TypeError,KeyError,AttributeError,StopIteration,sqlite3.Error,ContractError,DataError,RuntimeRefused):return False
