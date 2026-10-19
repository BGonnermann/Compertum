"""Explicit, immutable links to checked synthetic history. No dispatch authority."""
import json

from compertum.events import canonical, uuid
from compertum.runtime.errors import RuntimeRefused
from compertum.ai.manual import read_json
from compertum.ai.experiment import translate_proposal
from compertum.campaign_contract import UNITS
from compertum.evaluation_protocol import fixed_definition


def _published(bridge, task_id, name):
    path = f'artifacts/runs/{task_id}/ai/{name}'
    row = bridge.store.conn.execute(
        "SELECT manifest FROM reservations WHERE path=? AND status='PUBLISHED'", (path,)).fetchone()
    if row is None:
        raise RuntimeRefused('AI_HISTORY_EVIDENCE_MISSING')
    manifest = read_json(row[0])
    return bridge._read_published_ai(task_id, name, manifest), manifest


def _plan(bridge, task_id):
    uuid(task_id)
    row = bridge.store.conn.execute(
        'SELECT task,prompt_sha256,status,response FROM ai_tasks WHERE task_id=?', (task_id,)).fetchone()
    if not row or row[2] != 'PROPOSAL_ONLY' or not row[3]:
        raise RuntimeRefused('AI_PROPOSAL_NOT_ACCEPTED')
    task, receipt = read_json(row[0]), read_json(row[3])
    retained = dict(receipt)
    manifest = retained.pop('receipt_artifact')
    raw = bridge._read_published_ai(task_id, 'receipt.json', manifest)
    if (raw != canonical(retained) or receipt['task_id'] != task_id
            or receipt['status'] != 'PROPOSAL_ONLY' or receipt['executed'] is not False
            or task['task_id'] != task_id or task['kind'] != 'AI_PROPOSAL'
            or task['model_identity']['provider'] != 'manual_subscription'):
        raise RuntimeRefused('AI_EVIDENCE_MISMATCH')
    original = receipt['original']
    proposal_raw = bridge._read_published_ai(task_id, 'response-'+original['sha256']+'.json', original)
    proposal = read_json(proposal_raw)
    if proposal != receipt['proposal'] or proposal['role'] != task['role']:
        raise RuntimeRefused('AI_EVIDENCE_MISMATCH')
    selection, _ = _published(bridge, task_id, 'review-selection.json')
    plan_raw, artifact = _published(bridge, task_id, 'review-plan.json')
    expected = translate_proposal(proposal_raw, selection, task_id=task_id,
        prompt_sha256=row[1], input_hashes=task['input_hashes'])
    if plan_raw != expected:
        raise RuntimeRefused('AI_EVIDENCE_MISMATCH')
    return read_json(plan_raw), artifact


def _campaign(bridge, runs, run_id):
    from compertum.simulation.runs import SavedRuns
    from compertum.simulation.campaign_runs import history, verify
    from compertum.modeling.campaign import read_campaign
    from compertum.development_seals import check_campaign_history_seal
    if not isinstance(runs, SavedRuns) or runs.store is not bridge.store or runs.storage is not bridge.storage:
        raise RuntimeRefused('AI_HISTORY_OWNER_MISMATCH')
    state = runs._load(run_id)
    if state.get('input_kind') != 'synthetic-campaign':
        raise RuntimeRefused('AI_HISTORY_CAMPAIGN_REQUIRED')
    history(runs, run_id)
    check_campaign_history_seal(runs.store, state)
    if state['input_artifact'] is None:
        raise RuntimeRefused('AI_HISTORY_INPUT_MISSING')
    raw = runs._read(run_id, state['input_artifact'], 20*1024**2)
    # Historical inspection uses the recorded identity, never a fresh execution grant.
    bundle = read_campaign(raw, expected_sha256=state['request_sha256'], identity=state['identity'])
    verify(runs, state, raw, decode=False, historical=True)
    definition = fixed_definition()
    if (bundle['registered_family'] != definition['registered_family']
            or bundle['features'] != definition['features'] or bundle['universe'] != definition['universe']):
        raise RuntimeRefused('AI_HISTORY_DEFINITION_MISMATCH')
    # Require the original input and every accepted result to remain published.
    artifacts = [state['input_artifact']]
    artifacts += [v['artifact'] for v in state['outcomes'].values() if v['status'] == 'COMPLETED']
    for artifact in artifacts:
        row = runs.store.conn.execute(
            "SELECT manifest FROM reservations WHERE path=? AND status='PUBLISHED'", (artifact['path'],)).fetchone()
        if row is None or json.loads(row[0]) != artifact:
            raise RuntimeRefused('AI_HISTORY_ARTIFACT_UNPUBLISHED')
    return state, bundle


def _link(plan, artifact, state, bundle):
    return dict(schema_version='1', record_type='ReviewCampaignLink', authority='HISTORY_ONLY',
        execution_authorized=False, financial_accepted=False, task_id=plan['task_id'],
        proposal_id=plan['proposal_id'], proposal_sha256=plan['proposal_sha256'],
        review_plan=artifact, definition_sha256=plan['definition_sha256'],
        run_id=state['run_id'], request_sha256=state['request_sha256'],
        input_artifact=state['input_artifact'], trials=bundle['trials'])


def link_campaign(bridge, task_id, run_id, *, runs):
    """Associate one existing campaign. Identical repeats verify the same bytes."""
    uuid(run_id)
    with bridge.store._live():
        plan, artifact = _plan(bridge, task_id)
        state, bundle = _campaign(bridge, runs, run_id)
        value = _link(plan, artifact, state, bundle)
        return bridge._retain(task_id, 'campaign-link.json', canonical(value))


def read_history(bridge, task_id, *, runs):
    """Read checked evidence without registration, recovery, writes, or execution."""
    with bridge.store._live():
        plan, artifact = _plan(bridge, task_id)
        raw, link_artifact = _published(bridge, task_id, 'campaign-link.json')
        link = read_json(raw)
        if not isinstance(link, dict) or not isinstance(link.get('run_id'), str):
            raise RuntimeRefused('AI_EVIDENCE_MISMATCH')
        state, bundle = _campaign(bridge, runs, link['run_id'])
        if raw != canonical(_link(plan, artifact, state, bundle)):
            raise RuntimeRefused('AI_EVIDENCE_MISMATCH')
        trials = []
        for trial in bundle['trials']:
            units = []
            for index, unit in enumerate(UNITS):
                if unit.candidate_id != trial['candidate_id']:
                    continue
                outcome = state['outcomes'].get(unit.key)
                units.append(dict(unit=index, year=unit.year, phase=unit.phase,
                    status=outcome['status'] if outcome else 'PENDING'))
            resolved = sum(v['status'] != 'PENDING' for v in units)
            status = 'PENDING' if resolved == 0 else 'RESOLVED' if resolved == len(units) else 'PARTIAL'
            trials.append(dict(**trial, status=status, units=units))
        value = dict(schema_version='1', record_type='LinkedResearchHistory',
            authority='HISTORY_ONLY', execution_authorized=False, financial_accepted=False,
            proposal_id=plan['proposal_id'], task_id=task_id, review_plan=artifact,
            link=link_artifact, campaign=dict(run_id=state['run_id'], state=state['state'],
                request_sha256=state['request_sha256'], input_artifact=state['input_artifact'],
                recorded_identity=state['identity'], last_transition=state['last_transition']),
            trials=trials, attempts=state['attempts'], results=list(state['outcomes'].values()))
        if len(canonical(value)) > 512*1024:
            raise RuntimeRefused('AI_HISTORY_OUTPUT_BOUND')
        return value
