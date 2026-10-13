"""Compact observed-startup framing. Native receipt matching grants authority."""
import re
from compertum.data.errors import DataError
from compertum.data.encoding import canonical


def validate_proof(value):
    if (type(value) is not dict or set(value)!={'schema','pid','plan_sha256'} or value['schema']!='observed-python-startup-v1'
            or type(value['pid']) is not int or not 0<value['pid']<2**32 or type(value['plan_sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}',value['plan_sha256']) is None or len(canonical(value))>256):
        raise DataError('STARTUP_PROOF_UNVERIFIED')
    return dict(value)


def expected_proof(native):
    if native is None:return None
    from .job_identity import validate_execution_identity
    validate_execution_identity(native)
    if native['schema']=='native-template-execution-v1':return None
    return validate_proof({'schema':'observed-python-startup-v1','pid':native['process']['pid'],'plan_sha256':native['startup']['plan_sha256']})


def outcome_proof(state,index):
    attempts=[a for a in state['attempts'] if a['unit']==index]
    return expected_proof(attempts[-1].get('native_execution')) if attempts else None


def check_report(value,fields,native):
    proof=expected_proof(native)
    from .campaign_environment import observed_from_native,validate_observed
    environment=observed_from_native(native)
    schema='synthetic-native-unit-audit-v2' if proof is not None else 'synthetic-native-unit-audit-v1'
    if proof is not None:validate_proof(value.get('startup'))
    if environment is not None:
        schema='synthetic-native-unit-audit-v3';validate_observed(value.get('environment'))
        if value['environment']!=environment:raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED')
    if (set(value)!=fields|({'startup'} if proof is not None else set())|({'environment'} if environment is not None else set()) or value['schema']!=schema
            or proof is not None and canonical(value['startup'])!=canonical(proof)):raise DataError('STARTUP_PROOF_UNVERIFIED')
