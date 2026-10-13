"""Compact code and locked environment pins shared by numerical and role owners."""
import hashlib
from importlib.metadata import distributions
from pathlib import Path
import platform
import sysconfig
from compertum.data.errors import DataError


def runtime_identity():
    package=Path(__file__).resolve().parents[1]
    lock=package.parents[1]/'uv.lock'
    if not lock.is_file():lock=Path(sysconfig.get_path('data'))/'share/compertum/uv.lock'
    if not lock.is_file() or lock.stat().st_size>1024**2 or platform.python_version()!='3.14.7':
        raise DataError('RUN_ENVIRONMENT')
    digest=hashlib.sha256()
    for path in sorted(package.rglob('*.py')):
        digest.update(path.relative_to(package).as_posix().encode());digest.update(path.read_bytes())
    versions=sorted({(d.metadata['Name'],d.version) for d in distributions()})
    return {'package_sha256':digest.hexdigest(),'lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),
        'python':platform.python_version(),'distributions':versions}
