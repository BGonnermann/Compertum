"""Small fixtures only. These tests do not grant storage admission."""
import importlib.util
import json
import io
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


e = load('evidence_folder')
c = load('prepare_evidence_candidates')
capture = load('evidence_capture')
sys.path.insert(0, str(ROOT/'tools'))
child = load('evidence_child')


@pytest.mark.parametrize('size,expected', [(0, 0), (1, 4096), (4096, 4096), (4097, 8192)])
def test_rounding(size, expected):
    assert e.charged(size) == expected


@pytest.mark.parametrize('actual', [0, 4096, e.LIMIT])
def test_census_counts_actual_plus_unused_once(actual):
    assert actual + e.unused_allowance(actual) == e.LIMIT


def test_census_refuses_overflow():
    with pytest.raises(RuntimeError):
        e.unused_allowance(e.LIMIT + 1)


def test_original_checks_stay_in_order(tmp_path):
    old = [tmp_path/str(n) for n in range(28)]
    result = e.add_folder_check(old, tmp_path)
    assert len(old) == 28 and result[:28] == old and len(result) == 29
    with pytest.raises(ValueError):
        e.add_folder_check(result, tmp_path)


def folder(path, limit=12288):
    return e.EvidenceFolder(path, {'test.log': 4096, 'test.closure.json': 4096}, lambda: None, limit=limit)


def test_overflow_preserves_prefix_and_closure(tmp_path):
    owner = folder(tmp_path)
    with owner.open('test.log') as stream:
        stream.write(b'a' * 4096)
        with pytest.raises(RuntimeError, match='EVIDENCE_FILE_LIMIT'):
            stream.write(b'b')
    owner.save('test.closure.json', {'status': 'FAILED'})
    assert (tmp_path/'test.log').read_bytes() == b'a' * 4096
    with pytest.raises(RuntimeError, match='EVIDENCE_OUTPUT_FAILED'):
        owner.finish()


def test_success_and_exclusive_outputs(tmp_path):
    owner = folder(tmp_path)
    owner.save('test.closure.json', {'status': 'PASSED'})
    owner.finish()
    with pytest.raises(ValueError):
        owner.open('test.closure.json')
    with pytest.raises(FileExistsError):
        folder(tmp_path)


def test_existing_files_consume_space_without_changes(tmp_path):
    path = tmp_path/'old.json'
    path.write_bytes(b'old')
    with pytest.raises(RuntimeError, match='RESERVATION_LIMIT'):
        folder(tmp_path)
    assert path.read_bytes() == b'old'


@pytest.mark.parametrize('name', ['../escape', 'C:escape', 'same/child'])
def test_binding_escape_is_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        e.EvidenceFolder(tmp_path, {name: 4096, 'x.closure.json': 4096}, lambda: None)


def test_external_modification_is_rejected(tmp_path):
    owner = folder(tmp_path)
    with owner.open('test.log') as stream:
        stream.write(b'a')
    (tmp_path/'test.log').write_bytes(b'changed')
    with pytest.raises(RuntimeError, match='CHANGED_EXTERNALLY'):
        owner.finish()


def test_deadline_failure_is_retained(tmp_path):
    owner = folder(tmp_path)
    stream = owner.open('test.log')
    def stop():
        raise TimeoutError('JOB_DEADLINE')
    owner.poll = stop
    with pytest.raises(TimeoutError):
        stream.write(b'a')
    assert owner.failed
    stream.close()


def test_parent_and_child_share_reservations(tmp_path):
    bindings = {'child.log': 4096, 'job.closure.json': 4096}
    parent = e.EvidenceFolder(tmp_path, bindings, lambda: None, writable={'job.closure.json'}, limit=12288)
    child = e.EvidenceFolder(tmp_path, bindings, lambda: None, writable={'child.log'}, limit=12288)
    child.save('child.log', {'complete': True})
    parent.check()
    parent.save('job.closure.json', {'status': 'PASSED'})
    child.finish()
    parent.finish()


def test_removed_output_fails_final_check(tmp_path):
    owner = folder(tmp_path)
    owner.save('test.log', {})
    (tmp_path/'test.log').unlink()
    with pytest.raises(RuntimeError, match='OUTPUT_REMOVED'):
        owner.finish()


def test_timeout_can_save_reserved_failure_closure(tmp_path):
    owner = folder(tmp_path)
    def expired():
        raise TimeoutError('JOB_DEADLINE')
    owner.poll = expired
    owner.save_closure('test.closure.json', {'status': 'FAILED', 'reason': 'JOB_DEADLINE'})
    assert json.loads((tmp_path/'test.closure.json').read_text())['status'] == 'FAILED'
    with pytest.raises(TimeoutError):
        owner.check()


