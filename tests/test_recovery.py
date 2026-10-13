"""Recovery fixtures use real native owners in separate, bounded invocations."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import pytest

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')
ROOT=Path(__file__).parents[1]


def invoke(root,action,**arguments):
    expected_exit=arguments.pop('_expected_exit',0)
    # No inherited credentials; one native child owns each invocation.
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    packet=root/('invocation-'+str(uuid4())+'.json');packet.write_text(json.dumps({'action':action,**arguments}))
    result=subprocess.run([sys.executable,'-B',str(ROOT/'tests/helpers/recovery_fixture.py'),str(root),str(packet)],env=env,capture_output=True,text=True,timeout=40)
    assert not result.stderr,result.stderr
    assert result.returncode==expected_exit,result.stdout
    if not result.stdout:return {'status':'INTERRUPTED'}
    import compertum
    value=json.loads(result.stdout)
    assert value.pop('package_origin')==str(Path(compertum.__file__).resolve()),'Child imported a different package'
    return value


@pytest.fixture(scope='module')
def recovery_project(tmp_path_factory,request):
    module=importlib.import_module('compertum.recovery')
    configured=request.config.getoption('--m0-recovery-project')
    root=Path(configured) if configured else tmp_path_factory.mktemp('recovery-project')
    if not root.resolve().is_relative_to((ROOT/'.cache/test-runs').resolve()): raise RuntimeError('FIXTURE_ROOT_DENIED')
    root.mkdir(parents=True,exist_ok=True)
    if (root/'state/active-generation.json').exists() and invoke(root,'recovery_state')['status']=='EVALUATION_COMPROMISED': raise RuntimeError('FIXTURE_COMPROMISED_USE_FRESH_NAMESPACE')
    prepared=invoke(root,'prepare')
    return root,prepared


def test_barrier_contains_real_pending_acknowledged_and_artifact_closure(recovery_project):
    root,prepared=recovery_project
    m=importlib.import_module('compertum.recovery')
    result=m.validate_recovery_set(Path(prepared['before']),project_root=root)
    assert result['status']=='VERIFIED'
    manifest=result['manifest']
    assert len(manifest['snapshots'])==3 and len(manifest['writers'])==4
    assert prepared['pending_event'] in {row['event_id'] for row in manifest['messages']['pending']}
    assert prepared['ack_event'] in {row['event_id'] for row in manifest['messages']['deduplication']}
    assert all((root/row['path']).exists() for row in manifest['artifacts'])


def test_old_backup_restore_preserves_later_consumption_and_nonreplayable_messages(recovery_project):
    root,prepared=recovery_project
    result=invoke(root,'restore',manifest=prepared['before'],seal_id=prepared['seal_id'],evaluation_id=prepared['evaluation_id'],pending_event=prepared['pending_event'])
    assert result['status']=='RESTORED' and result['seal_state']=='CONSUMED'
    assert invoke(root,'attempt_consume',seal_id=prepared['seal_id'])['status']=='DENIED'
    assert result['safe_delivery_count']==1
    assert result['broker_pending']>=1 and result['admission']=='HALTED'
    assert Path(prepared['before']).exists()


def test_restore_with_uncertain_guard_never_reopens_unused_authority(recovery_project):
    root,prepared=recovery_project
    result=invoke(root,'restore',manifest=prepared['before'],seal_id=prepared['seal_id'],evaluation_id=prepared['evaluation_id'],pending_event=prepared['pending_event'],uncertain_guard=True)
    assert result['seal_state']=='EVALUATION_COMPROMISED'
    assert invoke(root,'attempt_consume',seal_id=prepared['seal_id'])['status']=='DENIED' and result['admission']=='HALTED'
    repeated=invoke(root,'restore',manifest=prepared['before'],seal_id=prepared['seal_id'],evaluation_id=prepared['evaluation_id'],pending_event=prepared['pending_event'])
    assert repeated['seal_state']=='EVALUATION_COMPROMISED'


def test_corrupt_reference_prevents_restore_publication(recovery_project):
    root,prepared=recovery_project
    result=invoke(root,'corrupt_copy',manifest=prepared['before'])
    assert result['status']=='RECOVERY_INVALID'
    assert result['active_generation_unchanged'] is True


def test_interrupted_restore_blocks_writers_and_aborts_without_mixed_generation(recovery_project):
    root,prepared=recovery_project
    before=(root/'state/active-generation.json').read_bytes()
    invoke(root,'interrupt_restore',manifest=prepared['before'],_expected_exit=17)
    assert invoke(root,'probe_blocked')['status']=='RESTORE_RECOVERY_REQUIRED'
    assert invoke(root,'recover_interruption')['status']=='ABORTED'
    assert (root/'state/active-generation.json').read_bytes()==before
    phase=json.loads((root/'state/restore-operation.json').read_bytes())
    assert (root/'state/generations'/phase['generation']).exists()

def test_mixed_barrier_snapshots_are_rejected_even_when_each_hash_is_valid(recovery_project):
    root,prepared=recovery_project
    first=json.loads(Path(prepared['before']).read_bytes())
    second=json.loads(Path(prepared['after']).read_bytes())
    first['snapshots']=[next(s for s in second['snapshots'] if s['owner_role']=='evaluation') if s['owner_role']=='evaluation' else s for s in first['snapshots']]
    path=root/('mixed-'+str(uuid4())+'.json');path.write_text(json.dumps(first))
    assert importlib.import_module('compertum.recovery').validate_recovery_set(path,project_root=root)['status']=='RECOVERY_INVALID'

def test_self_consistent_old_guard_cannot_erase_preserved_later_consumption(recovery_project):
    root,prepared=recovery_project
    result=invoke(root,'old_guard_restore',manifest=prepared['before'],guard_before=prepared['guard_before'])
    assert result['seal_state']=='EVALUATION_COMPROMISED'
    assert invoke(root,'attempt_consume',seal_id=prepared['seal_id'])['status']=='DENIED'
    assert Path(prepared['after']).exists()


def test_ai_packet_and_original_response_are_in_restore_closure(recovery_project):
    root,prepared=recovery_project
    manifest=json.loads(Path(prepared['before']).read_bytes())
    declared={a['artifact_id']:a for a in manifest['artifacts']}
    for item in (prepared['ai_packet'],prepared['ai_response']):
        assert declared[item['artifact_id']]['sha256']==item['sha256']
        target=root/item['path'];retained=target.with_name(target.name+'.retained-'+str(uuid4()))
        target.rename(retained)
    result=invoke(root,'restore',manifest=prepared['before'],seal_id=prepared['seal_id'],evaluation_id=prepared['evaluation_id'],pending_event=prepared['pending_event'])
    assert result['status']=='RESTORED'
    import hashlib
    for item in (prepared['ai_packet'],prepared['ai_response']):
        assert hashlib.sha256((root/item['path']).read_bytes()).hexdigest()==item['sha256']


def test_compromise_marker_is_sticky_even_with_empty_intact_guard(tmp_path):
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.persistence import open_store
    from compertum.recovery import _preserved_consumption
    from compertum.consumption import verify_consumption_guard,consume_once
    from compertum.runtime.errors import RuntimeRefused
    project=resolve_project(tmp_path);lease=acquire_owner(project,'evaluation')
    try:
        store=open_store(lease,'evaluation')
        with store.conn: store.conn.execute('INSERT INTO state VALUES(?,?)',('evaluation_status',json.dumps('EVALUATION_COMPROMISED')))
        evidence=verify_consumption_guard(project);assert evidence['status']=='VERIFIED' and evidence['sequence']==0
        records,consistent=_preserved_consumption(project,evidence)
        assert records=={} and consistent is False
        with pytest.raises(RuntimeRefused,match='EVALUATION_COMPROMISED'):
            consume_once(lease,str(uuid4()),str(uuid4()),{k:'a'*64 for k in ('input_sha256','protocol_sha256','shortlist_sha256')})
    finally: release_owner(lease)


def test_recovery_child_uses_selected_package(tmp_path):
    assert invoke(tmp_path,'package_origin')['status']=='VERIFIED'
