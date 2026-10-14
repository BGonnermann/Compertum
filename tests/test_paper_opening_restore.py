"""Pure simulated directory entries for the restore-absence decision."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import pytest
from compertum.runtime import paper_opening as m
from compertum.runtime.errors import RuntimeRefused

@pytest.fixture
def directory(monkeypatch):
 root=Path('memory-only');lease=SimpleNamespace(project_id='a'*64,generation=19)
 owner=SimpleNamespace(lease=lease,store=SimpleNamespace(root=root,path=root/'state/execution.sqlite'))
 guard=SimpleNamespace(api=SimpleNamespace(open_directory=lambda _:nullcontext()))
 entries=[]
 monkeypatch.setattr(m,'_owner_scope',lambda _:nullcontext(guard))
 monkeypatch.setattr(m,'checked_path',lambda root,path:path)
 monkeypatch.setattr(m,'_active_store_path',lambda root,project,role:root/'state/execution.sqlite')
 monkeypatch.setattr(m,'os',SimpleNamespace(scandir=lambda _:nullcontext(iter(entries))))
 return owner,entries

def entry(name,*,reparse=False):return SimpleNamespace(name=name,stat=lambda **kw:SimpleNamespace(st_file_attributes=0x400 if reparse else 0),is_symlink=lambda:False)

def test_normal_process_restart_does_not_block_first_pin(directory):
 owner,entries=directory;entries.extend([entry('execution.sqlite'),entry('locks')])
 assert m._restore_clear(owner)

@pytest.mark.parametrize('name',['active-generation.json','generations','restore-operation.json','restore-11111111-1111-4111-8111-111111111111.jsonl','aborted-pointer-11111111-1111-4111-8111-111111111111.json','RESTORE-OPERATION.JSON'])
def test_any_restore_marker_blocks_first_pin_even_if_other_markers_are_missing(directory,name):
 owner,entries=directory;entries.append(entry(name));assert not m._restore_clear(owner)


def test_restored_database_cannot_create_first_pin_without_visible_pointer(directory):
 owner,entries=directory;owner.store.path=owner.store.root/'state/generations/old/execution.sqlite';assert not m._restore_clear(owner)

@pytest.mark.parametrize('change',['overbound','reparse','unreadable','resolver'])
def test_unknown_restore_absence_fails_closed(directory,monkeypatch,change):
 owner,entries=directory
 if change=='overbound':entries.extend(entry(str(n)) for n in range(513))
 elif change=='reparse':entries.append(entry('unexpected',reparse=True))
 elif change=='unreadable':monkeypatch.setattr(m,'os',SimpleNamespace(scandir=lambda _:(_ for _ in ()).throw(PermissionError())))
 else:monkeypatch.setattr(m,'_active_store_path',lambda *a:(_ for _ in ()).throw(RuntimeRefused('RESTORE_RECOVERY_REQUIRED')))
 with pytest.raises(RuntimeRefused):m._restore_clear(owner)