def test_output_forecasts_match_fixed_ledgers():
    proposal = json.loads((ROOT/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').read_text())
    assert sum(e.output_bindings(proposal, 'stage', 'future-stage').values()) == 384 * 1024
    assert sum(e.output_bindings(proposal, 'capacity', 'future-capacity').values()) == 256 * 1024


@pytest.mark.parametrize('count,failed', [(4096, False), (4097, True)])
def test_child_output_limit_terminates_without_overwriting(tmp_path, monkeypatch, count, failed):
    class Process:
        stdout = io.BytesIO(b'x' * count)
        stderr = io.BytesIO(b'')
        killed = False
        def kill(self):
            self.killed = True
        def poll(self):
            return 1 if self.killed else 0
    process = Process()
    monkeypatch.setattr(capture.subprocess, 'Popen', lambda *a, **k: process)
    owner = e.EvidenceFolder(tmp_path, {'stdout': 4096, 'stderr': 4096, 'job.closure.json': 4096}, lambda: None)
    child = capture.CapturedProcess([], owner.open('stdout'), owner.open('stderr'), lambda: None)
    if failed:
        with pytest.raises(RuntimeError, match='CHILD_EVIDENCE_OUTPUT_FAILED'):
            child.finish()
        assert process.killed
    else:
        child.finish()
    assert (tmp_path/'stdout').stat().st_size == 4096


def test_disabled_candidates_compile_without_running(tmp_path):
    destination = tmp_path/'candidate'
    c.build(ROOT, destination)
    for path in destination.glob('*.py'):
        source = path.read_text()
        assert c.GUARD in source.splitlines()[:2]
        with pytest.raises(RuntimeError, match='PREPARATION_ONLY'):
            exec(compile(source, str(path), 'exec'), {})
    wrapper = (destination/'run_jobs08_prepared.py').read_text()
    assert 'evidence.add_folder_check(usage_roots,ROOT)' in wrapper
    census = (destination/'capacity_census_clock05_prepared.py').read_text()
    assert "extra_prefixes['artifacts/m5/simulated-evidence-next-01']=8" in census
    mapping=json.loads((destination/'output-bindings.json').read_text())
    assert len(mapping['stages']) == len(mapping['receipts']) == 10
    assert len({v['output_label'] for v in mapping['stages'].values()}) == 10
    assert all(v['output_label']+'-receipt.json' == mapping['receipts'][key+'-receipt.json']
               for key,v in mapping['stages'].items())
    admission=(destination/'run_admitted_stage_prepared.py').read_text()
    assert "0 <= time.time() - capacity.stat().st_mtime <= 180" in admission
    assert "closed['remaining_children'] == 0" in admission


def test_prepared_stage_collection_names_match_pytest(tmp_path):
    fixture=tmp_path/'test_harmless.py'
    fixture.write_text('def test_example():\n    pass\n')
    collected=[]
    class Inventory:
        def pytest_collection_modifyitems(self,items):
            collected.extend(item.nodeid for item in items)
    result=pytest.main(['--collect-only','-q','-p','no:cacheprovider','--rootdir',str(ROOT),str(fixture)],plugins=[Inventory()])
    assert result == 0
    assert collected == [fixture.relative_to(ROOT).as_posix()+'::test_example']


def child_fixture(tmp_path):
    original=tmp_path/'artifacts/m5/risk-dispatch-20261017-01'
    original.mkdir(parents=True)
    plan=original/'simclock02-source-history-plan.json'
    plan.write_text('{}')
    frozen={'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest()}
    label='simclock02-source-history'
    (original/'simulated-resumption01-bindings.json').write_text(json.dumps({'bindings':{label:frozen}}))
    mapping=tmp_path/'output-bindings.json'
    mapping.write_text(json.dumps({'stages':{label:{'original_binding':frozen,'output_label':'evidence01-source-history'}}}))
    (tmp_path/'docs').mkdir()
    (tmp_path/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').write_bytes((ROOT/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').read_bytes())
    (tmp_path/e.NAMESPACE).mkdir()
    return plan,mapping


def test_both_children_use_fixed_clock_binding(tmp_path):
    plan,mapping=child_fixture(tmp_path)
    assert child.clock_path(tmp_path,plan,mapping)==tmp_path/e.NAMESPACE/'evidence01-source-history-clock.json'
    for role in ('supervisor','execution'):
        original=(ROOT/f'tests/helpers/paper_fixture_rehearsal_{role}.py').read_text()
        candidate=c.child_candidate(original,role)
        assert 'clock_path==bound_clock_path(master,plan_path,' in candidate
        assert 'clock_for_plan(plan,' in candidate
        assert 'hashlib.sha256(clock_raw).hexdigest()' in candidate
        with pytest.raises(RuntimeError,match='PREPARATION_ONLY'):
            exec(compile(candidate,role,'exec'),{})


def test_child_failure_uses_reserved_file_and_preserves_prior(tmp_path):
    plan,mapping=child_fixture(tmp_path)
    child.save_child_failure(tmp_path,plan,mapping,'ValueError',[{'file':'fixture.py','line':1,'function':'run'}])
    path=tmp_path/e.NAMESPACE/'evidence01-source-history-cleanup.json'
    before=path.read_bytes()
    assert json.loads(before)['status']=='FAILED'
    assert len(before)<=16384
    with pytest.raises(FileExistsError):
        child.save_child_failure(tmp_path,plan,mapping,'OtherError',[])
    assert path.read_bytes()==before
    assert not list(plan.parent.glob('rehearsal-child-failure-*'))


def test_oversize_child_failure_records_explicit_limit_failure(tmp_path):
    plan,mapping=child_fixture(tmp_path)
    child.save_child_failure(tmp_path,plan,mapping,'Error',[{'file':'x'*20000}])
    raw=(tmp_path/e.NAMESPACE/'evidence01-source-history-cleanup.json').read_bytes()
    assert len(raw)<=16384
    value=json.loads(raw)
    assert value['error_type']=='CHILD_FAILURE_DETAIL_LIMIT' and value['frames_recorded'] is False


@pytest.mark.parametrize('change',['plan','mapping','frozen'])
def test_child_binding_refuses_changed_inputs(tmp_path,change):
    plan,mapping=child_fixture(tmp_path)
    if change=='plan':plan.write_text('{"changed":true}')
    elif change=='mapping':
        value=json.loads(mapping.read_text())
        value['stages']['simclock02-source-history']['output_label']='escape'
        mapping.write_text(json.dumps(value))
    else:
        path=plan.parent/'simulated-resumption01-bindings.json'
        path.write_text('{"bindings":{"simclock02-source-history":{"plan_sha256":"changed"}}}')
    with pytest.raises(ValueError):child.clock_path(tmp_path,plan,mapping)
