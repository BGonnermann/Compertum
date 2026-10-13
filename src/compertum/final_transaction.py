"""Owner-held synthetic final transaction. No protected reader is exposed here."""
import hashlib,json,sqlite3
from uuid import UUID,uuid5,uuid4
from .data.encoding import canonical
from .data.errors import DataError
from .final_recipe import recipe,recipe_hash,recipe_for_pin
from .evaluation_protocol import identifier,digest
from .runtime.errors import RuntimeRefused
from .runtime.owners import require_live_owner

# Two fixed whole-batch attempts and one interruption/terminal transition remain
# available after preparation. Unrelated events cannot spend this headroom.
FINAL_REMAINING_EVENTS=4


def generated_recipe():
    """Current default for newly sealed runs; replay resolves the sealed hash."""
    return recipe()


def recipe_sha256():return recipe_hash()


def _check(ok,code='FINAL_TRANSACTION_UNVERIFIED'):
    if not ok:raise RuntimeRefused(code)


def build_plan(project_id,seal_id,row,evaluation_id):
    identifier(evaluation_id);identifier(seal_id)
    freeze=row['freeze'];_check(freeze is not None,'SHORTLIST_NOT_FROZEN')
    protocol=row['creation']['protocol'];ticket=freeze['ticket']
    _check(ticket['pair']['source']['seal_id']==seal_id,'SHORTLIST_SOURCE_REQUIRED')
    try:pinned_recipe=recipe_for_pin(protocol['holdout_manifest_sha256'])
    except DataError:raise RuntimeRefused('FINAL_RECIPE_UNVERIFIED') from None
    inputs=dict(input_sha256=protocol['holdout_manifest_sha256'],
        protocol_sha256=row['creation']['protocol_sha256'],shortlist_sha256=ticket['shortlist_sha256'])
    return dict(schema='synthetic-final-plan-v1',project_id=project_id,seal_id=seal_id,
        evaluation_id=evaluation_id,checkpoint_id=str(uuid5(UUID(evaluation_id),'synthetic-final-initial-v1')),
        inputs=inputs,shortlist_ticket_sha256=freeze['ticket_sha256'],
        selected=ticket['comparison']['selection_projection']['selected'],
        recipe=pinned_recipe,runtime=protocol['runtime'],
        yearly_fits=protocol['definition']['fits'],
        budget=dict(attempts=2,wall_seconds=120,cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*1024**2),
        checkpoint=dict(schema='synthetic-final-checkpoint-v1',position='BEFORE_BATCH',price_reads=0),
        financial_accepted=False,full_M3=False)


def remaining_events(row):
    from .final_attempts import remaining_slots
    return remaining_slots(row)


def replay_prepare(project_id,seals,seal_id,record,sequence):
    row=seals[seal_id]
    _check(row['status']=='SEALED' and row.get('final') is None)
    plan=record['plan'];expected=build_plan(project_id,seal_id,row,plan['evaluation_id'])
    _check(canonical(plan)==canonical(expected) and record['plan_sha256']==hashlib.sha256(canonical(plan)).hexdigest())
    _check(not any(r.get('final') and r['final']['plan']['evaluation_id']==plan['evaluation_id'] for r in seals.values()),'FINAL_ID_REUSED')
    pair=row['freeze']['ticket']['pair']
    _check(all(seals[pair[lane]['seal_id']]['status']=='SEALED' for lane in ('source','wheel')))
    row.update(final=record,final_sequence=sequence,final_complete=None,final_complete_sequence=None)


def empty_result(plan):
    _check(plan['selected']==[],'FINAL_BATCH_REQUIRED')
    return dict(schema='synthetic-final-empty-result-v1',evaluation_id=plan['evaluation_id'],
        checkpoint_id=plan['checkpoint_id'],inputs=plan['inputs'],status='NO_CANDIDATE_QUALIFIES',
        selected=[],scoring_units=0,price_reads=0,financial_accepted=False,full_M3=False)


def replay_complete(seals,seal_id,record,sequence):
    row=seals[seal_id]
    _check(row['status']=='SEALED' and row.get('final') and row.get('final_complete') is None)
    expected=empty_result(row['final']['plan'])
    _check(canonical(record['result'])==canonical(expected))
    _check(record['result_sha256']==hashlib.sha256(canonical(expected)).hexdigest())
    row.update(final_complete=record,final_complete_sequence=sequence)


