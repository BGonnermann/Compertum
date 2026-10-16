"""Remove only the four owner-approved, verified historical fixture roots."""
if not __debug__:
    raise RuntimeError('OPTIMIZED_PYTHON_DENIED')
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import time
from contextlib import ExitStack

ROOT=Path(r'C:\Users\bgonn\Desktop\Compertum')
NAMESPACE=ROOT/'artifacts/m5/fixture-consolidation-execution-20261015-01'
spec=importlib.util.spec_from_file_location('fixture_archive_support',ROOT/'tools/fixture_archive.py')
archive=importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)
ROOTS=(
 '.cache/test-runs/m3-pair-validation-repair-20261013-01/source_native01-pytest',
 '.cache/test-runs/m3-review-health-20261013-01/installed_native11_r2-pytest',
 '.cache/test-runs/m3-review-health-20261013-01/source_native11_r2-pytest',
 '.cache/test-runs/m3-pair-validation-repair-20261013-01/source_green01-pytest',
)

def approved_key(key):
    if (type(key) is not str or '\\' in key or ':' in key or '\0' in key
            or any(part in ('','.','..') for part in key.split('/'))
            or not any(key==root or key.startswith(root+'/') for root in ROOTS)):
        raise ValueError('REMOVAL_PATH_OUTSIDE_APPROVED_ROOTS')
    return key

def plan_removal(groups):
    if tuple(group['root'] for group in groups)!=ROOTS:
        raise ValueError('EXACT_FOUR_ROOTS_REQUIRED')
    rows=[]
    for group in groups:
        root=group['root'];entries=group['entries']
        if root not in entries or entries[root]['kind']!='directory':
            raise ValueError('ORIGINAL_ROOT_DIRECTORY_REQUIRED')
        for key,value in entries.items():
            approved_key(key)
            if key!=root and not key.startswith(root+'/'):
                raise ValueError('CROSS_ROOT_MEMBER')
            if value['kind'] not in ('directory','file','reparse'):
                raise ValueError('UNSUPPORTED_ORIGINAL_KIND')
            if key!=root and entries.get(key.rsplit('/',1)[0],{}).get('kind')!='directory':
                raise ValueError('ORIGINAL_PARENT_MISSING')
            rows.append(dict(value,path=key))
    if len({row['path'] for row in rows})!=len(rows):
        raise ValueError('DUPLICATE_ORIGINAL_MEMBER')
    rank={'reparse':0,'file':1,'directory':2}
    return sorted(rows,key=lambda row:(rank[row['kind']],-row['path'].count('/'),row['path']))

def remove_checked(api,handle,row,*,check,note,absent,disposed,poll):
    approved_key(row['path']);poll();check(row,handle)
    intent={key:row[key] for key in ('path','kind','volume','file_id')}
    if 'verified_before_removal' in row:intent['verified_before_removal']=row['verified_before_removal']
    note(dict(action='REMOVE_INTENT',**intent))
    disposition=c.c_int32(1)
    api.checked(api.SetFileInformationByHandle(handle.get(),4,c.byref(disposition),c.sizeof(disposition)),'RemoveExactApprovedEntry')
    handle.close();disposed(row);absent(row)
    note(dict(action='REMOVED',path=row['path'],kind=row['kind'],file_id=row['file_id']))

def sha(path,poll=lambda:None):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        while data:=stream.read(65536):poll();result.update(data)
    return result.hexdigest()

def save_removal_record(path,value):
    assert path.parent==NAMESPACE,'REMOVAL_RECORD_LOCATION'
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    assert len(raw)<=1024**2,'REMOVAL_RECORD_BOUND'
    with path.open('xb') as output:
        assert output.write(raw)==len(raw)
        output.flush();os.fsync(output.fileno())

def namespace_usage(api,poll=lambda:None):
    total=0
    for base,dirs,files in os.walk(NAMESPACE,followlinks=False):
        for path in [Path(base)]+[Path(base)/name for name in files]:
            poll()
            with api.open_file(path,0x80,3,flags=0x02200000) as handle:
                assert not api.file_info(handle).attributes&0x400,'NAMESPACE_REPARSE_DENIED'
                total+=archive.native_allocation(api,handle)['charged']
                total+=sum(row['charged'] for row in archive.native_streams(api,handle))
        assert all(not (Path(base)/name).lstat().st_file_attributes&0x400 for name in dirs)
    return total

