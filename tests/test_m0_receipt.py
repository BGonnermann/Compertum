from pathlib import Path
import json
from compertum.domain import file_hash

def test_packaged_contracts_match_canonical_sources():
    root=Path(__file__).resolve().parents[1]
    for schema in (root/'schemas').glob('*.json'):assert file_hash(schema)==file_hash(root/'src/compertum/resources'/schema.name)
    assert file_hash(root/'config/default.toml')==file_hash(root/'src/compertum/resources/default.toml')

def test_acceptance_cannot_hide_missing_gate():
    from tools.verify_m0 import acceptance_state
    assert acceptance_state({'native':'VERIFIED_PASS','storage':'UNVERIFIED'})=='M0_BLOCKED'
    assert acceptance_state({'native':'VERIFIED_PASS','storage':'VERIFIED_FAIL'})=='M0_BLOCKED'
    assert acceptance_state({'native':'VERIFIED_PASS','storage':'VERIFIED_PASS'})=='ENGINEERING_FOUNDATIONS_READY'