def _guard(seals):
    from .consumption import verify_consumption_guard
    state=verify_consumption_guard(seals.project)
    _check(state['status']=='VERIFIED','EVALUATION_COMPROMISED')
    return state


def _mirror_consumption(seals,plan,record):
    """An ignored INSERT or restored older mirror cannot grant batch permission."""
    _check(record is not None and record['evaluation_id']==plan['evaluation_id'] and record['inputs']==plan['inputs'],'FINAL_CONSUMPTION_UNVERIFIED')
    from .clean_registration import _text
    rows=seals.store.conn.execute('SELECT evaluation_id,'+_text('body',8192)+' FROM consumption WHERE seal_id=?',(plan['seal_id'],)).fetchall()
    _check(rows==[(plan['evaluation_id'],canonical(record).decode())],'FINAL_CONSUMPTION_UNVERIFIED')


def final_receipt(project_id,evidence,guard,seal_id):
    row=evidence['seals'].get(seal_id)
    _check(row is not None and row.get('final'),'FINAL_NOT_PREPARED')
    plan=row['final']['plan'];record=guard['consumed'].get(seal_id)
    _check(guard['status']=='VERIFIED' and record is not None and record['evaluation_id']==plan['evaluation_id'] and record['inputs']==plan['inputs'],'FINAL_CONSUMPTION_UNVERIFIED')
    terminal=row.get('final_complete');pair=row['freeze']['ticket']['pair']
    active=all(evidence['seals'][pair[lane]['seal_id']]['status']=='SEALED' for lane in ('source','wheel'))
    attempts=row.get('final_attempts',[])
    status=('NO_CANDIDATE_QUALIFIES' if terminal else 'CONSUMED_WAITING_FOR_BATCH')
    if attempts:status=terminal['outcome'] if terminal else 'BATCH_INTERRUPTED' if attempts[-1]['close'] else 'BATCH_RUNNING'
    receipt=dict(schema='synthetic-final-receipt-v1',project_id=project_id,seal_id=seal_id,
        evaluation_id=plan['evaluation_id'],checkpoint_id=plan['checkpoint_id'],
        plan_sha256=row['final']['plan_sha256'],preparation_sequence=row['final_sequence'],
        consumption_sha256=hashlib.sha256(canonical(record)).hexdigest(),
        status=status if active else 'INVALIDATED',
        result=terminal['result'] if terminal else None,result_sha256=terminal['result_sha256'] if terminal else None,
        completion_sequence=row.get('final_complete_sequence'),price_reads=None if attempts else 0,financial_accepted=False,full_M3=False)
    if attempts:
        closed=[a['close'] for a in attempts if a['close']]
        receipt.update(attempt_count=len(attempts),charged_ms=closed[-1]['charged_ms'] if closed else 0)
    return receipt


def reserve_final(manager,seal_id):
    """Reserve immutable journal files before calling the evaluation owner."""
    from .evaluation_seals import verify_seal_journal,MAX_EVENT_BYTES,MAX_EVENTS
    from .consumption import verify_consumption_guard
    require_live_owner(manager.lease,'coordinator')
    with manager.store._live() as scope:
        journal=verify_seal_journal(scope.project);guard=verify_consumption_guard(scope.project)
        _check(journal['status']=='VERIFIED' and guard['status']=='VERIFIED')
        row=journal['seals'].get(seal_id);_check(row is not None)
        # The terminal empty case still reserves the full fixed budget.
        if row.get('final') is None:
            start=journal['sequence']+1;stop=start+FINAL_REMAINING_EVENTS+1
        else:start=journal['sequence']+1;stop=start+remaining_events(row)
        _check(stop-1<=MAX_EVENTS,'SEAL_COUNT_BOUND')
        paths=[(f'state/evaluation-seals/{n:08}.json',MAX_EVENT_BYTES) for n in range(start,stop)]
        if seal_id not in guard['consumed']:
            from .consumption import MAX_EVENTS as MAX_CONSUMPTION_EVENTS
            _check(guard['sequence']<MAX_CONSUMPTION_EVENTS,'CONSUMPTION_BOUND_EXCEEDED')
            paths.append((f"state/evaluation-consumption/{guard['sequence']+1:08}.json",8192))
        for path,maximum in paths:
            old=manager.store.conn.execute("SELECT maximum,category,status FROM reservations WHERE path=?",(path,)).fetchall()
            if old:_check(old==[(maximum,'records','RUNTIME')],'SEAL_STORAGE_UNRESERVED');continue
            grant=manager.reserve_bytes(str(uuid4()),'records',maximum)
            with manager.store.conn:manager.store.conn.execute("UPDATE reservations SET status='RUNTIME',path=? WHERE id=?",(path,grant.grant_id))


