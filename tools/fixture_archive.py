"""Archive-only maintenance support. No removal or extraction mode exists."""
if not __debug__:
    raise RuntimeError('OPTIMIZED_PYTHON_DENIED')
import ctypes as c
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import zlib
from contextlib import ExitStack

ROOT=Path(r'C:\Users\bgonn\Desktop\Compertum')
DESTINATION=ROOT/'backups/fixture-consolidation-20261015-01'
SPEC=(
 (0,'.cache/test-runs/m3-pair-validation-repair-20261013-01/source_native01-pytest',917504,818049),
 (1,'.cache/test-runs/m3-review-health-20261013-01/installed_native11_r2-pytest',163840,113230),
 (2,'.cache/test-runs/m3-review-health-20261013-01/source_native11_r2-pytest',163840,112886),
 (5,'.cache/test-runs/m3-pair-validation-repair-20261013-01/source_green01-pytest',65536,23812),
)
BACKUP_CAP=1572864
APPROVED_SCRATCH_MAXIMUM=5369020008
IDENTITY_KEYS=('volume','file_id','attributes','hardlinks','creation_100ns','write_100ns')

def compact(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def require_write_bound(position,amount,maximum):
    if not all(type(value) is int and value>=0 for value in (position,amount,maximum)) or position+amount>maximum:
        raise ValueError('ARCHIVE_WRITE_BOUND')

def require_scratch_baseline(physical,pending):
    if physical>APPROVED_SCRATCH_MAXIMUM or pending!=0:
        raise ValueError('SCRATCH_BASELINE_OR_RESERVATIONS_CHANGED')

class StrictGzipReader:
    """One bounded gzip member; reject extra members, trailing bytes and truncation."""
    def __init__(self,source,poll):
        self.source=source;self.poll=poll;self.codec=zlib.decompressobj(31)
        self.pending=b'';self.finished=False;self.total=0
    def read(self,amount):
        assert 0<=amount<=65536
        result=bytearray()
        while len(result)<amount and not self.finished:
            self.poll()
            if self.codec.eof:
                if self.pending or self.codec.unused_data or self.source.read(1):raise ValueError('GZIP_TRAILING_DATA')
                self.finished=True;break
            data=self.pending or self.source.read(65536)
            if not data:raise ValueError('GZIP_TRUNCATED')
            try:part=self.codec.decompress(data,amount-len(result))
            except zlib.error as error:raise ValueError('GZIP_INVALID') from error
            self.pending=self.codec.unconsumed_tail
            result.extend(part);self.total+=len(part)
            if self.total>32*1024**2:raise ValueError('GZIP_EXPANSION_BOUND')
        return bytes(result)

def exact(source,amount):
    result=bytearray()
    while len(result)<amount:
        data=source.read(min(65536,amount-len(result)))
        if not data:raise ValueError('ARCHIVE_TRUNCATED')
        result.extend(data)
    return bytes(result)

def member(name,row):
    item=tarfile.TarInfo(name)
    if row['kind']=='directory':item.type=tarfile.DIRTYPE
    else:item.size=row['size']
    return item

def verify_canonical_tar(source,inventory,poll=lambda:None):
    reader=StrictGzipReader(source,poll);length=0
    members=[(name,row,None) for name,row in sorted(inventory.items()) if row['kind']!='reparse']
    metadata=compact(inventory)
    members.append(('consolidation-metadata.json',dict(kind='file',size=len(metadata)),metadata))
    for name,row,expected in members:
        poll();item=member(name,row);header=item.tobuf(format=tarfile.PAX_FORMAT)
        if exact(reader,len(header))!=header:raise ValueError('TAR_MEMBER_HEADER:'+name)
        length+=len(header);digest=hashlib.sha256();offset=0
        while offset<item.size:
            poll();data=exact(reader,min(65536,item.size-offset));digest.update(data)
            if expected is not None and data!=expected[offset:offset+len(data)]:raise ValueError('TAR_METADATA_MISMATCH')
            offset+=len(data)
        if expected is None and row['kind']=='file' and digest.hexdigest()!=row['sha256']:raise ValueError('TAR_FILE_HASH:'+name)
        padding=(-item.size)%512
        if exact(reader,padding)!=b'\0'*padding:raise ValueError('TAR_MEMBER_PADDING')
        length+=item.size+padding
    padding=1024+(-(length+1024))%tarfile.RECORDSIZE
    if exact(reader,padding)!=b'\0'*padding or reader.read(1):raise ValueError('TAR_TRAILING_DATA')

def verify_properties(source,expected,poll=lambda:None):
    reader=StrictGzipReader(source,poll);offset=0
    while offset<len(expected):
        poll();data=exact(reader,min(65536,len(expected)-offset))
        if data!=expected[offset:offset+len(data)]:raise ValueError('PROPERTIES_MISMATCH')
        offset+=len(data)
    if reader.read(1):raise ValueError('PROPERTIES_TRAILING_DATA')

class NativeReader:
    def __init__(self,api,handle,poll):
        from compertum.runtime._windows import HANDLE,BOOL
        self.api=api;self.handle=handle;self.poll=poll
        self.seek=c.WinDLL('kernel32',use_last_error=True).SetFilePointerEx
        self.seek.argtypes=[HANDLE,c.c_int64,c.POINTER(c.c_int64),c.c_uint32];self.seek.restype=BOOL
        api.checked(self.seek(handle.get(),0,None,0),'ArchiveReadReset')
        self.digest=hashlib.sha256();self.count=0
    def read(self,amount):
        self.poll();assert 0<=amount<=65536
        buffer=c.create_string_buffer(amount);count=c.c_uint32()
        self.api.checked(self.api.ReadFile(self.handle.get(),buffer,amount,c.byref(count),None),'ArchiveRead')
        data=buffer.raw[:count.value];self.digest.update(data);self.count+=len(data);return data

class NativeFile:
    """CREATE_NEW and fixed physical allocation; never opens an original to write."""
    def __init__(self,api,path,maximum,poll,allocation):
        self.api=api;self.path=path;self.maximum=maximum;self.poll=poll;self.allocation=allocation
        assert maximum>0 and maximum%4096==0
        self.handle=api.open_file(path,0xC0000080,1,disposition=1,flags=0x00200000)
        try:
            self.original_id=api.file_identity(self.handle)
            amount=c.c_int64(maximum)
            api.checked(api.SetFileInformationByHandle(self.handle.get(),5,c.byref(amount),c.sizeof(amount)),'ArchivePreallocation')
            value=allocation(self.handle)
            assert value['size']==0 and value['allocation']==maximum,'ARCHIVE_PREALLOCATION_UNVERIFIED'
            self.position=0;self.digest=hashlib.sha256()
        except BaseException:
            self.handle.close();raise
    def write(self,data):
        self.poll();require_write_bound(self.position,len(data),self.maximum)
        count=c.c_uint32();buffer=c.create_string_buffer(data)
        self.api.checked(self.api.WriteFile(self.handle.get(),buffer,len(data),c.byref(count),None),'ArchiveWrite')
        assert count.value==len(data),'ARCHIVE_SHORT_WRITE'
        self.position+=len(data);self.digest.update(data)
        value=self.allocation(self.handle)
        assert value['size']==self.position and value['allocation']<=self.maximum
        return len(data)
    def flush(self):
        self.api.checked(self.api.FlushFileBuffers(self.handle.get()),'ArchiveFlush')
    def close(self):
        self.handle.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def save_record(path,value):
    raw=json.dumps(value,sort_keys=True,indent=2).encode()+b'\n'
    assert len(raw)<=512*1024
    with path.open('xb') as output:
        assert output.write(raw)==len(raw)
        output.flush();os.fsync(output.fileno())

def native_allocation(api,handle):
    from compertum.storage import StandardInfo
    value=StandardInfo()
    api.checked(api.GetFileInformationByHandleEx(handle.get(),1,c.byref(value),c.sizeof(value)),'ArchiveAllocation')
    assert value.size>=0 and value.allocation>=0
    return dict(size=value.size,allocation=value.allocation,charged=max(value.size,value.allocation))

def native_streams(api,handle):
    import struct
    capacity=4096
    while True:
        buffer=c.create_string_buffer(capacity)
        if api.GetFileInformationByHandleEx(handle.get(),7,buffer,capacity):break
        error=c.get_last_error()
        if error==38:return []
        if error not in (122,234) or capacity>=1024**2:raise OSError(error,'ArchiveStreams')
        capacity*=2
    offset=0;found=[]
    while True:
        step,length,size,allocated=struct.unpack_from('<IIqq',buffer.raw,offset)
        if not any((offset,step,length,size,allocated)):return found
        assert length>0 and length%2==0 and offset+24+length<=capacity and size>=0 and allocated>=0
        name=buffer.raw[offset+24:offset+24+length].decode('utf-16-le')
        if name!='::$DATA':found.append(dict(name=name,size=size,allocation=allocated,charged=max(size,allocated)))
        if not step:return found
        assert step%8==0 and step>=24+length and offset+step<capacity
        offset+=step

def create_archives(context):
    """Run only after the reviewed, fresh capacity probe in the same native Job."""
    api=context['api'];poll=context['poll'];meta=context['meta'];allocation=context['allocation'];streams=context['streams']
    namespace=context['N'];capacity=json.loads((namespace/'gate-capacity.json').read_bytes())
    metadata=json.loads((namespace/'gate-metadata.json').read_bytes())
    link_check=json.loads((namespace/'gate-links.json').read_bytes())
    approval=json.loads((namespace/'owner-approval.json').read_bytes())
    assert approval['maintenance_exception_approved'] and approval['stage_a_archive_and_verification_approved']
    assert not approval['stage_b_removal_approved'] and approval['scratch_growth_bytes']==0
    assert capacity['capacity_qualified'] and not capacity['barriers'] and not capacity['unknown_streams'] and not capacity['ledger_failures']
    assert not link_check['incoming'] and not link_check['unresolved'] and not link_check['barriers']
    assert tuple(group['root'] for group in metadata['groups'])==tuple(row[1] for row in SPEC)
    pending=dict(capacity['outstanding_conservative_bytes'])
    require_scratch_baseline(capacity['categories']['scratch'],pending['scratch'])
    assert capacity['probe_growth_hold_bytes']==16*1024**2 and pending['records']>=16*1024**2
    pending['records']+=10*1024**2  # Retain the old preparation hold and publication allowance.
    pending['backups']+=BACKUP_CAP
    charged={key:capacity['categories'][key]+pending[key] for key in context['CAPS']}
    assert all(charged[key]<=limit for key,limit in context['CAPS'].items() if key!='scratch')
    assert sum(charged.values())<=50*1024**3
    assert capacity['free_bytes']-26*1024**2-BACKUP_CAP>=50*1024**3
    assert not os.path.lexists(DESTINATION),'PRESERVE_EXISTING_BACKUP_DESTINATION'
    assert not (namespace/'archive-result.json').exists(),'PRESERVE_EXISTING_ARCHIVE_RESULT'
    before_reserve=capacity['execution_reserve_observation']
    results=[]
    with ExitStack() as locks:
        held={}
        def hold(path):
            current=ROOT
            if current not in held:held[current]=locks.enter_context(api.open_directory(current))
            for part in path.relative_to(ROOT).parts:
                current=current/part
                if current not in held:held[current]=locks.enter_context(api.open_directory(current))
            return held[path]
        hold(namespace);backup_parent=hold(ROOT/'backups')
        parent_before=allocation(backup_parent)['charged']
        ledgers=[]
        for ledger in capacity['ledgers']:
            path=ROOT/ledger['path'];hold(path.parent)
            handle=locks.enter_context(api.open_file(path,0x80000080,1))
            assert context['digest'](path)==ledger['sha256']
            assert not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal'))
            ledgers.append((path,handle,ledger))
        reserve=locks.enter_context(api.open_file(ROOT/'state/execution-reserve.bin',0x80,1))
        assert all(meta(reserve)[key]==before_reserve[key] for key in IDENTITY_KEYS)
        assert allocation(reserve)['allocation']>=1024**3
        source_handles={};old_groups=[]
        for number,root,cap,expected_size in SPEC:
            old=json.loads((context['P']/f'group-{number:02d}.json').read_bytes());old_groups.append(old)
            fresh=next(group for group in metadata['groups'] if group['root']==root)
            hold(ROOT/root)
            for key,row in sorted(fresh['entries'].items()):
                poll();path=ROOT/key;assert path==ROOT/root or path.is_relative_to(ROOT/root)
                hold(path if row['kind']=='directory' else path.parent)
                access=0x20080|(0x80000000 if row['kind']=='file' else 0)
                handle=locks.enter_context(api.open_file(path,access,1,flags=0x02200000))
                assert all(meta(handle)[field]==row[field] for field in IDENTITY_KEYS),key
                assert allocation(handle)=={field:row[field] for field in ('size','allocation','charged')},key
                assert not streams(handle),key
                assert context['security'](handle,7)==row['owner_group_dacl_hex'],key
                if row['kind']=='reparse':assert context['reparse'](handle,path)=={field:row[field] for field in ('target','raw_reparse_hex')},key
                source_handles[key]=handle
            assert set(old['inventory'])==set(fresh['entries'])
        def check_sources():
            for old,fresh in zip(old_groups,metadata['groups'],strict=True):
                root=fresh['root'];observed={root}
                for base,dirs,files in os.walk(ROOT/root,followlinks=False):
                    poll()
                    for name in dirs+files:observed.add((Path(base)/name).relative_to(ROOT).as_posix())
                    dirs[:]=[name for name in dirs if not (Path(base)/name).lstat().st_file_attributes&0x400]
                assert observed==set(old['inventory']),root
                for key,row in fresh['entries'].items():
                    poll();handle=source_handles[key]
                    assert all(meta(handle)[field]==row[field] for field in IDENTITY_KEYS),key
                    assert allocation(handle)=={field:row[field] for field in ('size','allocation','charged')},key
                    assert not streams(handle) and context['security'](handle,7)==row['owner_group_dacl_hex'],key
                    if row['kind']=='reparse':assert context['reparse'](handle,ROOT/key)=={field:row[field] for field in ('target','raw_reparse_hex')},key
                    if row['kind']=='file':
                        reader=NativeReader(api,handle,poll)
                        while reader.read(65536):pass
                        assert reader.count==row['size'] and reader.digest.hexdigest()==row['sha256'],key
        check_sources()
        save_record(namespace/'maintenance-allowance.json',dict(scope='APPROVED_STAGE_A_ONLY',backup_maximum=BACKUP_CAP,records_execution_hold=16*1024**2,other_records_hold=10*1024**2,starting_scratch_overage=max(0,charged['scratch']-context['CAPS']['scratch']),scratch_growth=0,execution_reserve_untouched=True,removal_authorized=False,capacity_sha256=context['digest'](namespace/'gate-capacity.json'),approval_sha256=context['digest'](namespace/'owner-approval.json')))
        DESTINATION.mkdir()
        destination_handle=hold(DESTINATION)
        outputs={}
        for number,root,cap,expected_size in SPEC:
            content_cap=((expected_size+4095)//4096)*4096
            for suffix,maximum in (('contents.tar.gz',content_cap),('properties.json.gz',cap-content_cap)):
                name=f'root-{number:02d}.{suffix}'
                outputs[name]=locks.enter_context(NativeFile(api,DESTINATION/name,maximum,poll,allocation))
        outputs['index.json']=locks.enter_context(NativeFile(api,DESTINATION/'index.json',131072,poll,allocation))
        read_handles={}
        def backup_usage():
            poll()
            extra=max(0,allocation(backup_parent)['charged']-parent_before)+allocation(destination_handle)['charged']
            assert not streams(destination_handle) and not streams(backup_parent)
            total=extra
            for name,output in outputs.items():
                handle=read_handles.get(name,output.handle)
                assert api.file_identity(handle)==output.original_id
                info=api.file_info(handle);assert not info.attributes&0x4E10 and info.links==1
                assert not streams(handle)
                value=allocation(handle);assert value['charged']<=output.maximum
                total+=value['charged']
            assert extra<=131072 and total<=BACKUP_CAP
            assert shutil.disk_usage(ROOT).free>=50*1024**3
            return total
        backup_usage()
        for old,fresh,(number,root,cap,expected_size) in zip(old_groups,metadata['groups'],SPEC,strict=True):
            output=outputs[f'root-{number:02d}.contents.tar.gz']
            with gzip.GzipFile(fileobj=output,mode='wb',filename='',mtime=0,compresslevel=9) as compressed:
                with tarfile.open(fileobj=compressed,mode='w|',format=tarfile.PAX_FORMAT) as archive:
                    for key,row in sorted(old['inventory'].items()):
                        poll()
                        if row['kind']=='reparse':continue
                        item=member(key,row)
                        if row['kind']=='directory':archive.addfile(item)
                        else:
                            reader=NativeReader(api,source_handles[key],poll);archive.addfile(item,reader)
                            assert reader.count==row['size'] and reader.digest.hexdigest()==row['sha256'],key
                    raw=compact(old['inventory']);item=tarfile.TarInfo('consolidation-metadata.json');item.size=len(raw)
                    archive.addfile(item,io.BytesIO(raw))
            output.flush();assert output.position==expected_size,'FROZEN_CONTENT_STREAM_CHANGED'
            properties=outputs[f'root-{number:02d}.properties.json.gz']
            properties.write(gzip.compress(compact(fresh),compresslevel=9,mtime=0));properties.flush()
            backup_usage()
        for name,output in outputs.items():
            if name!='index.json':output.close()
        for name,output in outputs.items():
            if name=='index.json':continue
            reopened=locks.enter_context(api.open_file(output.path,0x80000080,1))
            assert api.file_identity(reopened)==output.original_id
            assert allocation(reopened)['size']==output.position
            read_handles[name]=reopened
        for old,fresh,(number,root,cap,expected_size) in zip(old_groups,metadata['groups'],SPEC,strict=True):
            for suffix,is_content in (('contents.tar.gz',True),('properties.json.gz',False)):
                name=f'root-{number:02d}.{suffix}';output=outputs[name]
                reader=NativeReader(api,read_handles[name],poll)
                if is_content:verify_canonical_tar(reader,old['inventory'],poll)
                else:verify_properties(reader,compact(fresh),poll)
                assert reader.count==output.position and reader.digest.hexdigest()==output.digest.hexdigest()
                results.append(dict(name=name,size=output.position,allocation=allocation(read_handles[name])['allocation'],allocation_cap=output.maximum,sha256=reader.digest.hexdigest(),volume=output.original_id[0],file_id=output.original_id[1]))
        index=dict(status='HISTORICAL_EVIDENCE_COPY_INDEX_REQUIRES_STAGE_A_CLOSURE',roots=[row[1] for row in SPEC],groups=[dict(root=root,original_manifest_sha256=fresh['manifest_sha256'],contents=f'root-{number:02d}.contents.tar.gz',properties=f'root-{number:02d}.properties.json.gz',root_identity={key:fresh['entries'][root][key] for key in ('volume','file_id')}) for fresh,(number,root,cap,expected_size) in zip(metadata['groups'],SPEC,strict=True)],payloads=results,member_counts=dict(files=1098,directories=718,links_recorded=11),preservation='CONTENTS_LINK_RECORDS_READABLE_PROPERTIES_ONLY',full_windows_restoration=False,removal_authorized=False,source_input_manifest_sha256=context['digest'](namespace/'inspection-inputs.json'))
        index_output=outputs['index.json'];index_output.write(compact(index));index_output.flush()
        backup_usage();index_output.close()
        read_handles['index.json']=locks.enter_context(api.open_file(index_output.path,0x80000080,1))
        assert api.file_identity(read_handles['index.json'])==index_output.original_id
        reader=NativeReader(api,read_handles['index.json'],poll)
        assert exact(reader,len(compact(index)))==compact(index) and not reader.read(1)
        assert reader.digest.hexdigest()==index_output.digest.hexdigest()
        check_sources()
        for path,handle,ledger in ledgers:
            assert context['digest'](path)==ledger['sha256']
            assert not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal'))
        assert all(meta(reserve)[key]==before_reserve[key] for key in IDENTITY_KEYS)
        assert allocation(reserve)['allocation']==before_reserve['allocation']
        names={output.path.name for output in outputs.values()}
        assert {path.name for path in DESTINATION.iterdir()}==names
        record=dict(status='STAGE_A_CHILD_VERIFICATION_COMPLETE',requires_successful_parent_job_closure=True,payload_files=8,index_file='index.json',index_sha256=index_output.digest.hexdigest(),index_size=index_output.position,index_volume=index_output.original_id[0],index_file_id=index_output.original_id[1],backup_charged_bytes=backup_usage(),backup_maximum_bytes=BACKUP_CAP,files_verified=1098,directories_verified=718,link_records_verified=11,original_entries_present=1827,originals_changed=0,files_removed=0,scratch_growth=0,scratch_growth_scope='THIS_HELPER_WRITES_ONLY_NOT_A_POSTRUN_CENSUS',starting_scratch_bytes=capacity['categories']['scratch'],approved_scratch_maximum=APPROVED_SCRATCH_MAXIMUM,permissions_changed=False,privileges_changed=False,removal_authorized=False,payloads=results)
        save_record(namespace/'archive-result.json',record)
        return record