def require_namespace_budget(api,hold=0):
    original=(NAMESPACE/'execution-budget-baseline.json').read_bytes()
    baseline=json.loads(original)
    approval=json.loads((NAMESPACE/'recovery01-owner-approval.json').read_bytes())
    assert hashlib.sha256(original).hexdigest()==approval['original_budget_baseline_sha256']
    assert approval['additional_attempts']==1 and approval['prior_removal_attempts']==1
    assert approval['additional_records_bytes']==8*1024**2
    assert approval['cumulative_growth_maximum_bytes']==24*1024**2
    assert approval['total_namespace_maximum_bytes']==32*1024**2
    assert approval['additional_review_rounds']==2 and approval['prior_review_rounds_used']==3
    assert approval['failed_attempt_preserved'] is True
    assert approval['scratch_growth_bytes']==0
    assert not any(approval[key] for key in ('administrator_elevation_approved','security_changes_approved','halt_change_approved','runtime_or_clone_writes_approved'))
    used=namespace_usage(api)
    assert baseline['scope']=='CUMULATIVE_STAGE_A_AND_B'
    assert baseline['growth_maximum_bytes']==16*1024**2 and baseline['total_namespace_maximum_bytes']==32*1024**2
    assert used+hold<=baseline['total_namespace_maximum_bytes']
    assert used-baseline['initial_namespace_charged_bytes']+hold<=approval['cumulative_growth_maximum_bytes']
    assert shutil.disk_usage(ROOT).free>=50*1024**3
    return used

def verify_backups(api,poll,locks):
    """Retain read-only archive handles and verify exact Stage A streams."""
    result=json.loads((NAMESPACE/'archive-result.json').read_bytes())
    closure=json.loads((NAMESPACE/'stage-a-closure.json').read_bytes())
    assert closure['status']=='STAGE_A_VERIFIED_ORIGINALS_INTACT' and closure['exit_code']==0
    assert closure['process_exit_observed'] and closure['active_processes_after_cleanup']==0
    assert sha(NAMESPACE/'archive-result.json',poll)==closure['archive_result_sha256']
    assert sha(NAMESPACE/'independent-verification.json',poll)=='5b955917c2dc863334442f8d6cf8bcad35fd9c777043e939ff09b1f4926f1c50'
    metadata=json.loads((NAMESPACE/'gate-metadata.json').read_bytes())
    assert tuple(group['root'] for group in metadata['groups'])==ROOTS
    for path in (ROOT/'backups',archive.DESTINATION):locks.enter_context(api.open_directory(path))
    retained={}
    for row in result['payloads']:
        name=row['name'];assert '/' not in name and '\\' not in name
        handle=locks.enter_context(api.open_file(archive.DESTINATION/name,0x80000080,1))
        assert api.file_identity(handle)==(row['volume'],row['file_id'])
        value=archive.native_allocation(api,handle)
        assert value['size']==row['size'] and value['allocation']==row['allocation']
        assert not archive.native_streams(api,handle)
        retained[name]=handle
    index_handle=locks.enter_context(api.open_file(archive.DESTINATION/'index.json',0x80000080,1))
    assert api.file_identity(index_handle)==(result['index_volume'],result['index_file_id'])
    assert not archive.native_streams(api,index_handle)
    assert 0<result['index_size']<=131072
    reader=archive.NativeReader(api,index_handle,poll);raw=archive.exact(reader,result['index_size'])
    assert len(raw)==result['index_size'] and not reader.read(1)
    assert reader.digest.hexdigest()==result['index_sha256']
    index=json.loads(raw);assert tuple(index['roots'])==ROOTS and index['payloads']==result['payloads']
    names=set(retained)|{'index.json'}
    assert len(names)==9 and {path.name for path in archive.DESTINATION.iterdir()}==names
    for group,(number,root,_,_) in zip(metadata['groups'],archive.SPEC,strict=True):
        old=json.loads((ROOT/'.cache/test-runs/m5-fixture-consolidation-plan-20261015-01'/f'group-{number:02d}.json').read_bytes())
        for suffix,content in (('contents.tar.gz',True),('properties.json.gz',False)):
            name=f'root-{number:02d}.{suffix}';reader=archive.NativeReader(api,retained[name],poll)
            if content:archive.verify_canonical_tar(reader,old['inventory'],poll)
            else:archive.verify_properties(reader,archive.compact(group),poll)
            row=next(value for value in result['payloads'] if value['name']==name)
            assert reader.count==row['size'] and reader.digest.hexdigest()==row['sha256']
    return result,index

