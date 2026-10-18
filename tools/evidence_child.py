"""Fixed child evidence paths. These helpers never grant execution admission."""
import hashlib
import json
from pathlib import Path
import time

from evidence_folder import EvidenceFolder, NAMESPACE, output_bindings


def binding(master, plan_path, mapping_path):
    master, plan_path = Path(master), Path(plan_path)
    original = master/'artifacts/m5/risk-dispatch-20261017-01'
    if plan_path.parent != original or not plan_path.name.endswith('-plan.json'):
        raise ValueError('CHILD_PLAN_PATH')
    label = plan_path.stem.removesuffix('-plan')
    mapping = json.loads(Path(mapping_path).read_text())['stages'][label]
    frozen = json.loads((original/'simulated-resumption01-bindings.json').read_text())['bindings'][label]
    if mapping['original_binding'] != frozen:
        raise ValueError('CHILD_BINDING_CHANGED')
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != frozen['plan_sha256']:
        raise ValueError('CHILD_PLAN_CHANGED')
    name = 'evidence01-' + label.removeprefix('simclock02-')
    if mapping['output_label'] != name:
        raise ValueError('CHILD_OUTPUT_CHANGED')
    proposal = json.loads((master/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').read_text())
    ledger = output_bindings(proposal, 'stage', name)
    ledger[name+'-clock.json'] = 4096
    return master/NAMESPACE, name, ledger


def clock_path(master, plan_path, mapping_path):
    folder, name, _ = binding(master, plan_path, mapping_path)
    return folder/(name+'-clock.json')


def save_child_failure(master, plan_path, mapping_path, kind, frames):
    """Use the reserved 16 KiB cleanup file for this execution child's failure."""
    deadline = time.monotonic() + 5
    def poll():
        if time.monotonic() >= deadline:
            raise TimeoutError('CHILD_FAILURE_RECORD_DEADLINE')
    poll()
    folder, name, ledger = binding(master, plan_path, mapping_path)
    target = name+'-cleanup.json'
    record = dict(status='FAILED', error_type=kind, values_recorded=False, frames=frames)
    raw = (json.dumps(record, allow_nan=False, indent=2)+'\n').encode('utf-8')
    if len(raw) > ledger[target]:
        record = dict(status='FAILED', error_type='CHILD_FAILURE_DETAIL_LIMIT',
                      values_recorded=False, frames_recorded=False, required_bytes=len(raw))
    owner = EvidenceFolder(folder, ledger, poll, writable={target})
    owner.save(target, record)
    owner.finish()
