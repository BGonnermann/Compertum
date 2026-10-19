"""Bind the proposed experiment to its fixed files. This does not grant authority."""
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from evidence_folder import EvidenceFolder, regular_folder
from prepare_pipe_experiment import LABEL, PREPARATION
from prepare_pipe_policy import proposed_outputs

NATIVE_GUARD = "raise RuntimeError('PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED')\n"
CAPACITY_LABEL = LABEL + '-capacity01'


def activation_source(raw):
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    if len(lines) < 2 or lines[1].rstrip('\r\n') != NATIVE_GUARD.rstrip('\n'):
        raise RuntimeError('NATIVE_GUARD_CHANGED')
    return ''.join(lines[:1]+lines[2:]).encode('utf-8')


def validate_launch(plan, root, manifest):
    root = Path(root)
    activation = root/'.cache/test-runs/m5-local-economics-20261017-01/pipe-isolated01-activation'
    expected = {
        'python': str(root/'.cache/clean-env-m0/Scripts/python.exe'),
        'args': [str(activation/'pipe_experiment_native.py')],
        'pythonpath': os.pathsep.join([str(root/'tools'), str(root/'src')]),
        'temp': str(activation), 'cpus': 1, 'memory_mib': 128, 'seconds': 120,
    }
    for key, value in expected.items():
        if type(plan.get(key)) is not type(value) or plan[key] != value:
            raise RuntimeError('EXPERIMENT_COMMAND_CHANGED')
    forbidden = {'affinity_choice', 'economic_fixture', 'fixture', 'reconciliation_fixture', 'attempt'}
    if forbidden & plan.keys():
        raise RuntimeError('EXPERIMENT_OVERRIDE_DENIED')
    allowed = set(expected) | {
        'resource_wrapper_sha256','resource_profile_sha256','economic_profile_sha256',
        'native_profile_sha256','risk_profile_sha256','namespace_usage_sha256',
        'approved_manifest_sha256','fresh_capacity_result','fresh_capacity_closure',
        'fresh_capacity_sha256','fresh_closure_sha256','capacity_files',
    }
    if set(plan) != allowed:
        raise RuntimeError('EXPERIMENT_PLAN_FIELDS_CHANGED')
    raw = checked_bytes(root/'tools/pipe_experiment_native.py', 1048576)
    if checked_bytes(activation/'pipe_experiment_native.py', 1048576) != activation_source(raw):
        raise RuntimeError('ACTIVATED_SOURCE_DIFFERS')
    if hashlib.sha256(checked_bytes(Path(expected['python']),1048576)).hexdigest() != manifest['python_sha256']:
        raise RuntimeError('EXPERIMENT_INTERPRETER_CHANGED')


def checked_bytes(path, limit):
    path = Path(path)
    regular_folder(path.parent)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400
            or info.st_size > limit):
        raise RuntimeError('INPUT_FILE_DENIED')
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise RuntimeError('INPUT_SIZE_DENIED')
    return value


