"""Native template identity records; validation alone grants no authority."""
import hashlib,re
from uuid import UUID
from .identity import PeerObservation
from compertum.data.encoding import canonical
from compertum.data.errors import DataError

_TEMPLATES={'experiment_runner':'compertum.runtime.campaign_worker','experiment_auditor':'compertum.runtime.audit_worker'}
_FIELDS={'schema','process','task_id','role','entrypoint','code_sha256','lock_sha256','task_sha256'}


def _check(value):
    if not value:raise DataError('NATIVE_EXECUTION_IDENTITY_INVALID')


def validate_execution_identity(value):
    """Check only the record contract, never authenticate caller-provided JSON."""
    try:
        _check(type(value) is dict and value.get('schema') in {'native-template-execution-v1','native-template-execution-v2','native-template-execution-v3','native-template-final-auditor-v1'} and len(canonical(value))<=1536)
        modern=value['schema']!='native-template-execution-v1';clean=value['schema']=='native-template-execution-v3';auditor=value['schema']=='native-template-final-auditor-v1'
        _check(set(value)==_FIELDS|({'startup'} if modern else set())|({'clean_environment'} if clean else set())|({'auditor_environment'} if auditor else set()))
        if clean:
            from .campaign_environment import validate_expected
            validate_expected(value['clean_environment'])
        if auditor:
            from .auditor_environment import validate_expected
            validate_expected(value['auditor_environment'])
            _check(value['role']=='experiment_auditor' and value['task_id']==value['auditor_environment']['task_id'])
        if modern:
            startup=value['startup'];_check(type(startup) is dict and set(startup)=={'image_sha256','volume_serial','file_id','plan_sha256'})
            _check(type(startup['volume_serial']) is int and 0<startup['volume_serial']<2**64)
            _check(type(startup['file_id']) is str and re.fullmatch('[0-9a-f]{32}',startup['file_id']) is not None)
            _check(all(type(startup[k]) is str and re.fullmatch('[0-9a-f]{64}',startup[k]) for k in ('image_sha256','plan_sha256')))
        process=value['process'];_check(type(process) is dict and set(process)=={'pid','creation_filetime','operator_sid'})
        _check(type(process['pid']) is int and 0<process['pid']<2**32 and type(process['creation_filetime']) is int and 0<process['creation_filetime']<2**64)
        _check(type(process['operator_sid']) is str and len(process['operator_sid'])<=184 and re.fullmatch(r'S-1-\d+(?:-\d+){1,15}',process['operator_sid']) is not None)
        _check(type(value['task_id']) is str and str(UUID(value['task_id']))==value['task_id'])
        _check(value['role'] in _TEMPLATES and value['entrypoint']==_TEMPLATES[value['role']])
        _check(all(type(value[k]) is str and re.fullmatch('[0-9a-f]{64}',value[k]) for k in ('code_sha256','lock_sha256','task_sha256')))
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError,RecursionError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('NATIVE_EXECUTION_IDENTITY_INVALID') from None


def capture_execution_identity(observation,task,entrypoint,*,startup=None,clean_environment=None,auditor_environment=None):
    """Called by the launcher with its live suspended-child observation."""
    try:
        _check(type(observation) is PeerObservation and type(task) is dict)
        value={'schema':'native-template-execution-v1','process':{'pid':observation.pid,'creation_filetime':observation.creation_filetime,'operator_sid':observation.operator_sid},'task_id':task['task_id'],'role':task['role'],'entrypoint':entrypoint,'code_sha256':task['code_sha256'],'lock_sha256':task['lock_sha256'],'task_sha256':hashlib.sha256(canonical(task)).hexdigest()}
        _check(clean_environment is None or auditor_environment is None)
        if startup is not None:value.update(schema='native-template-execution-v2',startup=dict(startup))
        if clean_environment is not None:
            _check(startup is not None);value.update(schema='native-template-execution-v3',clean_environment=dict(clean_environment))
        if auditor_environment is not None:
            _check(startup is not None);value.update(schema='native-template-final-auditor-v1',auditor_environment=dict(auditor_environment))
        validate_execution_identity(value);return value
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError,RecursionError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('NATIVE_EXECUTION_IDENTITY_INVALID') from None


def same_process(a,b):
    validate_execution_identity(a);validate_execution_identity(b)
    return (a['process']['pid'],a['process']['creation_filetime'])==(b['process']['pid'],b['process']['creation_filetime'])
