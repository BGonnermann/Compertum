"""Prepare the owner-authorized evidence move and bounded verification sources."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT/'artifacts/m5/local-economics-20261017-01'
NEW = ROOT/'artifacts/ai/review-plan-verification-20261018-01'
WORK = ROOT/'.cache/test-runs/m5-local-economics-20261017-01/ai-review-verification-preparation01'
FILES = ['ai-review-red01'+s for s in ('.py', '.job.json', '.xml', '-pins.json', '.closure.json')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('PREPARATION_SOURCE_CHANGED: '+old[:60])
    return source.replace(old, new)


def move_evidence():
    """Move five exact files on the same volume and retain their hashes."""
    from evidence_folder import regular_folder, charged
    regular_folder(OLD)
    regular_folder(NEW.parent.parent)
    if not NEW.parent.exists():
        NEW.parent.mkdir()
    regular_folder(NEW.parent)
    if NEW.exists():
        raise FileExistsError('PRESERVE_DESTINATION')
    rows = []
    for name in FILES:
        source = OLD/name
        if source.is_symlink() or source.stat().st_file_attributes & 0x400:
            raise ValueError('UNSAFE_SOURCE')
        rows.append(dict(name=name, size=source.stat().st_size, sha256=sha(source)))
    assert sum(charged(row['size']) for row in rows) == 28672
    NEW.mkdir()
    regular_folder(NEW)
    # Every absolute target stays under the named source or destination folder.
    for row in rows:
        source, target = OLD/row['name'], NEW/row['name']
        assert source.resolve().parent == OLD.resolve()
        assert target.resolve().parent == NEW.resolve() and not target.exists()
        assert sha(source) == row['sha256']
        source.rename(target)
        assert sha(target) == row['sha256'] and target.stat().st_size == row['size']
    record = dict(status='MOVED_HASHES_VERIFIED', source=str(OLD), destination=str(NEW),
                  files=rows, deleted_bytes=0, limits_changed=False)
    raw = (json.dumps(record, indent=2)+'\n').encode()
    assert len(raw) <= 4096
    for folder, name in ((NEW, 'relocation.json'), (OLD, 'ai-review-red01-relocated.json')):
        with (folder/name).open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return record


def prepare(capacity_label='ai-review-capacity01'):
    """Write fresh copies. This function launches no census or test."""
    if capacity_label not in ('ai-review-capacity01', 'ai-review-capacity02'):
        raise ValueError('CAPACITY_LABEL_DENIED')
    work = WORK if capacity_label == 'ai-review-capacity01' else WORK.with_name('ai-review-verification-preparation02')
    from evidence_folder import regular_folder
    regular_folder(work.parent)
    work.mkdir(exist_ok=False)
    regular_folder(work)
    original = OLD/'run_jobs08_storage01.py'
    assert sha(original) == '3f83f6eff1f2fcdb95b9fbc72f342e22a2942edcbb4d2081ff8dd3c9227a9aad'
    source = original.read_text()
    source = replace(source, 'EVIDENCE=ROOT/evidence.NAMESPACE',
        "AI=ROOT/'artifacts/ai/review-plan-verification-20261018-01'\nEVIDENCE=ROOT/evidence.NAMESPACE")
    source = replace(source, "bindings=evidence.output_bindings(proposal,kind,name)\nif kind=='stage':bindings[name+'-clock.json']=4096", """if kind=='capacity':
    if name!='ai-review-capacity01':raise RuntimeError('ONE_STORAGE_ATTEMPT_ONLY')
    bindings=evidence.output_bindings(proposal,kind,name)