class ExperimentEvidence:
    def __init__(self, root, plan_path, plan, poll):
        self.root, self.plan_path, self.plan = Path(root), Path(plan_path), plan
        self.manifest_path = self.root/'docs/M5_PIPE_EXPERIMENT_BINDINGS.json'
        self.manifest_raw = checked_bytes(self.manifest_path, 32768)
        self.manifest = json.loads(self.manifest_raw)
        self.plan_raw = checked_bytes(plan_path, 8192)
        if json.loads(self.plan_raw) != plan:
            raise RuntimeError('PLAN_CHANGED')
        self.folder = self.root/'artifacts/m5/simulated-evidence-next-01'
        if self.plan_path != self.folder/(LABEL+'.plan.json'):
            raise RuntimeError('PLAN_PATH_DENIED')
        proposal = json.loads(checked_bytes(self.root/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json',16384))
        capacity_limits = {name.replace('NAME',CAPACITY_LABEL):bound for name,bound in
                           proposal['per_capacity_output_charged_bytes'].items()}
        if sum(capacity_limits.values()) != PREPARATION[CAPACITY_LABEL]:
            raise RuntimeError('CAPACITY_ALLOCATION_CHANGED')
        capacity_files = self.plan['capacity_files']
        if type(capacity_files) is not dict or set(capacity_files) != set(capacity_limits):
            raise RuntimeError('CAPACITY_INVENTORY_REQUIRED')
        for name, record in capacity_files.items():
            if record is None:
                continue
            if set(record) != {'sha256','bytes'} or type(record['bytes']) is not int or not 0 <= record['bytes'] <= capacity_limits[name]:
                raise RuntimeError('CAPACITY_FILE_BOUND_CHANGED')
        required = {CAPACITY_LABEL+'-result.json', CAPACITY_LABEL+'-measurement.json', CAPACITY_LABEL+'.closure.json', CAPACITY_LABEL+'.job.json'}
        if any(capacity_files[name] is None for name in required):
            raise RuntimeError('CAPACITY_REQUIRED_FILE_MISSING')
        self.capacity_files = {name:record for name,record in capacity_files.items() if record is not None}
        self.output = EvidenceFolder(self.folder, {**proposed_outputs(),**capacity_limits}, poll,
                                     writable={LABEL+'.closure.json'})
        self.next_input_check = 0.0
        self.check_inputs()

    def check_inputs(self, *, throttled=False):
        if throttled and time.monotonic() < self.next_input_check:
            return
        if (checked_bytes(self.manifest_path, 32768) != self.manifest_raw
                or checked_bytes(self.plan_path, 8192) != self.plan_raw):
            raise RuntimeError('EXPERIMENT_INPUT_CHANGED')
        bindings = self.manifest['source_sha256']
        for name, expected in bindings.items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts:
                raise RuntimeError('SOURCE_PATH_DENIED')
            raw = checked_bytes(self.root/path, 1048576)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise RuntimeError('SOURCE_BINDING_CHANGED')
        original = {x['name']: x for x in self.manifest['existing_files']}
        original.update(self.capacity_files)
        names = set()
        with os.scandir(self.folder) as entries:
            for entry in entries:
                if len(names) >= 64:
                    raise RuntimeError('EVIDENCE_ENTRY_LIMIT')
                names.add(entry.name)
                if entry.name in proposed_outputs():
                    continue
                if entry.name not in original:
                    raise RuntimeError('UNASSIGNED_PREPARATION_FILE')
                raw = checked_bytes(Path(entry.path), 8388608)
                record = original[entry.name]
                if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
                    raise RuntimeError('PRIOR_EVIDENCE_CHANGED')
        if not original.keys() <= names:
            raise RuntimeError('PRIOR_EVIDENCE_MISSING')
        self.next_input_check = time.monotonic() + .5

    def validate_activation(self):
        """A future launcher must bind reviewed activation and fresh complete capacity."""
        if hashlib.sha256(self.manifest_raw).hexdigest() != self.plan['approved_manifest_sha256']:
            raise RuntimeError('APPROVED_MANIFEST_CHANGED')
        validate_launch(self.plan, self.root, self.manifest)
        # Receipt fields cannot supply user authority. The top-level code guard remains.
        capacity_path = self.root/self.plan['fresh_capacity_result']
        closure_path = self.root/self.plan['fresh_capacity_closure']
        if (capacity_path != self.folder/(CAPACITY_LABEL+'-result.json')
                or closure_path != self.folder/(CAPACITY_LABEL+'.closure.json')):
            raise RuntimeError('CAPACITY_PATH_DENIED')
        capacity_raw, closure_raw = checked_bytes(capacity_path, 8192), checked_bytes(closure_path, 65536)
        if (hashlib.sha256(capacity_raw).hexdigest() != self.plan['fresh_capacity_sha256']
                or hashlib.sha256(closure_raw).hexdigest() != self.plan['fresh_closure_sha256']):
            raise RuntimeError('CAPACITY_BINDING_CHANGED')
        capacity, closure = json.loads(capacity_raw), json.loads(closure_raw)
        if (capacity['status'] != 'CAPACITY_GATE_PASSED' or closure['status'] != 'PASSED'
                or closure['exit_observed'] is not True or closure['remaining_children'] != 0):
            raise RuntimeError('FRESH_CAPACITY_REQUIRED')
        # The actual capacity producer must provide its completion time. Do not invent it.
        completed = capacity.get('completed_unix')
        if type(completed) not in (int, float) or not 0 <= time.time()-completed < 35:
            raise RuntimeError('FRESH_CAPACITY_TIME_UNVERIFIED')

    def save_closure(self, record):
        self.output.save_closure(LABEL+'.closure.json', record)
