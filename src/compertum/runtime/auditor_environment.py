"""Distinct locked-environment binding for an independent consumed-Final audit.

Manifest bytes describe the auditor; only the owner can admit a Final audit.
"""
import re
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import digest,identifier
from compertum import environment_manifest as environment

FIELDS={'schema','manifest_sha256','environment_id','lane','task_id'}


def _check(ok):
    if not ok:raise DataError('AUDITOR_ENVIRONMENT_UNVERIFIED')


def validate_expected(value):
    try:
        _check(type(value) is dict and set(value)==FIELDS and value['schema']=='expected-final-auditor-environment-v1')
        digest(value['manifest_sha256']);identifier(value['task_id'])
        _check(type(value['environment_id']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,95}',value['environment_id']) is not None)
        _check(type(value['lane']) is str and value['lane'] in {'source','wheel'} and len(canonical(value))<=512)
        return dict(value)
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('AUDITOR_ENVIRONMENT_UNVERIFIED') from None


def expected_from_manifest(raw,expected_sha256,task_id):
    value=environment.read_manifest(raw,expected_sha256=expected_sha256)
    return validate_expected(dict(schema='expected-final-auditor-environment-v1',manifest_sha256=expected_sha256,environment_id=value['environment_id'],lane=value['lane'],task_id=task_id))


def verify_input(raw,expected_sha256,*,expected):
    binding=validate_expected(expected)
    _check(canonical(expected_from_manifest(raw,expected_sha256,binding['task_id']))==canonical(binding))
    observed=environment.verify_environment(raw,expected_sha256=binding['manifest_sha256'])
    _check(observed['status']=='ENVIRONMENT_BYTES_VERIFIED' and observed['campaign_admitted'] is False and observed['manifest_sha256']==binding['manifest_sha256'] and observed['lane']==binding['lane'] and observed['environment_id']==binding['environment_id'])
    return {**binding,'schema':'observed-final-auditor-environment-v1'}


def validate_observed(value):
    _check(type(value) is dict and value.get('schema')=='observed-final-auditor-environment-v1')
    validate_expected({**value,'schema':'expected-final-auditor-environment-v1'});return dict(value)


def observed_from_native(native):
    from .job_identity import validate_execution_identity
    validate_execution_identity(native);_check(native['schema']=='native-template-final-auditor-v1')
    return validate_observed({**native['auditor_environment'],'schema':'observed-final-auditor-environment-v1'})
