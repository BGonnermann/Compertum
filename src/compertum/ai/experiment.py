"""Translate explicit proposal selections into review-only experiment settings.

This module does not read data, execute proposal text, or dispatch experiments.
The caller supplies trusted task bindings from the accepted proposal receipt.
"""
import hashlib

from compertum.ai.manual import MAX_PACKET, read_json, sanitized
from compertum.campaign_contract import VARIANTS
from compertum.domain import ContractError, validate_record
from compertum.evaluation_protocol import fixed_definition
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused


def translate_proposal(proposal_raw, selection_raw, *, task_id, prompt_sha256, input_hashes):
    """Return canonical immutable bytes; this is never execution authority.

    The separate selection names review priorities within the fixed family.
    It cannot remove other variants from later qualification requirements.
    Exact proposal bytes bind the selection, including its original formatting.
    """
    sanitized(proposal_raw)
    sanitized(selection_raw)
    try:
        proposal = validate_record('ai_proposal.v1', read_json(proposal_raw))
    except (ContractError, TypeError, ValueError, AttributeError):
        raise RuntimeRefused('AI_PROPOSAL_INVALID') from None
    if (proposal['task_id'] != task_id or proposal['prompt_sha256'] != prompt_sha256
            or proposal['input_hashes'] != input_hashes):
        raise RuntimeRefused('AI_RESPONSE_MISMATCH')
    if proposal['role'] not in ('research_proposer', 'ml_planner'):
        raise RuntimeRefused('AI_EXPERIMENT_ROLE_DENIED')
    if proposal['proposed_patch'] is not None or proposal['fictional_tool_proposal'] is not None:
        raise RuntimeRefused('AI_EXECUTABLE_PROPOSAL_DENIED')
    selection = read_json(selection_raw)
    digest = hashlib.sha256(proposal_raw).hexdigest()
    if (type(selection) is not dict
            or set(selection) != {'schema_version', 'proposal_sha256', 'candidate_ids'}
            or selection['schema_version'] != '1' or selection['proposal_sha256'] != digest):
        raise RuntimeRefused('AI_EXPERIMENT_SELECTION_DENIED')
    candidates = selection['candidate_ids']
    registered = [v.candidate_id for v in VARIANTS]
    if (type(candidates) is not list or not 1 <= len(candidates) <= len(registered)
            or any(type(value) is not str or value not in registered for value in candidates)
            or len(set(candidates)) != len(candidates)):
        raise RuntimeRefused('AI_EXPERIMENT_VARIANT_DENIED')
    definition = fixed_definition()
    if [v['candidate_id'] for v in definition['registered_family']] != registered:
        raise RuntimeRefused('AI_EXPERIMENT_CONTRACT_MISMATCH')
    plan = dict(schema_version='1', record_type='ExperimentReviewPlan', authority='REVIEW_ONLY',
        executed=False, financial_accepted=False, task_id=proposal['task_id'],
        proposal_id=proposal['proposal_id'], proposal_sha256=digest,
        selection_sha256=hashlib.sha256(selection_raw).hexdigest(),
        prompt_sha256=proposal['prompt_sha256'], input_hashes=proposal['input_hashes'],
        priority_candidate_ids=[name for name in registered if name in candidates],
        definition=definition, definition_sha256=hashlib.sha256(canonical(definition)).hexdigest(),
        next_action='REVIEW_BEFORE_REGISTRATION')
    plan['plan_sha256'] = hashlib.sha256(canonical(plan)).hexdigest()
    raw = canonical(plan)
    if len(raw) > MAX_PACKET:
        raise RuntimeRefused('AI_OUTPUT_BUDGET')
    return raw
