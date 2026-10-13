from contextlib import contextmanager
import json,shutil,sqlite3
from pathlib import Path
from uuid import uuid4
import pytest
from test_m0_lifecycle import launch,stopped
from compertum.runtime.supervisor import control
from compertum.runtime._pipes import NativePipeAPI
from compertum.runtime._windows import NativeCallError

ROOT=Path(__file__).parents[2]

@pytest.mark.parametrize('phase',['before_write','lost_reply'])
def test_same_control_id_recovers_disconnect_without_duplicate_effect(tmp_path,monkeypatch,phase):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');process,status=launch(tmp_path)
    try:
        method='write_frame' if phase=='before_write' else 'read_frame'
        original=getattr(NativePipeAPI,method);remaining=[1]
        def interrupt(self,*args,**kwargs):
            if remaining[0]:
                remaining[0]=0
                if phase=='lost_reply':original(self,*args,**kwargs)
                raise NativeCallError('SyntheticDisconnect',233)
            return original(self,*args,**kwargs)
        monkeypatch.setattr(NativePipeAPI,method,interrupt)
        request=str(uuid4());result=control(tmp_path,'pause_research',request_id=request)
        assert result['confirmed'] and control(tmp_path,'pause_research',request_id=request)==result
        with sqlite3.connect((tmp_path/'state/research.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            assert db.execute('SELECT count(*) FROM control_requests WHERE request_id=?',(request,)).fetchone()[0]==1
        control(tmp_path,'shutdown');stopped(process)
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)
