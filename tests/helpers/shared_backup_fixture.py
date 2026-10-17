"""Two real recovery snapshots; reserve measurement is explicitly simulated."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parents[1]))
from test_recovery_snapshot_closure import prepared
from test_storage import manager
from compertum.persistence import open_store
from compertum.recovery import collect_recovery_set, validate_recovery_set
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner, release_owner


root = Path(sys.argv[1])
project = resolve_project(root)
leases = {role: acquire_owner(project, role) for role in
          ('coordinator', 'evaluation', 'execution', 'watchdog', 'recovery')}
try:
    owners = {role: leases[role] for role in ('coordinator', 'evaluation', 'execution')}
    extra = {role: leases[role] for role in ('watchdog', 'recovery')}
    action = sys.argv[2] if len(sys.argv) > 2 else 'prepare'
    if action == 'prepare':
        seals, _, item, first = prepared((project, owners), barrier_leases=extra)
        storage = seals.test_storage
    else:
        assert action == 'collect'
        item = json.loads(sys.argv[3])
        storage = manager((project, owners))
    reserve = SimpleNamespace(lease=leases['execution'], receipt=lambda: dict(
        capacity_bytes=1024**3, unused_bytes=1024**3, allocated_bytes=1024**3))
    second = collect_recovery_set(project,
        [open_store(leases[r], r) for r in ('coordinator', 'evaluation', 'execution')],
        storage.reserve_bytes(str(uuid4()), 'backups', 4 * 1024**2),
        recovery_lease=leases['recovery'], watchdog_lease=leases['watchdog'], reserve=reserve)
    for record in ((first, second) if action == 'prepare' else (second,)):
        assert validate_recovery_set(record['manifest_path'], project_root=root)['status'] == 'VERIFIED'
    selected = lambda record: next(a['path'] for a in record['manifest']['artifacts'] if a['artifact_id'] == item['artifact_id'])
    answer = dict(second_copy=selected(second),
        copy_count=len(list((project.root_path / 'backups').rglob(item['artifact_id'] + '-' + item['sha256'] + '.bin'))),
        reserve_measurement='SIMULATED_NOT_NATIVE_RESERVE_ACCEPTANCE')
    if action == 'prepare':
        original = project.root_path / item['path']
        retained = original.with_suffix('.retained')
        original.rename(retained)
        answer.update(artifact=item, first_copy=selected(first), first_manifest=first['manifest_path'],
            retained_original=str(retained),
            manifest_hashes={r['manifest_path']: hashlib.sha256(Path(r['manifest_path']).read_bytes()).hexdigest()
                             for r in (first, second)})
finally:
    for lease in reversed(list(leases.values())):
        release_owner(lease)
print(json.dumps(answer))
