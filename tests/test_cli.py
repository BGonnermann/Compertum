"""Read-only and unavailable CLI calls leave the actual inventory untouched."""
from pathlib import Path
import hashlib
import pytest
from compertum.cli import main

def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

@pytest.mark.parametrize('args',[['doctor','--read-only','--json'],['status'],['start','--mode','supervised-paper'],['data','fetch'],['evaluate','final'],['paper','arm'],['orders','cancel']])
def test_read_only_or_unavailable_never_creates_state(tmp_path,args,capsys):
    (tmp_path/'existing.txt').write_text('preserve')
    before=inventory(tmp_path)
    code=main(['--project-root',str(tmp_path),*args])
    assert code==(0 if args[0]=='doctor' else 3)
    assert inventory(tmp_path)==before
    text=capsys.readouterr().out
    assert 'DISARMED' in text


def test_baseline_cli_routes_explicit_unit_and_controls(tmp_path,monkeypatch,capsys):
    from uuid import uuid4
    import compertum.runtime.supervisor as supervisor
    calls=[];run=str(uuid4())
    monkeypatch.setattr(supervisor,'control',lambda root,action,payload: calls.append((action,payload)) or {'state':'PAUSED'})
    for operation in ('status','resume','step','pause','stop'):
        assert main(['--project-root',str(tmp_path),'baseline',operation,'--run',run])==0
        assert calls[-1]==('baseline',{'run_id':run,'operation':operation})
    assert main(['--project-root',str(tmp_path),'baseline','step'])==3


def test_final_cli_routes_only_existing_seal_controls(tmp_path,monkeypatch,capsys):
 from uuid import uuid4
 import compertum.runtime.supervisor as supervisor
 sid=str(uuid4());calls=[]
 monkeypatch.setattr(supervisor,'control',lambda root,action,payload:calls.append((action,payload)) or dict(status='CONSUMED_WAITING_FOR_BATCH'))
 for operation in ('status','step','resume','pause','stop','recover'):
  assert main(['--project-root',str(tmp_path),'final',operation,'--seal',sid])==0
  assert calls[-1]==('final',dict(seal_id=sid,operation=operation))
 assert main(['--project-root',str(tmp_path),'final','step'])==3
 assert main(['--project-root',str(tmp_path),'final','create','--seal',sid])==3
