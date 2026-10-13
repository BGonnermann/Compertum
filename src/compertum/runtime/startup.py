"""Observed native launch facts, not preregistered campaign authority.

The expected image is held against replacement before CreateProcess and through
Resume. Python checks its actual startup state before numerical worker imports.
"""
import ctypes as c
import hashlib,json,os,sys
from pathlib import Path
from uuid import uuid4,UUID
from ._windows import DWORD
from .errors import RuntimeRefused

_FIELDS={'schema','token','cache_prefix','executable','base_executable','prefix','base_prefix','package_root'}

def _canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')

def _absent(path):
    if os.path.lexists(path):raise RuntimeRefused('STARTUP_CACHE_UNVERIFIED')

def _read_plan(raw):
    try:
        if type(raw) is not bytes or not 0<len(raw)<=4096:raise ValueError()
        value=json.loads(raw)
        if type(value) is not dict or value.get('schema') not in {'native-python-startup-v1','native-python-startup-v2','native-python-auditor-startup-v1'} or _canonical(value)!=raw:raise ValueError()
        clean=value['schema']=='native-python-startup-v2';auditor=value['schema']=='native-python-auditor-startup-v1'
        if set(value)!=_FIELDS|({'clean_environment'} if clean else set())|({'auditor_environment'} if auditor else set()):raise ValueError()
        if clean:
            from .campaign_environment import validate_expected
            validate_expected(value['clean_environment'])
        if auditor:
            from .auditor_environment import validate_expected
            validate_expected(value['auditor_environment'])
        if type(value['token']) is not str or str(UUID(value['token']))!=value['token']:raise ValueError()
        for key in _FIELDS-{'schema','token'}:
            if type(value[key]) is not str or not 0<len(value[key])<=2048 or '\0' in value[key] or not Path(value[key]).is_absolute():raise ValueError()
        if Path(value['cache_prefix']).name!='.python-cache-'+value['token']:raise ValueError()
        return value
    except (ValueError,TypeError,KeyError,RecursionError):raise RuntimeRefused('STARTUP_CONTRACT_UNVERIFIED') from None