def verify_retained_links(api,entries,removed,poll):
    """Check every remaining master link against the fresh raw-link record."""
    from compertum.runtime._windows import HANDLE,DWORD,BOOL
    device=c.WinDLL('kernel32',use_last_error=True).DeviceIoControl
    device.argtypes=[HANDLE,DWORD,HANDLE,DWORD,HANDLE,DWORD,c.POINTER(DWORD),HANDLE];device.restype=BOOL
    count=0
    for key,row in entries.items():
        if key in removed:continue
        poll()
        with api.open_file(ROOT/key,0x80,1,flags=0x02200000) as handle:
            info=api.file_info(handle);volume,file_id=api.file_identity(handle)
            observed=dict(volume=volume,file_id=file_id,attributes=info.attributes,hardlinks=info.links,creation_100ns=(info.creation.high<<32)|info.creation.low,write_100ns=(info.write.high<<32)|info.write.low)
            assert all(observed[field]==row[field] for field in archive.IDENTITY_KEYS),key
            assert archive.native_allocation(api,handle)=={field:row[field] for field in ('size','allocation','charged')}
            assert archive.native_streams(api,handle)==row['streams']
            buffer=c.create_string_buffer(16384);size=DWORD()
            api.checked(device(handle.get(),0x900a8,None,0,buffer,len(buffer),c.byref(size),None),'PreservedRawLink')
            assert buffer.raw[:size.value].hex()==row['raw_reparse_hex'] and os.readlink(ROOT/key)==row['target'],key
        count+=1
    assert count==1627
    return count

