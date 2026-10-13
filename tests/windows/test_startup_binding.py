"""Real Windows startup evidence: tests never confer campaign admission."""
import ctypes as c
import hashlib,json,os,shutil,sys
from pathlib import Path
import pytest
from compertum.runtime._windows import OwnedHandle
from compertum.runtime.jobs import JobAPI,create_suspended
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.startup import StartupBinding,verify_startup

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')

def launch(api,binding,code='pass',extra=()):
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONPATH=str(Path(__import__('compertum').__file__).resolve().parent.parent))
 binding.apply(env)
 info=create_suspended(api,[sys.executable,'-B',*extra,'-c',code],env,binding.parent)
 return OwnedHandle(api,info.process),OwnedHandle(api,info.thread)

def close(api,process,thread):
 api.TerminateProcess(process.get(),125);assert api.WaitForSingleObject(process.get(),3000)==0
 thread.close();process.close()

def test_observes_actual_suspended_image_and_holds_it_against_writes(tmp_path):
 api=JobAPI()
 with StartupBinding(api,tmp_path) as binding:
  process,thread=launch(api,binding)
  try:
   result=binding.observe(process)
   assert result['image_sha256']==hashlib.sha256(Path(sys._base_executable).read_bytes()).hexdigest()
   assert result['plan_sha256']==hashlib.sha256(binding.raw).hexdigest()
   assert result['file_id'] and result['volume_serial']
   with pytest.raises(RuntimeRefused):
    with api.open_file(sys._base_executable,0x40000000,7):pass
   binding.before_resume(process)
  finally:close(api,process,thread)
 assert binding.image.closed

@pytest.mark.parametrize('kind',['directory','file','dangling_link'])
def test_prefix_collision_after_creation_refuses_before_resume(tmp_path,kind):
 api=JobAPI()
 with StartupBinding(api,tmp_path) as binding:
  process,thread=launch(api,binding)
  try:
   if kind=='directory':binding.prefix.mkdir()
   elif kind=='file':binding.prefix.write_bytes(b'x')
   else:binding.prefix.symlink_to(tmp_path/'missing',target_is_directory=True)
   with pytest.raises(RuntimeRefused,match='STARTUP_CACHE_UNVERIFIED'):binding.before_resume(process)
  finally:close(api,process,thread)

def test_same_bytes_at_different_image_identity_are_rejected(tmp_path):
 api=JobAPI();copy=tmp_path/'different-python.exe';shutil.copyfile(sys._base_executable,copy)
 with StartupBinding(api,tmp_path) as binding:
  original=api.CreateProcessW
  def swapped(application,*args):return original(str(copy),*args)
  api.CreateProcessW=swapped
  process,thread=launch(api,binding)
  try:
   with pytest.raises(RuntimeRefused,match='STARTUP_IMAGE_UNVERIFIED'):binding.observe(process)
  finally:close(api,process,thread)

@pytest.mark.parametrize('override',['none','override_prefix','remove_setting','no_user_site','allow_cache_write'])
def test_actual_python_startup_values_are_checked(tmp_path,override):
 api=JobAPI();out=tmp_path/'observed.json'
 code="from compertum.runtime.startup import verify_startup; import pathlib,json; value=verify_startup(); pathlib.Path("+repr(str(out))+").write_text(json.dumps(value))"
 with StartupBinding(api,tmp_path) as binding:
  original=binding.apply
  def changed(env):
   original(env)
   if override=='remove_setting':env.pop('PYTHONPYCACHEPREFIX')
   if override=='no_user_site':env.pop('PYTHONNOUSERSITE')
   if override=='allow_cache_write':env.pop('PYTHONDONTWRITEBYTECODE')
  binding.apply=changed
  extra=['-X','pycache_prefix='+str(tmp_path/'override')] if override=='override_prefix' else []
  if override=='allow_cache_write':code='import sys; sys.dont_write_bytecode=False; '+code
  process,thread=launch(api,binding,code,extra)
  try:
   binding.before_resume(process);assert api.ResumeThread(thread.get())==1
   assert api.WaitForSingleObject(process.get(),15000)==0
   code_value=c.c_uint32();api.checked(api.GetExitCodeProcess(process.get(),c.byref(code_value)),'Exit')
   assert (code_value.value==0)==(override=='none')
   assert out.exists()==(override=='none')
   if out.exists():assert json.loads(out.read_text())['plan_sha256']==hashlib.sha256(binding.raw).hexdigest()
  finally:close(api,process,thread)

def test_each_binding_has_a_fresh_prefix_even_after_abandoned_launch(tmp_path):
 api=JobAPI()
 with StartupBinding(api,tmp_path) as first:
  previous=first.prefix;assert not previous.exists()
 with StartupBinding(api,tmp_path) as second:assert second.prefix!=previous and not second.prefix.exists()

def test_unbound_interpreter_cannot_claim_startup_proof(monkeypatch):
 monkeypatch.delenv('COMPERTUM_STARTUP',raising=False)
 with pytest.raises(RuntimeRefused,match='STARTUP_CONTRACT_UNVERIFIED'):verify_startup()

def test_old_valid_bytecode_is_ignored_only_with_fresh_prefix(tmp_path):
 import py_compile
 module=tmp_path/'sample_cache.py';module.write_text("value='cache'\n");stamp=module.stat()
 py_compile.compile(str(module),doraise=True)
 module.write_text("value='fresh'\n");os.utime(module,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
 api=JobAPI();values=[]
 for isolated in (False,True):
  out=tmp_path/('isolated.json' if isolated else 'control.json')
  with StartupBinding(api,tmp_path) as binding:
   apply=binding.apply
   if not isolated:
    def diagnostic(env):apply(env);env.pop('PYTHONPYCACHEPREFIX')
    binding.apply=diagnostic
   code="import sys; sys.path.insert(0,"+repr(str(tmp_path))+"); import sample_cache; from pathlib import Path; Path("+repr(str(out))+").write_text(sample_cache.value)"
   process,thread=launch(api,binding,code)
   try:
    binding.before_resume(process);api.ResumeThread(thread.get());assert api.WaitForSingleObject(process.get(),15000)==0
    values.append(out.read_text())
   finally:close(api,process,thread)
 assert values==['cache','fresh']

def test_preexisting_prefix_refuses_before_creating_a_process(tmp_path,monkeypatch):
 import compertum.runtime.startup as module
 from uuid import UUID
 token=UUID('11111111-1111-4111-8111-111111111111')
 (tmp_path/('.python-cache-'+str(token))).mkdir()
 monkeypatch.setattr(module,'uuid4',lambda:token)
 with pytest.raises(RuntimeRefused,match='STARTUP_CACHE_UNVERIFIED'):StartupBinding(JobAPI(),tmp_path)
