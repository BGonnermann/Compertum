"""Small preparation checks. These do not qualify Windows pipe transport."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pipe_diagnostic', ROOT / 'tools/diagnose_pipe_access.py')
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.mark.parametrize('value, expected', [(b'\0', False), (b'\1', True),
                                           (b'\0\0\0\0', False), (b'\1\0\0\0', True)])
def test_restriction_field_observed_and_documented_sizes(value, expected):
    assert diagnostic.restriction_value(value) == (expected, len(value))


@pytest.mark.parametrize('size', [0, 2, 3, 8])
def test_restriction_field_refuses_unknown_sizes(size):
    with pytest.raises(RuntimeError, match='TOKEN_RESTRICTION_SIZE_UNEXPECTED'):
        diagnostic.restriction_value(bytes(size))


def test_evidence_proposal_accounts_for_each_output_and_keeps_caps():
    proposal = json.loads((ROOT / 'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').read_text(encoding='utf-8'))
    assert proposal['status'] == 'PREPARED_NOT_ACTIVE'
    assert proposal['folder_limit_bytes'] == 8 * 1024**2
    assert proposal['category_limit_bytes'] == 5 * 1024**3
    assert proposal['total_limit_bytes'] == 50 * 1024**3
    assert proposal['forecast_total_bytes'] == sum(proposal['forecast_bytes'].values())
    assert proposal['forecast_total_bytes'] + proposal['unassigned_margin_bytes'] == proposal['folder_limit_bytes']
    for kind in ('capacity', 'stage'):
        ledger = proposal[f'per_{kind}_output_charged_bytes']
        assert all(charge > 0 and charge % 4096 == 0 for charge in ledger.values())
        assert 10 * sum(ledger.values()) == proposal['forecast_bytes'][f'ten_{kind}_outputs']