def execute_removal(context):
    """Follow the approved Stage B procedure after a fresh complete snapshot."""
    api=context['api'];base_poll=context['poll'];meta=context['meta'];allocation=context['allocation']
    streams=context['streams'];namespace=context['N'];assert namespace==NAMESPACE
    approval=json.loads((namespace/'stage-b-owner-approval.json').read_bytes())
    assert approval['stage_b_exact_removal_approved'] and approval['historical_copy_limits_accepted']
    assert approval['master_only_incoming_link_scope_accepted'] and tuple(approval['approved_roots'])==ROOTS
    assert not approval['administrator_elevation_approved'] and not approval['security_changes_approved']
    assert approval['scratch_growth_bytes']==0
    assert approval['stage_a_independent_verification_sha256']==sha(namespace/'independent-verification.json')
    fresh=json.loads((namespace/'recovery01-stage-b-gate-metadata.json').read_bytes())
    capacity=json.loads((namespace/'recovery01-stage-b-gate-capacity.json').read_bytes())
    links=json.loads((namespace/'recovery01-stage-b-gate-links.json').read_bytes())
    assert capacity['capacity_qualified'] and not capacity['unknown_streams'] and not capacity['barriers'] and not capacity['ledger_failures']
    assert not links['incoming'] and not links['unresolved'] and not links['barriers']
    archive.require_scratch_baseline(capacity['categories']['scratch'],capacity['outstanding_conservative_bytes']['scratch'])
    pending=dict(capacity['outstanding_conservative_bytes']);pending['records']+=10*1024**2
    assert pending['records']>=34*1024**2
    assert all(capacity['categories'][key]+pending[key]<=limit for key,limit in context['CAPS'].items() if key!='scratch')
    assert sum(capacity['categories'].values())+sum(pending.values())<=50*1024**3
    assert capacity['free_bytes']-34*1024**2>=50*1024**3
    rows=plan_removal(fresh['groups']);assert len(rows)==1827
    assert {kind:sum(row['kind']==kind for row in rows) for kind in ('file','directory','reparse')}==dict(file=1098,directory=718,reparse=11)
    result_path=namespace/'recovery01-stage-b-result.json';manifest_path=namespace/'recovery01-stage-b-removal-manifest.json';journal_path=namespace/'recovery01-stage-b-removal-journal.jsonl'
    assert not any(path.exists() for path in (result_path,manifest_path,journal_path)),'PRESERVE_PREVIOUS_REMOVAL_ATTEMPT'
    last_budget=-float('inf');disposed_paths=[];verified_paths=[];changed_dirs=set()
    result=dict(status='STAGE_B_FAILED_RETAIN_ALL_PROGRESS',entries_disposed=0,entries_verified_absent=0,recursive_removal=False,permissions_changed=False,privileges_changed=False,extra_roots_removed=False)
    def poll():
        nonlocal last_budget
        base_poll()
        if time.monotonic()-last_budget>=.25:
            require_namespace_budget(api,256*1024);last_budget=time.monotonic()
    with ExitStack() as locks:
        parents={};handles={};by_name={row['path']:row for row in rows}
        def hold_outside(path):
            current=ROOT
            if current not in parents:parents[current]=locks.enter_context(api.open_directory(current))
            for part in path.relative_to(ROOT).parts:
                current=current/part
                assert not any(current==ROOT/root or current.is_relative_to(ROOT/root) for root in ROOTS)
                if current not in parents:parents[current]=locks.enter_context(api.open_directory(current))
        hold_outside(namespace)
        for root in ROOTS:hold_outside((ROOT/root).parent)
        backup_result,index=verify_backups(api,poll,locks)
        reserve=locks.enter_context(api.open_file(ROOT/'state/execution-reserve.bin',0x80,1))
        expected_reserve=capacity['execution_reserve_observation']
        assert all(meta(reserve)[key]==expected_reserve[key] for key in archive.IDENTITY_KEYS)
        assert allocation(reserve)['allocation']==1024**3 and not streams(reserve)
        for ledger in capacity['ledgers']:
            path=ROOT/ledger['path'];hold_outside(path.parent)
            locks.enter_context(api.open_file(path,0x80000080,1))
            assert context['digest'](path)==ledger['sha256']
            assert not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal'))
        old_groups=json.loads((namespace/'gate-metadata.json').read_bytes())['groups']
        for group,old in zip(fresh['groups'],old_groups,strict=True):
            assert group['root']==old['root'] and set(group['entries'])==set(old['entries'])
            for key,row in group['entries'].items():
                poll();original=old['entries'][key]
                assert all(row[field]==original[field] for field in (*archive.IDENTITY_KEYS,'kind','size','allocation','charged','owner_group_dacl_hex'))
                if row['kind']=='file':assert row['sha256']==original['sha256']
                if row['kind']=='reparse':assert row['target']==original['target'] and row['raw_reparse_hex']==original['raw_reparse_hex']
                # One retained handle per selected directory, carrying DELETE
                # from the start. No read-only directory handle blocks removal.
                access=0x30080|(0x80000000 if row['kind']=='file' else 0)
                handles[key]=locks.enter_context(api.open_file(ROOT/key,access,1,flags=0x02200000))
        def check(row,handle,empty=False):
            poll();key=row['path'];observed=meta(handle)
            fields=archive.IDENTITY_KEYS if key not in changed_dirs else tuple(field for field in archive.IDENTITY_KEYS if field!='write_100ns')
            assert all(observed[field]==row[field] for field in fields),key
            value=allocation(handle)
            if key in changed_dirs:assert row['kind']=='directory' and value['charged']<=row['charged']
            else:assert value=={field:row[field] for field in ('size','allocation','charged')},key
            assert not streams(handle) and context['security'](handle,7)==row['owner_group_dacl_hex'],key
            if row['kind']=='file':
                reader=archive.NativeReader(api,handle,poll)
                while reader.read(65536):pass
                assert reader.count==row['size'] and reader.digest.hexdigest()==row['sha256'],key
            elif row['kind']=='reparse':assert context['reparse'](handle,ROOT/key)=={field:row[field] for field in ('target','raw_reparse_hex')},key
            elif empty:assert not os.listdir(ROOT/key),'DIRECTORY_NOT_EMPTY'
            row['verified_before_removal']={field:observed[field] for field in archive.IDENTITY_KEYS}|value
        for row in rows:check(row,handles[row['path']])
        for group in fresh['groups']:
            observed={group['root']}
            for base,dirs,files in os.walk(ROOT/group['root'],followlinks=False):
                poll()
                for name in dirs+files:observed.add((Path(base)/name).relative_to(ROOT).as_posix())
                dirs[:]=[name for name in dirs if not (Path(base)/name).lstat().st_file_attributes&0x400]
            assert observed==set(group['entries'])
        manifest=dict(scope='EXACT_APPROVED_FOUR_ROOTS',roots=list(ROOTS),metadata_sha256=sha(namespace/'recovery01-stage-b-gate-metadata.json'),capacity_sha256=sha(namespace/'recovery01-stage-b-gate-capacity.json'),approval_sha256=sha(namespace/'stage-b-owner-approval.json'),recovery_approval_sha256=sha(namespace/'recovery01-owner-approval.json'),archive_index_sha256=backup_result['index_sha256'],entries=[{key:row[key] for key in ('path','kind','volume','file_id')} for row in rows])
        manifest_bytes=len((json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode())
        assert manifest_bytes<=1024**2
        # Hold the actual full manifest plus the entire journal, result and
        # final-receipt ceilings before the first irreversible operation.
        require_namespace_budget(api,((manifest_bytes+4095)//4096)*4096+3*1024**2+1024**2+512*1024)
        save_removal_record(manifest_path,manifest)
        try:
            with journal_path.open('xb',buffering=0) as log:
                def note(value):
                    poll();data=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
                    assert len(data)<32768 and log.tell()+len(data)<=3*1024**2,'REMOVAL_JOURNAL_BOUND'
                    assert log.write(data)==len(data);os.fsync(log.fileno())
                def absent(row):
                    try:(ROOT/row['path']).lstat()
                    except FileNotFoundError:return
                    raise RuntimeError('REMOVED_ENTRY_STILL_PRESENT')
                def immediately_check(row,handle):
                    parent=row['path'].rsplit('/',1)[0]
                    if parent in by_name:check(by_name[parent],handles[parent])
                    check(row,handle,empty=True)
                for row in rows:
                    remove_checked(api,handles[row['path']],row,check=immediately_check,note=note,absent=absent,disposed=lambda value:disposed_paths.append(value['path']),poll=poll)
                    verified_paths.append(row['path'])
                    changed_dirs.add(row['path'].rsplit('/',1)[0])
            for row in rows:absent(row)
            verify_backups(api,poll,locks)
            preserved_links=verify_retained_links(api,links['links'],set(by_name),poll)
            for ledger in capacity['ledgers']:
                path=ROOT/ledger['path'];assert context['digest'](path)==ledger['sha256']
                assert not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal'))
            assert all(meta(reserve)[key]==expected_reserve[key] for key in archive.IDENTITY_KEYS)
            assert allocation(reserve)['allocation']==1024**3
            result.update(status='STAGE_B_CHILD_COMPLETE_REQUIRES_PARENT_CLOSURE',original_roots_absent=4,files_removed=1098,directories_removed=718,links_removed=11,preserved_master_links_verified=preserved_links,backup_payloads_verified=8,index_sha256=backup_result['index_sha256'],journal_sha256=sha(journal_path),manifest_sha256=sha(manifest_path),conservative_file_bytes_released=9612976,production_admission=False)
        except BaseException as error:
            result.update(error=type(error).__name__,detail=str(error));raise
        finally:
            result.update(entries_disposed=len(disposed_paths),entries_verified_absent=len(verified_paths),disposed_paths=disposed_paths,verified_absent_paths=verified_paths)
            save_removal_record(result_path,result)
    return result
