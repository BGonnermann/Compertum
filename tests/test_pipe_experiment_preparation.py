"""Source-only checks. Never create a Windows pipe or change permissions."""
import ast
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import prepare_pipe_experiment as experiment
import prepare_pipe_launcher as launcher
from prepare_pipe_policy import Observation, proposed_outputs


def observed():
    return Observation(123, 456, 'S-1-5-21-1-2-3-1001', 'S-1-5-5-1-2',
                       'S-1-15-2-1-2-3-4-5-6-7', 4096)


def proposal():
    return json.loads((ROOT/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').read_text())


def inventory():
    return [dict(name='existing.json', bytes=80000, charged_bytes=81920, sha256='a'*64)]


def test_fixed_name_and_rights_match_reviewed_scope():
    from compertum.runtime._pipes import pipe_security
    value = observed()
    assert experiment.PIPE_NAME == r'\\.\pipe\compertum-policy-4c9002b9d6e14c048c7949ecc069eb74'
    assert experiment.descriptor(value) == pipe_security(value.operator_sid, value.logon_sid) + (
        '(A;;0x00100083;;;' + value.app_sid + ')')
    assert experiment.BOUNDS == dict(cpus=1, memory_mib=128, processes=16, seconds=120,
        start_memory_gib=16, stop_memory_gib=12, operation_seconds=5, cancellation_seconds=1, retry_limit=0)


def test_full_accounting_keeps_old_files_outside_all_forecasts():
    result = experiment.reconcile(proposal(), inventory(), experiment.PREPARATION)
    assert result['total_committed_bytes'] == 8343552
    assert result['remaining_bytes'] == 45056
    assert sum(result['preparation'].values()) == 1048576
    assert sum(result['outputs'].values()) == result['preparation']['pipe-isolated01'] == 131072
    assert not result['reservation_active'] and not result['global_admission']


@pytest.mark.parametrize('key', list(experiment.FORECAST))
def test_no_forecast_allowance_can_be_reduced(key):
    item = proposal()
    item['forecast_bytes'][key] -= 4096
    with pytest.raises(ValueError, match='FORECAST_CHANGED'):
        experiment.reconcile(item, inventory(), experiment.PREPARATION)


@pytest.mark.parametrize('change', ['unknown', 'smaller', 'larger'])
def test_preparation_assignments_must_be_exact(change):
    commitments = dict(experiment.PREPARATION)
    if change == 'unknown': commitments['other'] = 4096
    elif change == 'smaller': commitments['remaining_preparation'] -= 4096
    else: commitments['remaining_preparation'] += 4096
    with pytest.raises(ValueError, match='COMMITMENTS_CHANGED'):
        experiment.reconcile(proposal(), inventory(), commitments)


@pytest.mark.parametrize('field,value', [
    ('bytes', True), ('bytes', -1), ('bytes', 8388609), ('charged_bytes', 80000),
    ('charged_bytes', True), ('sha256', 'A'*64), ('sha256', 'a'*63),
    ('name', '../outside'), ('name', r'..\outside'), ('name', 'PIPE-ISOLATED01.RESULT.JSON'),
])
def test_invalid_inventory_cannot_reserve_space(field, value):
    rows = inventory()
    rows[0][field] = value
    with pytest.raises(ValueError):
        experiment.reconcile(proposal(), rows, experiment.PREPARATION)


def test_duplicate_inventory_refused():
    with pytest.raises(ValueError, match='COLLISION'):
        experiment.reconcile(proposal(), inventory()*2, experiment.PREPARATION)


def test_excess_existing_evidence_does_not_borrow_from_stage_holds():
    rows = inventory()
    rows[0].update(bytes=131072, charged_bytes=131072)
    with pytest.raises(ValueError, match='EXCEED_LIMIT'):
        experiment.reconcile(proposal(), rows, experiment.PREPARATION)


@pytest.mark.parametrize('field,value', [
    ('pid', 124), ('creation_time', 457), ('operator_sid', 'S-1-5-21-1-2-3-1002'),
    ('logon_sid', 'S-1-5-5-1-3'), ('app_sid', 'S-1-15-2-1-2-3-4-5-6-8'),
    ('integrity_rid', 8192),
])
def test_changed_effective_identity_refused(field, value):
    original = observed()
    with pytest.raises(ValueError):
        experiment.checked_observation(original, replace(original, **{field:value}),
                                       experiment.identity_fields(original), retained=original)


@pytest.mark.parametrize('field,value', [('pid', 124), ('creation_time', 457)])
def test_retained_process_cannot_be_replaced(field, value):
    original = observed()
    changed = replace(original, **{field:value})
    with pytest.raises(ValueError, match='RETAINED_PROCESS_CHANGED'):
        experiment.checked_observation(changed, changed, experiment.identity_fields(original), retained=original)


def test_new_process_ids_need_fresh_binding_not_historical_pid_reuse():
    original = observed()
    fresh = replace(original, pid=999, creation_time=10000)
    assert experiment.checked_observation(fresh, fresh, experiment.identity_fields(original), retained=fresh) == fresh
    experiment.check_pair(original, fresh, experiment.identity_fields(original))
    with pytest.raises(ValueError, match='TWO_DISTINCT'):
        experiment.check_pair(original, original, experiment.identity_fields(original))


@pytest.mark.parametrize('path', ['tools/pipe_experiment_native.py'])
def test_native_candidate_refuses_before_any_import_or_native_call(path):
    source = (ROOT/path).read_text()
    tree = ast.parse(source)
    assert isinstance(tree.body[1], ast.Raise)
    calls = []
    def denied_import(*args, **kwargs):
        calls.append(args)
        raise AssertionError('Native candidate reached an import.')
    with pytest.raises(RuntimeError, match='PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED'):
        exec(compile(source, path, 'exec'), {'__builtins__':{'RuntimeError':RuntimeError, '__import__':denied_import}})
    assert not calls


def test_launcher_preserves_original_checks_and_has_first_statement_guard():
    raw = (ROOT/'artifacts/m5/local-economics-20261017-01/run_evidence_maintenance01.py').read_bytes()
    candidate = launcher.prepare_launcher(raw)
    tree = ast.parse(candidate)
    assert isinstance(tree.body[0], ast.Raise)
    assert 'usage_roots.append(EVIDENCE)' in candidate
    assert 'assert len(usage_roots)==29' in candidate
    assert 'output.validate_activation()' in candidate
    assert 'output.save_closure(record)' in candidate
    assert 'api.assign(job,process);assigned=True' in candidate
    assert 'guard.admit()' in candidate and 'guard.poll()' in candidate
    assert "if plan.get('pythonpath')" in candidate
    with pytest.raises(RuntimeError, match='PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED'):
        exec(compile(candidate, '<disabled launcher>', 'exec'), {})
    with pytest.raises(ValueError, match='LAUNCHER_HASH_CHANGED'):
        launcher.prepare_launcher(raw+b'\n')


def test_all_prepared_python_sources_compile_without_execution():
    for name in ('prepare_pipe_experiment', 'prepare_pipe_launcher', 'pipe_experiment_identity',
                 'pipe_experiment_native', 'pipe_experiment_evidence'):
        ast.parse((ROOT/'tools'/(name+'.py')).read_text())


def test_native_source_contains_no_production_entrypoint_or_security_editor():
    source = (ROOT/'tools/pipe_experiment_native.py').read_text()
    for text in ('SetSecurityInfo', 'SetTokenInformation', 'Impersonate', 'AdjustTokenPrivileges',
                 'subprocess.Popen', 'Start-Service', 'strata.exe', 'llama-server'):
        assert text not in source
    assert 'verify_dacl(api, pipe, descriptor(current))' in source
    assert 'checked_observation(reader.process(child, info.pid)' in source
    assert "api.read_frame(pipe, time.monotonic() + 5)" in source


def test_preparation_entrypoint_has_no_native_override():
    with pytest.raises(RuntimeError, match='PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED'):
        experiment.main()


def test_source_ledger_and_proposal_have_exact_same_outputs():
    value = json.loads((ROOT/'docs/M5_PIPE_EXPERIMENT_OUTPUTS.json').read_text())
    assert value['outputs'] == proposed_outputs()
    assert value['native_execution_enabled'] is False
    assert sum(value['outputs'].values()) == 131072


@pytest.mark.parametrize('text,expected', [('EXPERIMENT_DEADLINE','EXPERIMENT_DEADLINE'),
    ('D:P(A;;GA;;;S-1-15-2-123)',None), ('a secret value',None), ('x'*200,None)])
def test_failure_fields_preserve_only_safe_refusal_codes(text, expected):
    result = experiment.failure_fields(RuntimeError(text))
    assert result.get('refusal_code') == expected
    assert result['error_type'] == 'RuntimeError'
    assert 'error' not in result


def test_failure_fields_keep_native_error_and_runtime_refusal_code():
    from compertum.runtime.errors import RuntimeRefused
    from compertum.runtime._windows import NativeCallError
    assert experiment.failure_fields(RuntimeRefused('PIPE_DEADLINE_EXCEEDED'))['refusal_code'] == 'PIPE_DEADLINE_EXCEEDED'
    result = experiment.failure_fields(NativeCallError('CreateFileW',5))
    assert (result['operation'],result['winerror']) == ('CreateFileW',5)


def launch_plan():
    import os
    activation = ROOT/'.cache/test-runs/m5-local-economics-20261017-01/pipe-isolated01-activation'
    plan = dict(python=str(ROOT/'.cache/clean-env-m0/Scripts/python.exe'),
        args=[str(activation/'pipe_experiment_native.py')],
        pythonpath=os.pathsep.join([str(ROOT/'tools'),str(ROOT/'src')]),
        temp=str(activation),cpus=1,memory_mib=128,seconds=120)
    for key in ('resource_wrapper_sha256','resource_profile_sha256','economic_profile_sha256',
        'native_profile_sha256','risk_profile_sha256','namespace_usage_sha256','approved_manifest_sha256',
        'fresh_capacity_result','fresh_capacity_closure','fresh_capacity_sha256','fresh_closure_sha256','capacity_files'):
        plan[key] = None
    return plan


@pytest.mark.parametrize('field,value', [('python','cmd.exe'), ('args',['unrelated.py']),
    ('pythonpath','elsewhere'), ('temp','C:/Windows/Temp'), ('cpus',True),('memory_mib',256),
    ('seconds',121), ('fixture','anything'), ('economic_fixture','anything'),
    ('reconciliation_fixture','anything'), ('attempt','new'),('affinity_choice','highest_available'),
    ('unreviewed',True)])
def test_launcher_rejects_command_and_fixture_overrides_before_reading_files(monkeypatch,field,value):
    import pipe_experiment_evidence as evidence
    plan = launch_plan()
    plan[field] = value
    reads=[]
    monkeypatch.setattr(evidence,'checked_bytes',lambda *args:reads.append(args))
    with pytest.raises(RuntimeError,match='EXPERIMENT_'):
        evidence.validate_launch(plan,ROOT,{})
    assert not reads


def test_activation_can_only_remove_the_explicit_guard(monkeypatch):
    import hashlib
    import pipe_experiment_evidence as evidence
    source = (ROOT/'tools/pipe_experiment_native.py').read_bytes()
    active = evidence.activation_source(source)
    assert b'PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED' not in active
    assert active.count(b'CreateNamedPipeW') == source.count(b'CreateNamedPipeW')
    with pytest.raises(RuntimeError,match='NATIVE_GUARD_CHANGED'):
        evidence.activation_source(active)
    plan = launch_plan()
    def read(path, limit):
        if path == ROOT/'tools/pipe_experiment_native.py': return source
        if path == Path(plan['args'][0]): return active
        if path == Path(plan['python']): return b'fixed interpreter'
        raise AssertionError(path)
    monkeypatch.setattr(evidence,'checked_bytes',read)
    evidence.validate_launch(plan,ROOT,{'python_sha256':hashlib.sha256(b'fixed interpreter').hexdigest()})
    with pytest.raises(RuntimeError,match='INTERPRETER_CHANGED'):
        evidence.validate_launch(plan,ROOT,{'python_sha256':'0'*64})


def test_simulated_deadline_saves_failure_without_repolling_expired_execution(monkeypatch):
    """Execute only the Python failure path with fake adapters and no Windows calls."""
    from types import SimpleNamespace
    source = ast.parse((ROOT/'tools/pipe_experiment_native.py').read_text())
    functions = [node for node in source.body if isinstance(node,ast.FunctionDef) and node.name == 'server']
    saved=[]
    class Handle:
        def __enter__(self): return self
        def __exit__(self,*args): pass
    class Output:
        def __init__(self,*args,**kwargs): pass
        def save_failure(self,name,record): saved.append((name,dict(record)))
    class Reader:
        def __init__(self,*args): pass
        def current(self,*args): raise RuntimeError('EXPERIMENT_DEADLINE')
    class Journal:
        def __init__(self,*args): self.stream=SimpleNamespace(close=lambda:None)
        def close(self): raise AssertionError('Expired poll must not run during cleanup.')
    scope=dict(inputs=lambda:({},{}),NativePipeAPI=lambda:SimpleNamespace(open_process=lambda pid:Handle()),
        JobAPI=lambda:None,IdentityReader=Reader,time=__import__('time'),EvidenceFolder=Output,
        proposed_outputs=proposed_outputs,FOLDER=Path('fake'),LABEL=experiment.LABEL,PIPE_NAME=experiment.PIPE_NAME,
        EvidenceJournal=Journal,os=SimpleNamespace(getpid=lambda:123),failure_fields=experiment.failure_fields)
    exec(compile(ast.Module(body=functions,type_ignores=[]),'<fake-only cleanup>','exec'),scope)
    assert scope['server']() == 1
    assert len(saved)==1 and saved[0][1]['refusal_code']=='EXPERIMENT_DEADLINE'


def test_fake_client_access_denied_saves_exact_windows_error_in_reserved_log():
    from compertum.runtime._windows import NativeCallError
    tree=ast.parse((ROOT/'tools/pipe_experiment_native.py').read_text())
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='client']
    saved=[]
    class Output:
        def __init__(self,*args,**kwargs):
            assert kwargs['writable']=={experiment.LABEL+'.log'}
        def save_failure(self,name,record): saved.append((name,dict(record)))
    def denied(*args): raise NativeCallError('CreateFileW',5)
    scope=dict(time=__import__('time'),EvidenceFolder=Output,FOLDER=Path('fake'),
        proposed_outputs=proposed_outputs,LABEL=experiment.LABEL,client_exchange=denied,
        failure_fields=experiment.failure_fields)
    exec(compile(ast.Module(body=functions,type_ignores=[]),'<fake-only client denial>','exec'),scope)
    assert scope['client'](123,456)==1
    assert len(saved)==1 and saved[0][0]=='pipe-isolated01.log'
    assert saved[0][1]['status']=='FAILED'
    assert (saved[0][1]['operation'],saved[0][1]['winerror'])==('CreateFileW',5)