class StartupBinding:
    def __init__(self,api,parent,*,clean_environment=None,auditor_environment=None):
        if clean_environment is not None and auditor_environment is not None:raise RuntimeRefused('STARTUP_CONTRACT_UNVERIFIED')
        self.api=api;self.image=None;self.directory=None;self.parent=Path(parent).resolve(strict=True)
        try:
            self.directory=api.open_directory(self.parent)
            self.image=api.open_file(Path(sys._base_executable).resolve(strict=True),0x80000000,1)
            info=api.file_info(self.image);size=info.size_hi<<32|info.size_lo
            if info.attributes&(0x400|0x10) or not 0<size<=16*1024**2:raise RuntimeRefused('STARTUP_IMAGE_UNVERIFIED')
            self.file_identity=api.file_identity(self.image);self.application=api.final_path(self.image)
            digest=hashlib.sha256();remaining=size
            while remaining:
                n=DWORD();buffer=c.create_string_buffer(min(1024**2,remaining))
                api.checked(api.ReadFile(self.image.get(),buffer,len(buffer),c.byref(n),None),'StartupReadImage')
                if not 0<n.value<=remaining:raise RuntimeRefused('STARTUP_IMAGE_UNVERIFIED')
                digest.update(buffer.raw[:n.value]);remaining-=n.value
            self.image_sha256=digest.hexdigest();token=str(uuid4())
            value={'schema':'native-python-startup-v1','token':token,'cache_prefix':str(self.parent/('.python-cache-'+token)),
                   'executable':str(Path(sys.executable).resolve(strict=True)),'base_executable':str(self.application),
                   'prefix':str(Path(sys.prefix).resolve(strict=True)),'base_prefix':str(Path(sys.base_prefix).resolve(strict=True)),
                   'package_root':str(Path(__file__).resolve().parents[1])}
            if clean_environment is not None:value.update(schema='native-python-startup-v2',clean_environment=clean_environment)
            if auditor_environment is not None:value.update(schema='native-python-auditor-startup-v1',auditor_environment=auditor_environment)
            self._raw=_canonical(value);_read_plan(self._raw);_absent(self.prefix)
        except BaseException:self.close();raise

    @property
    def raw(self):return self._raw
    @property
    def prefix(self):return Path(_read_plan(self.raw)['cache_prefix'])

    def apply(self,env):
        _absent(self.prefix)
        env.update(COMPERTUM_STARTUP=self.raw.decode('utf-8'),PYTHONPYCACHEPREFIX=str(self.prefix),
                   PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')

    def observe(self,process):
        actual=self.api.process_image_path(process)
        with self.api.open_file(actual,0x80000000,1) as image:
            info=self.api.file_info(image)
            if (info.attributes&(0x400|0x10) or self.api.file_identity(image)!=self.file_identity
                    or self.api.final_path(image)!=self.application):raise RuntimeRefused('STARTUP_IMAGE_UNVERIFIED')
        if self.api.WaitForSingleObject(process.get(),0)!=258:raise RuntimeRefused('STARTUP_IMAGE_UNVERIFIED')
        return {'image_sha256':self.image_sha256,'volume_serial':self.file_identity[0],'file_id':self.file_identity[1],
                'plan_sha256':hashlib.sha256(self.raw).hexdigest()}

    def before_resume(self,process):
        result=self.observe(process);_absent(self.prefix);return result

    def close(self):
        try:
            if self.image is not None:self.image.close()
        finally:
            if self.directory is not None:self.directory.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def verify_startup():
    raw=os.environ.get('COMPERTUM_STARTUP','').encode('utf-8');plan=_read_plan(raw)
    actual={'cache_prefix':sys.pycache_prefix,'executable':sys.executable,'base_executable':sys._base_executable,
            'prefix':sys.prefix,'base_prefix':sys.base_prefix,'package_root':str(Path(__file__).resolve().parents[1])}
    try:
        if not sys.dont_write_bytecode or sys.flags.no_user_site!=1:raise ValueError()
        if any(type(value) is not str or (Path(value).resolve()!=Path(plan[key]).resolve() if key=='cache_prefix' else not os.path.samefile(value,plan[key])) for key,value in actual.items()):raise ValueError()
    except (ValueError,OSError):raise RuntimeRefused('STARTUP_STATE_UNVERIFIED') from None
    _absent(Path(plan['cache_prefix']))
    return {'schema':'observed-python-startup-v1','pid':os.getpid(),'plan_sha256':hashlib.sha256(raw).hexdigest()}


def require_entrypoint_startup():
    # Fixed entrypoints fail before their heavy imports; pure imported functions
    # remain available to portable tests without manufacturing native proof.
    try:return verify_startup()
    except (RuntimeRefused,OSError):raise SystemExit(6) from None



def expected_clean_environment(proof):
    from .startup_record import validate_proof
    from compertum.data.errors import DataError
    validate_proof(proof)
    raw=os.environ.get('COMPERTUM_STARTUP','').encode('utf-8')
    if proof['pid']!=os.getpid() or hashlib.sha256(raw).hexdigest()!=proof['plan_sha256']:raise DataError('STARTUP_PROOF_UNVERIFIED')
    plan=_read_plan(raw)
    if 'auditor_environment' in plan:raise DataError('STARTUP_PROOF_UNVERIFIED')
    return plan.get('clean_environment')



def expected_auditor_environment(proof):
    from .startup_record import validate_proof
    from compertum.data.errors import DataError
    validate_proof(proof)
    raw=os.environ.get('COMPERTUM_STARTUP','').encode('utf-8')
    if proof['pid']!=os.getpid() or hashlib.sha256(raw).hexdigest()!=proof['plan_sha256']:raise DataError('STARTUP_PROOF_UNVERIFIED')
    plan=_read_plan(raw)
    if plan['schema']!='native-python-auditor-startup-v1':raise DataError('STARTUP_PROOF_UNVERIFIED')
    return dict(plan['auditor_environment'])
