"""Prepare text for review. This module cannot create pipes or grant access.

Inputs are supplied observations, not proof of token identity or permission.
A future native adapter must independently observe and retain process tokens.
"""
from dataclasses import dataclass
import re

CLIENT_ACCESS = 0x00100083
EVIDENCE_NAME = 'pipe-isolated01'
EVIDENCE_FOLDER = 'artifacts/m5/simulated-evidence-next-01'
# Proposed suballocation of the existing 1 MiB preparation allowance.
# This ledger is not an active reservation or fresh capacity admission.
OUTPUT_LIMITS = (
    ('pipe-isolated01.plan.json', 8192),
    ('pipe-isolated01.result.json', 32768),
    ('pipe-isolated01.log', 16384),
    ('pipe-isolated01.progress.jsonl', 8192),
    ('pipe-isolated01.closure.json', 65536),
)


def _sid(value, prefix, count):
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError('IDENTITY_DENIED')
    parts = value[len(prefix):].split('-')
    if len(parts) != count or any(
        not re.fullmatch(r'0|[1-9][0-9]{0,9}', part) or int(part) > 0xffffffff
        for part in parts
    ):
        raise ValueError('IDENTITY_DENIED')


@dataclass(frozen=True)
class Observation:
    """Expected token fields. Construction does not query or trust Windows."""

    pid: int
    creation_time: int
    operator_sid: str
    logon_sid: str
    app_sid: str
    integrity_rid: int

    def validate(self):
        if type(self.pid) is not int or not 1 <= self.pid <= 0xffffffff:
            raise ValueError('PROCESS_ID_DENIED')
        if type(self.creation_time) is not int or not 1 <= self.creation_time < 2**64:
            raise ValueError('PROCESS_TIME_DENIED')
        # This isolated proposal supports the observed local user SID shape only.
        _sid(self.operator_sid, 'S-1-5-21-', 4)
        _sid(self.logon_sid, 'S-1-5-5-', 2)
        # Excludes capabilities and the broad All Application Packages SID.
        _sid(self.app_sid, 'S-1-15-2-', 7)
        if type(self.integrity_rid) is not int or self.integrity_rid != 4096:
            raise ValueError('INTEGRITY_CONTEXT_UNREVIEWED')


def candidate_descriptor(process, effective, expected, *, namespace, name_suffix,
                         requested_access=CLIENT_ACCESS):
    """Return a review candidate only. Never select a namespace automatically."""
    if any(type(item) is not Observation for item in (process, effective, expected)):
        raise ValueError('OBSERVATION_REQUIRED')
    for item in (process, effective, expected):
        item.validate()
    if process != effective or process != expected:
        raise ValueError('IDENTITY_CHANGED_OR_UNREVIEWED')
    if type(requested_access) is not int or requested_access != CLIENT_ACCESS:
        raise ValueError('ACCESS_MASK_DENIED')
    if namespace not in ('desktop', 'local'):
        raise ValueError('PIPE_NAMESPACE_UNRESOLVED')
    if not isinstance(name_suffix, str) or not re.fullmatch(r'[a-f0-9]{32}', name_suffix):
        raise ValueError('PIPE_NAME_DENIED')
    prefix = '\\\\.\\pipe\\' + ('LOCAL\\' if namespace == 'local' else '')
    descriptor = (
        f'D:P(A;;0x{CLIENT_ACCESS:08x};;;{process.operator_sid})'
        f'(A;;0x{CLIENT_ACCESS:08x};;;{process.logon_sid})'
        f'(A;;0x{CLIENT_ACCESS:08x};;;{process.app_sid})'
    )
    return {
        'status': 'PREPARED_NOT_AUTHORIZED',
        'native_execution_enabled': False,
        'identity_verified_by_windows': False,
        'namespace_verified_for_launcher': False,
        'pipe_name': prefix + 'compertum-isolated-' + name_suffix,
        'descriptor': descriptor,
        'requested_access': CLIENT_ACCESS,
        'retry_limit': 0,
        'permission_approval_required': True,
    }


def proposed_outputs():
    """Return a fresh ledger. The caller must establish capacity before use."""
    return dict(OUTPUT_LIMITS)


def main():
    raise RuntimeError('PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED')


if __name__ == '__main__':
    main()
