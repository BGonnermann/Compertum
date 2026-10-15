"""Independent native inventory checks across deep paths and all budget categories."""
import os
from pathlib import Path
import pytest
from compertum.runtime.identity import resolve_project
from compertum.runtime.errors import RuntimeRefused
from compertum.storage import sample_storage,category,CAPS
pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')

def test_nested_inventory_counts_every_file_in_its_root_category(tmp_path):
 expected={}
 for top in ('data','models','.cache','.venv','backups','artifacts','Data'):
  for depth in (1,3):
   p=tmp_path/top/('/'.join(['child']*depth))/'unicodé space.bin'
   p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'x'*(17+depth))
 # Enumerate independently because Windows folds Data/data case.
 for p in tmp_path.rglob('*.bin'):expected[p.relative_to(tmp_path).as_posix()]=p.stat().st_size
 s=sample_storage(resolve_project(tmp_path))
 assert set(s['files'])==set(expected)
 totals=dict.fromkeys(CAPS,0)
 for n,size in expected.items():
  record=s['files'][n];assert record['size']==size
  assert record['charged']==max(size,record['allocated'])
  totals[category(n)]+=record['charged']
 assert s['categories']==totals

def test_directory_batches_still_enforce_deadline(tmp_path,monkeypatch):
 import compertum.storage as storage
 values=iter((0,6));monkeypatch.setattr(storage.time,'monotonic',lambda:next(values))
 with pytest.raises(RuntimeRefused,match='STORAGE_SCAN_DEADLINE'):sample_storage(resolve_project(tmp_path))

def test_multi_batch_directory_and_empty_siblings_have_exact_inventory(tmp_path):
 # Long names force several native batches while file contents stay small.
 expected={}
 for top in ('.cache','data'):
  directory=tmp_path/top;directory.mkdir()
  (directory/'empty').mkdir()
  for index in range(260):
   path=directory/(str(index).zfill(4)+'_unicod\u00e9_'+('n'*150)+'.bin')
   path.write_bytes(bytes([index%256])*(index%17+1))
   expected[path.relative_to(tmp_path).as_posix()]=path.stat().st_size
 (tmp_path/'alias').symlink_to(tmp_path/'data',target_is_directory=True)
 s=sample_storage(resolve_project(tmp_path))
 assert set(s['files'])==set(expected)|{'alias'}
 assert s['reparse_paths']==['alias']
 totals=dict.fromkeys(CAPS,0)
 for name,value in s['files'].items():
  if name!='alias':assert value['size']==expected[name]
  assert value['charged']==max(value['size'],value['allocated'])
  totals[category(name)]+=value['charged']
 assert s['categories']==totals and s['total_bytes']==sum(totals.values())


@pytest.mark.parametrize('returned_bytes',[0,65537])
def test_native_batch_invalid_returned_size_refuses(tmp_path,monkeypatch,returned_bytes):
 import compertum.storage as storage
 from types import SimpleNamespace
 import compertum._native_storage as reader
 real=reader._library()
 def invalid_open(path,buffer,length,result):
  code=real.cs_open_read(path,buffer,length,result)
  reader.c.cast(result,reader.c.POINTER(reader.Result)).contents.bytes=returned_bytes
  return code
 monkeypatch.setattr(reader,'_library',lambda:SimpleNamespace(cs_open_read=invalid_open,cs_next=real.cs_next,cs_close=real.cs_close))
 with pytest.raises(RuntimeRefused,match='STORAGE_SCAN_UNVERIFIED'):
  sample_storage(resolve_project(tmp_path))
