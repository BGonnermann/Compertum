"""Pure preparation checks. No Windows calls, process launch, or writes."""
from dataclasses import asdict
import hashlib
import json
import re

from prepare_pipe_policy import Observation, CLIENT_ACCESS, proposed_outputs

PIPE_NAME = r'\\.\pipe\compertum-policy-4c9002b9d6e14c048c7949ecc069eb74'
LABEL = 'pipe-isolated01'
IDENTITY_KEYS = ('operator_sid', 'logon_sid', 'app_sid', 'integrity_rid')
FORECAST = {
    'preparation_and_bindings': 1048576,
    'ten_stage_outputs': 3932160,
    'ten_capacity_outputs': 2621440,
    'independent_review': 524288,
    'final_closure': 131072,
    'directory_charge': 4096,
}
# Assign every byte of preparation. Unused assignments remain reserved.
PREPARATION = {
    'pipe-isolated01': 131072,
    'pipe-isolated01-capacity01': 262144,
    'remaining_preparation': 655360,
}
BOUNDS = dict(cpus=1, memory_mib=128, processes=16, seconds=120,
              start_memory_gib=16, stop_memory_gib=12,
              operation_seconds=5, cancellation_seconds=1, retry_limit=0)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def failure_fields(error):
    """Keep fixed refusal codes without recording arbitrary exception text."""
    result = {'error_type': type(error).__name__}
    code = getattr(error, 'code', str(error))
    if isinstance(code, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', code):
        result['refusal_code'] = code
    operation = getattr(error, 'operation', None)
    winerror = getattr(error, 'winerror', None)
    if (isinstance(operation, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}', operation)
            and type(winerror) is int and 0 <= winerror <= 0xffffffff):
        result.update(operation=operation, winerror=winerror)
    return result


def from_record(record):
    """Parse supplied evidence. This alone does not verify a Windows token."""
    if type(record) is not dict or record.get('is_appcontainer') is not True:
        raise ValueError('APPCONTAINER_REQUIRED')
    result = Observation(record['pid'], record['creation_time'], record['user_sid'],
                         record['logon_sid'], record['app_sid'], record['integrity_rid'])
    result.validate()
    return result


def identity_fields(value):
    if type(value) is not Observation:
        raise ValueError('OBSERVATION_REQUIRED')
    value.validate()
    return {key: getattr(value, key) for key in IDENTITY_KEYS}


def checked_observation(process, effective, expected_identity, *, retained=None):
    """Require fresh process/effective equality and the reviewed identity fields."""
    fields = identity_fields(process)
    identity_fields(effective)
    if process != effective or fields != expected_identity:
        raise ValueError('IDENTITY_CHANGED_OR_UNREVIEWED')
    if retained is not None:
        identity_fields(retained)
        if process != retained:
            raise ValueError('RETAINED_PROCESS_CHANGED')
    return process


def check_pair(server, client, expected_identity):
    checked_observation(server, server, expected_identity)
    checked_observation(client, client, expected_identity)
    if server.pid == client.pid:
        raise ValueError('TWO_DISTINCT_PROCESSES_REQUIRED')


def descriptor(observation):
    identity_fields(observation)
    return ('D:P' + ''.join(f'(A;;0x{CLIENT_ACCESS:08x};;;{sid})' for sid in
                           (observation.operator_sid, observation.logon_sid, observation.app_sid)))


def reconcile(proposal, existing, commitments):
    """Count old files conservatively outside every full planned allowance."""
    if (proposal.get('namespace') != 'artifacts/m5/simulated-evidence-next-01'
            or proposal.get('folder_limit_bytes') != 8388608
            or proposal.get('forecast_bytes') != FORECAST
            or proposal.get('forecast_total_bytes') != sum(FORECAST.values())
            or proposal.get('category_limit_bytes') != 5 * 1024**3
            or proposal.get('total_limit_bytes') != 50 * 1024**3):
        raise ValueError('FORECAST_CHANGED')
    if commitments != PREPARATION or sum(commitments.values()) != FORECAST['preparation_and_bindings']:
        raise ValueError('PREPARATION_COMMITMENTS_CHANGED')
    if type(existing) is not list or len(existing) > 64:
        raise ValueError('EVIDENCE_INVENTORY_DENIED')
    names = set()
    used = 0
    for item in existing:
        if set(item) != {'name', 'bytes', 'charged_bytes', 'sha256'}:
            raise ValueError('EVIDENCE_ENTRY_DENIED')
        name = item['name']
        if (not isinstance(name, str) or not name or '/' in name or '\\' in name
                or name.casefold() in names or name.casefold() in
                {key.casefold() for key in proposed_outputs()}):
            raise ValueError('EVIDENCE_NAME_COLLISION')
        names.add(name.casefold())
        size = item['bytes']
        if type(size) is not int or size < 0 or size > 8388608:
            raise ValueError('EVIDENCE_SIZE_DENIED')
        charge = max(4096, ((size + 4095) // 4096) * 4096)
        if type(item['charged_bytes']) is not int or item['charged_bytes'] != charge:
            raise ValueError('EVIDENCE_CHARGE_CHANGED')
        if (not isinstance(item['sha256'], str) or len(item['sha256']) != 64
                or any(ch not in '0123456789abcdef' for ch in item['sha256'])):
            raise ValueError('EVIDENCE_HASH_DENIED')
        used += charge
    total = sum(FORECAST.values()) + used
    if total > 8388608:
        raise ValueError('EVIDENCE_COMMITMENTS_EXCEED_LIMIT')
    return dict(existing_file_bytes=used, forecast_bytes=sum(FORECAST.values()),
                total_committed_bytes=total, remaining_bytes=8388608-total,
                preparation=dict(commitments), outputs=proposed_outputs(),
                reservation_active=False, global_admission=False)


def prepare(observed, proposal, commitments):
    """Bind the historical observation without treating old PIDs as live peers."""
    if (observed.get('status') != 'OBSERVED_NOT_AUTHORIZED'
            or observed.get('permissions_changed') is not False
            or type(observed.get('pipes_created')) is not int or observed['pipes_created'] != 0
            or observed.get('effective_matches_process') is not True
            or observed.get('parent_matches_process') is not True):
        raise ValueError('IDENTITY_EVIDENCE_INCOMPLETE')
    server, parent = from_record(observed['process']), from_record(observed['parent'])
    fields = identity_fields(server)
    effective_record = dict(observed['effective'], pid=server.pid, creation_time=server.creation_time)
    checked_observation(server, from_record(effective_record), fields)
    check_pair(server, parent, fields)
    accounting = reconcile(proposal, observed['folder']['files'], commitments)
    return dict(status='PREPARED_NOT_AUTHORIZED', native_execution_enabled=False,
                pipe_name=PIPE_NAME, client_access=CLIENT_ACCESS,
                application_sid_sha256=hashlib.sha256(server.app_sid.encode()).hexdigest(),
                identity_fields_sha256=digest(fields), observation_sha256=digest(observed),
                historical_peer_records_sha256=digest([asdict(server), asdict(parent)]),
                fresh_retained_peer_checks_required=True, bounds=dict(BOUNDS),
                evidence=accounting, namespace_verified=False,
                authority_required='One temporary pipe with the exact application grant.')


def main():
    raise RuntimeError('PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED')


if __name__ == '__main__':
    main()
