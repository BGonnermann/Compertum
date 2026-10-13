"""Exit classification via simulated native API observations, not live Jobs."""
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from test_final_attempts import context,start
from compertum.runtime.errors import RuntimeRefused
from compertum.final_completion import observe_exited


@pytest.mark.parametrize('mode,status',[('exited','VERIFIED_EXIT'),('reused','VERIFIED_PID_REUSED'),('absent','VERIFIED_ABSENT'),('live',None),('denied',None),('wait_error',None),('snapshot_present',None)])
def test_original_pid_must_be_proven_gone(monkeypatch,mode,status):
 import compertum.runtime._windows as windows
 n=start(context())['attempt']['native_execution'];p=n['process']
 @contextmanager
 def process(pid):
  assert pid==p['pid']
  if mode in ('absent','snapshot_present'):raise windows.NativeCallError('OpenProcess',87)
  if mode=='denied':raise windows.NativeCallError('OpenProcess',5)
  yield SimpleNamespace(get=lambda:1)
 api=SimpleNamespace(open_process=process,creation_time=lambda h:p['creation_filetime']+(mode=='reused'),WaitForSingleObject=lambda *a:0xffffffff if mode=='wait_error' else 258 if mode in ('live','reused') else 0,process_snapshot=lambda:[p['pid']] if mode=='snapshot_present' else [])
 monkeypatch.setattr(windows,'WindowsAPI',lambda:api)
 if status:
  proof=observe_exited(n);assert proof['status']==status and proof['process']==p
 else:
  with pytest.raises(RuntimeRefused):observe_exited(n)
