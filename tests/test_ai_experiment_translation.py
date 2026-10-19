import hashlib
import json

import pytest

from compertum.ai.experiment import translate_proposal
from compertum.campaign_contract import VARIANTS
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused


def example():
    proposal = dict(schema_version='1', record_type='AIProposal',
        proposal_id='d924c484-61b4-4bb9-a109-8ad156e42d11',
        task_id='165be964-dab1-4794-90b3-6144071d9993', role='research_proposer',
        created_at='2026-10-18T12:00:00+00:00', prompt_sha256='a'*64,
        input_hashes=['b'*64], provider=dict(name='manual_subscription',
        model_label='synthetic', usage_status='UNKNOWN'), state='PROPOSAL_ONLY',
        summary='Compare the fixed variants.', assumptions=[], falsifier='No improvement.',
        citations=[], proposed_patch=None, fictional_tool_proposal=None)
    raw = canonical(proposal)
    selection = dict(schema_version='1', proposal_sha256=hashlib.sha256(raw).hexdigest(),
                     candidate_ids=['ridge-h05-a010'])
    expected = dict(task_id=proposal['task_id'], prompt_sha256='a'*64, input_hashes=['b'*64])
    return proposal, selection, expected


def run(proposal, selection, expected):
    return translate_proposal(canonical(proposal), canonical(selection), **expected)


@pytest.mark.parametrize('candidate', [v.candidate_id for v in VARIANTS])
def test_supported_variants_freeze_full_family(candidate):
    p, s, e = example(); s['candidate_ids'] = [candidate]
    raw = run(p, s, e); plan = json.loads(raw)
    assert raw == run(p, s, e)
    assert plan['authority'] == 'REVIEW_ONLY' and plan['executed'] is False
    assert plan['priority_candidate_ids'] == [candidate]
    assert len(plan['definition']['registered_family']) == 12
    assert plan['definition']['data']['real_protected_access'] is False
    digest = plan.pop('plan_sha256')
    assert hashlib.sha256(canonical(plan)).hexdigest() == digest


@pytest.mark.parametrize('change', ['unknown', 'duplicate', 'empty', 'override', 'wrong_hash',
                                  'task', 'prompt', 'inputs', 'patch', 'role'])
def test_unsafe_requests_are_refused(change):
    p, s, e = example()
    if change == 'unknown': s['candidate_ids'] = ['new-model']
    elif change == 'duplicate': s['candidate_ids'] *= 2
    elif change == 'empty': s['candidate_ids'] = []
    elif change == 'override': s['features'] = ['future_return']
    elif change == 'wrong_hash': s['proposal_sha256'] = 'f'*64
    elif change == 'task': e['task_id'] = 'd924c484-61b4-4bb9-a109-8ad156e42d11'
    elif change == 'prompt': e['prompt_sha256'] = 'c'*64
    elif change == 'inputs': e['input_hashes'] = ['c'*64]
    elif change == 'patch': p['proposed_patch'] = 'raise SystemExit()'
    elif change == 'role': p['role'] = 'mathematician'
    if change in ('patch', 'role'): s['proposal_sha256'] = hashlib.sha256(canonical(p)).hexdigest()
    with pytest.raises(RuntimeRefused): run(p, s, e)


@pytest.mark.parametrize('raw', [b'{}', b'{"x":1,"x":2}', b'NaN', b'[]', b'\xff', b'x'*131073], ids=['empty-object','duplicate-key','nonfinite','array','invalid-utf8','oversized'])
def test_malformed_selection_is_refused(raw):
    p, s, e = example()
    with pytest.raises(RuntimeRefused): translate_proposal(canonical(p), raw, **e)


def test_selection_order_is_normalized_and_input_is_unchanged():
    p, s, e = example(); s['candidate_ids'] = ['ridge-h21-a100', 'momentum-h01']
    original = canonical(s); a = json.loads(run(p, s, e))
    s['candidate_ids'].reverse(); b = json.loads(run(p, s, e))
    assert a['priority_candidate_ids'] == b['priority_candidate_ids']
    assert a['definition'] == b['definition']
    assert a['selection_sha256'] == hashlib.sha256(original).hexdigest()