def prepare_final(seals,seal_id,evaluation_id):
    from . import evaluation_seals as journal
    from .shortlist_freeze import owner_ticket
    from .consumption import consume_once
    identifier(seal_id);identifier(evaluation_id)
    with seals.store._live() as scope:
        require_live_owner(seals.store.lease,'evaluation')
        evidence=seals._evidence();seals._mirror(evidence);row=evidence['seals'].get(seal_id)
        _check(row is not None,'SEAL_NOT_FOUND')
        _check(row['creation']['protocol'].get('clean_pair',{}).get('lane')=='source','SHORTLIST_SOURCE_REQUIRED')
        _check(row['creation']['protocol']['runtime']==json.loads(canonical(journal.runtime_identity())),'SEAL_RUNTIME_CHANGED')
        _check(row['freeze'] is not None,'SHORTLIST_NOT_FROZEN')
        frozen=row['freeze'];ticket=owner_ticket(seals.project,seal_id,frozen['ticket_sha256'],evidence)
        journal._freeze_ticket(seals.project.project_id,evidence['seals'],seal_id,ticket,frozen['ticket_sha256'])
        plan=build_plan(seals.project.project_id,seal_id,row,evaluation_id)
        state=_guard(seals);prior=row.get('final')
        _check(ticket['pair']['wheel']['seal_id'] not in state['consumed'],'SEAL_ALREADY_CONSUMED')
        if prior:
            _check(canonical(prior['plan'])==canonical(plan),'FINAL_CONFLICT')
            if seal_id not in state['consumed']:
                journal._require_reservation(seals.project,f"state/evaluation-consumption/{state['sequence']+1:08}.json",8192)
        else:
            _check(seal_id not in state['consumed'],'FINAL_CHECKPOINT_MISSING')
            _check(not any(r.get('final') and r['final']['plan']['evaluation_id']==evaluation_id for r in evidence['seals'].values()),'FINAL_ID_REUSED')
            # Verify all future slots and the separate consumption write first.
            for n in range(evidence['sequence']+1,evidence['sequence']+FINAL_REMAINING_EVENTS+2):
                journal._require_reservation(seals.project,f'state/evaluation-seals/{n:08}.json',journal.MAX_EVENT_BYTES)
            journal._require_reservation(seals.project,f"state/evaluation-consumption/{state['sequence']+1:08}.json",8192)
            record=seals._record(seal_id,'PREPARE_FINAL');record.update(plan=plan,plan_sha256=hashlib.sha256(canonical(plan)).hexdigest())
            seals._append(evidence,record,scope)
        record=consume_once(seals.store.lease,seal_id,evaluation_id,plan['inputs'])
        state=_guard(seals);_check(state['consumed'].get(seal_id)==record,'FINAL_CONSUMPTION_UNVERIFIED')
        _mirror_consumption(seals,plan,record)
        evidence=seals._evidence();row=evidence['seals'][seal_id]
        if not plan['selected'] and row.get('final_complete') is None:
            result=empty_result(plan);record=seals._record(seal_id,'COMPLETE_EMPTY_FINAL')
            record.update(result=result,result_sha256=hashlib.sha256(canonical(result)).hexdigest())
            seals._append(evidence,record,scope);evidence=seals._evidence()
        return final_receipt(seals.project.project_id,evidence,state,seal_id)


def inspect_final(seals,seal_id):
    identifier(seal_id)
    with seals.store._live():
        require_live_owner(seals.store.lease,'evaluation')
        evidence=seals._evidence();seals._mirror(evidence);state=_guard(seals)
        result=final_receipt(seals.project.project_id,evidence,state,seal_id)
        _mirror_consumption(seals,evidence['seals'][seal_id]['final']['plan'],state['consumed'][seal_id])
        return result

