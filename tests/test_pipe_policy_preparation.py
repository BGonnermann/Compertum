"""Pure policy checks. No Windows pipes, token calls, or security changes."""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pipe_policy_preparation', ROOT/'tools/prepare_pipe_policy.py')
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)


def observed():
    return policy.Observation(123, 456, 'S-1-5-21-1-2-3-1001', 'S-1-5-5-1-2',
                              'S-1-15-2-1-2-3-4-5-6-7', 4096)


def prepare(**kwargs):
    value = observed()
    return policy.candidate_descriptor(value, value, value, namespace='desktop',
                                       name_suffix='a'*32, **kwargs)


def test_descriptor_retains_default_and_adds_only_exact_app_rights():
    from compertum.runtime._pipes import pipe_security, CLIENT_ACCESS
    value = observed()
    result = prepare()
    assert result['descriptor'] == pipe_security(value.operator_sid, value.logon_sid) + (
        f'(A;;0x{CLIENT_ACCESS:08x};;;{value.app_sid})')
    assert CLIENT_ACCESS == 0x00100083
    assert not CLIENT_ACCESS & (4 | 0x40000 | 0x80000 | 0x10000000 | 0x40000000)
    assert result['status'] == 'PREPARED_NOT_AUTHORIZED'
    assert result['permission_approval_required'] is True
    assert result['native_execution_enabled'] is False
    assert result['identity_verified_by_windows'] is False
    assert result['namespace_verified_for_launcher'] is False


@pytest.mark.parametrize('field,value', [
    ('pid', True), ('pid', 0), ('pid', 2**32), ('creation_time', 0),
    ('creation_time', True), ('creation_time', 2**64),
    ('operator_sid', 'S-1-1-0'), ('operator_sid', 'S-1-5-21-1-2-3-4294967296'),
    ('logon_sid', 'S-1-5-5-01-2'), ('logon_sid', 'S-1-5-18'),
    ('app_sid', 'S-1-15-2-1'), ('app_sid', 'S-1-15-3-1-2-3-4-5-6-7'),
    ('app_sid', 'S-1-15-2-1-2-3-4-5-6-7)(A;;GA;;;WD)'),
    ('integrity_rid', 8192), ('integrity_rid', True),
])
def test_invalid_or_unreviewed_observations_fail(field, value):
    item = replace(observed(), **{field:value})
    with pytest.raises(ValueError):
        policy.candidate_descriptor(item, item, item, namespace='desktop', name_suffix='a'*32)


@pytest.mark.parametrize('field,value', [
    ('pid', 124), ('creation_time', 457), ('operator_sid', 'S-1-5-21-1-2-3-1002'),
    ('logon_sid', 'S-1-5-5-1-3'), ('app_sid', 'S-1-15-2-1-2-3-4-5-6-8'),
])
@pytest.mark.parametrize('position', [1, 2])
def test_changed_effective_or_expected_identity_fails(field, value, position):
    values = [observed()]*3
    values[position] = replace(observed(), **{field:value})
    with pytest.raises(ValueError, match='IDENTITY_CHANGED'):
        policy.candidate_descriptor(*values, namespace='desktop', name_suffix='a'*32)


@pytest.mark.parametrize('mask', [True, 0, 0x00100087, 0x001f01ff, 0x40000000])
def test_other_access_masks_fail(mask):
    with pytest.raises(ValueError, match='ACCESS_MASK'):
        prepare(requested_access=mask)


@pytest.mark.parametrize('namespace', [None, '', 'automatic', 'LOCAL'])
def test_namespace_is_explicit(namespace):
    value = observed()
    with pytest.raises(ValueError, match='PIPE_NAMESPACE'):
        policy.candidate_descriptor(value, value, value, namespace=namespace, name_suffix='a'*32)


def test_local_candidate_is_not_qualification():
    value = observed()
    result = policy.candidate_descriptor(value, value, value, namespace='local', name_suffix='b'*32)
    assert result['pipe_name'] == '\\\\.\\pipe\\LOCAL\\compertum-isolated-' + 'b'*32
    assert not result['namespace_verified_for_launcher']


@pytest.mark.parametrize('suffix', ['..', 'a'*33, 'A'*32, 'a'*31+'\\'])
def test_unreviewable_pipe_names_fail(suffix):
    value = observed()
    with pytest.raises(ValueError, match='PIPE_NAME'):
        policy.candidate_descriptor(value, value, value, namespace='desktop', name_suffix=suffix)


def test_output_ledger_is_fixed_bounded_and_independent():
    first = policy.proposed_outputs()
    assert sum(first.values()) == 128*1024
    assert len(first) == 5
    assert all(n.startswith('pipe-isolated01.') and v % 4096 == 0 for n,v in first.items())
    assert first['pipe-isolated01.closure.json'] == 65536
    first.clear()
    assert len(policy.proposed_outputs()) == 5


def test_native_entrypoint_always_refuses():
    with pytest.raises(RuntimeError, match='PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED'):
        policy.main()