else:
    if kind!='ai' or name not in ('ai-review-tests01','ai-review-tests02','ai-review-tests03','ai-review-map01'):
        raise RuntimeError('VERIFICATION_LABEL_DENIED')
    EVIDENCE=AI
    bindings={name+'.job.json':8192,name+'-source-pins.json':8192,
        name+'-results.xml':65536,name+'-stdout.log':32768,
        name+'-stderr.log':16384,name+'.closure.json':65536}""")
    source = replace(source, 'usage_roots=evidence.add_folder_check(usage_roots,ROOT)',
        'usage_roots=evidence.add_folder_check(usage_roots,ROOT)\nusage_roots.append(AI)\nassert len(usage_roots)==30')
    source = replace(source, '    evidence.unused_allowance(values[-1])',
        "    evidence.unused_allowance(values[-2])\n    if values[-1]>1048576:raise RuntimeError('AI_EVIDENCE_LIMIT')")
    source = replace(source,
        "    output=evidence.EvidenceFolder(EVIDENCE,bindings,monitor_poll,\n        writable={name+'-parent-progress.jsonl',name+'.closure.json'})\n    journal=evidence.EvidenceJournal(output,name+'-parent-progress.jsonl',monitor_poll)",
        """    parent_log=name+'-parent-progress.jsonl' if kind=='capacity' else name+'-stderr.log'
    output=evidence.EvidenceFolder(EVIDENCE,bindings,monitor_poll,
        limit=8388608 if kind=='capacity' else 1048576,
        writable={parent_log,name+'.closure.json'})
    journal=evidence.EvidenceJournal(output,parent_log,monitor_poll)
    if kind=='ai':
        gate=ROOT/evidence.NAMESPACE/'ai-review-capacity01-result.json'
        closed=ROOT/evidence.NAMESPACE/'ai-review-capacity01.closure.json'
        if (hashlib.sha256(gate.read_bytes()).hexdigest()!=plan['fresh_capacity_sha256']
                or hashlib.sha256(closed.read_bytes()).hexdigest()!=plan['fresh_closure_sha256']):
            raise RuntimeError('CAPACITY_IDENTITY_CHANGED')
        accepted=json.loads(gate.read_text());ended=json.loads(closed.read_text())
        if (accepted['status']!='CAPACITY_GATE_PASSED' or ended['status']!='PASSED'
                or ended['exit_code']!=0 or not ended['exit_observed'] or ended['remaining_children']!=0):
            raise RuntimeError('CAPACITY_NOT_ACCEPTED')""")
    source = replace(source, "plan=json.loads((EVIDENCE/(name+'.job.json')).read_text())",
        "plan=json.loads((EVIDENCE/(name+'.job.json')).read_text())\nif (plan['cpus'],plan['memory_mib'],plan['seconds']) != (1,128,120):raise RuntimeError('LIMITS_CHANGED')")
    source = replace(source,
        "    record.update(error=type(error).__name__,reason=str(error))",
        "    record.update(status='FAILED',error=type(error).__name__,reason=str(error))")
    if capacity_label != 'ai-review-capacity01':
        assert source.count('ai-review-capacity01') == 3
        source = source.replace('ai-review-capacity01', capacity_label)
        source = replace(source, "    guard.admit()", """    guard.admit()
    for relative, pin in plan['current_inputs'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==pin,relative""")
        source = replace(source,
            "    record['peak_memory_bytes']=api.limits(job).peak_job_memory",
            """    record['peak_memory_bytes']=api.limits(job).peak_job_memory
    for relative, pin in plan['current_inputs'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==pin,relative""")
    census = OLD/'capacity_census_clock05_storage01.py'
    assert sha(census) == 'b0603abac75982242e4b0e3eab01b70d6aa7698049622dc482183e34e662aafc'
    text = census.read_text()
    text = replace(text, "label=sys.argv[2];assert label.replace('-','').isalnum()",
        "label=sys.argv[2];assert label=='ai-review-capacity01'")
    text = replace(text, "extra_prefixes['artifacts/m5/simulated-evidence-next-01']=8",
        "extra_prefixes['artifacts/m5/simulated-evidence-next-01']=8\nextra_prefixes['artifacts/ai/review-plan-verification-20261018-01']=1")
    if capacity_label != 'ai-review-capacity01':
        assert text.count('ai-review-capacity01') == 1
        text = text.replace('ai-review-capacity01', capacity_label)
        text = replace(text,
            "    preserved={row['Path'].replace('\\\\','/'):Path(row['Preserved']) for row in read(OUT/'test-clock-original-helpers.json')}",
            """    preserved={row['Path'].replace('\\\\','/'):Path(row['Preserved']) for row in read(OUT/'test-clock-original-helpers.json')}
    # The earlier release and its manifests retain the original manual bridge.
    # Current review-plan sources have separate pins in this attempt's job.
    def verify_input(name, pin, path):
        if name != 'src/compertum/ai/manual.py':
            assert sha(path)==pin,name
            return
        import hashlib, zipfile
        assert sha(Path(current['source_archive']))==current['source_archive_sha256']
        with zipfile.ZipFile(current['source_archive']) as retained:
            info=retained.getinfo(name)
            assert info.file_size<=256*1024
            assert hashlib.sha256(retained.read(name)).hexdigest()==pin,name""")
        text = replace(text,
            "        assert sha(preserved.get(name,M/name))==pin,name",
            "        verify_input(name,pin,preserved.get(name,M/name))")
        text = replace(text,
            "    for name,pin in read(current_clock)['inputs'].items():assert sha(M/name)==pin,name",
            "    for name,pin in read(current_clock)['inputs'].items():verify_input(name,pin,M/name)")
    for name, value in [('run_bounded.py', source), ('capacity_census.py', text)]:
        compile(value, name, 'exec')
        with (work/name).open('x', encoding='utf-8') as stream: stream.write(value)
    plan = json.loads((ROOT/'artifacts/m5/simulated-evidence-next-01/storage-evidence-admission01.job.json').read_text())
    plan['args'] = [str(work/'capacity_census.py'), 'capacity', capacity_label]
    plan['resource_wrapper_sha256'] = sha(work/'run_bounded.py')
    plan['temp'] = str(work)
    if capacity_label != 'ai-review-capacity01':
        current_inputs = [
            'src/compertum/ai/manual.py', 'src/compertum/ai/experiment.py',
            'src/compertum/campaign_contract.py', 'src/compertum/evaluation_protocol.py',
            'tests/test_ai_review_plan_storage.py', 'tests/test_ai_manual.py',
            'tests/test_ai_experiment_translation.py', 'tests/test_ai_review_runner_preparation.py',
            'tests/helpers/ai_fixture.py', 'schemas/ai_proposal.v1.json',
            'tools/run_ai_review_tests.py', 'tools/prepare_ai_review_verification.py',
            'tools/evidence_folder.py', 'tools/fresh_namespace_usage.py',
            str((work/'capacity_census.py').relative_to(ROOT)).replace('\\', '/'),
        ]
        plan['current_inputs'] = {name:sha(ROOT/name) for name in current_inputs}
        assert len((json.dumps(plan, indent=2)+'\n').encode())<=4096
    with (ROOT/'artifacts/m5/simulated-evidence-next-01'/(capacity_label+'.job.json')).open('x') as stream:
        json.dump(plan, stream, indent=2)
    return dict(wrapper_sha256=sha(work/'run_bounded.py'), census_sha256=sha(work/'capacity_census.py'))


if __name__ == '__main__':
    raise RuntimeError('CALL_EXPLICIT_PREPARATION_FUNCTION_ONLY')
