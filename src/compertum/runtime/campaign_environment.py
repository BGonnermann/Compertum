"""Verify separately pinned clean inputs before any numerical worker imports.

This byte observation grants no registration or native result authority.
"""
import hashlib,json
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import digest,identifier
from compertum import clean_pair,environment_manifest as environment

MIB=1024**2
EXPECTED_FIELDS={'schema','pair_sha256','manifest_sha256','lane','run_id'}


def _check(ok):
    if not ok:raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED')


def validate_expected(value):
    try:
        _check(type(value) is dict and set(value)==EXPECTED_FIELDS and value['schema']=='expected-clean-campaign-v1')
        digest(value['pair_sha256']);digest(value['manifest_sha256']);identifier(value['run_id'])
        _check(type(value['lane']) is str and value['lane'] in {'source','wheel'} and len(canonical(value))<=512)
        return dict(value)
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED') from None


def verify_input(raw,expected_sha256,*,expected):
    try:
        _check(type(raw) is bytes and 0<len(raw)<=20*MIB and hashlib.sha256(raw).hexdigest()==digest(expected_sha256))
        body=json.loads(raw);_check(type(body) is dict and canonical(body)==raw)
        if body.get('schema')=='synthetic-campaign-v1':
            _check(expected is None and 'environment' not in body and 'clean_pair' not in body)
            return None
        _check(body.get('schema')=='synthetic-campaign-v2');binding=validate_expected(expected)
        _,pair,manifest,lane=clean_pair.detach_environment(raw,expected_sha256=expected_sha256)
        value=json.loads(pair.content)
        _check(pair.sha256==binding['pair_sha256'] and manifest.sha256==binding['manifest_sha256'] and lane==binding['lane'] and value[lane]['run_id']==binding['run_id'])
        observed=environment.verify_environment(manifest.content,expected_sha256=binding['manifest_sha256'])
        _check(observed['status']=='ENVIRONMENT_BYTES_VERIFIED' and observed['campaign_admitted'] is False and observed['manifest_sha256']==binding['manifest_sha256'] and observed['lane']==lane and observed['environment_id']==value[lane]['environment_id'])
        return {**binding,'schema':'observed-clean-environment-v1'}
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED') from None



def validate_observed(value):
    _check(type(value) is dict and value.get('schema')=='observed-clean-environment-v1')
    validate_expected({**value,'schema':'expected-clean-campaign-v1'})
    return dict(value)


def observed_from_native(native):
    if native is None:return None
    from .job_identity import validate_execution_identity
    validate_execution_identity(native)
    _check('auditor_environment' not in native)
    expected=native.get('clean_environment')
    return validate_observed({**expected,'schema':'observed-clean-environment-v1'}) if expected is not None else None


def check_native(native,expected):
    if expected is not None:validate_expected(expected)
    if native is None:
        _check(expected is None);return
    from .job_identity import validate_execution_identity
    validate_execution_identity(native)
    _check('auditor_environment' not in native and native.get('clean_environment')==expected)


def outcome_environment(state,index):
    attempts=[a for a in state['attempts'] if a['unit']==index]
    native=attempts[-1].get('native_execution') if attempts else None
    check_native(native,state.get('clean_environment'))
    return observed_from_native(native)



def expected_from_input(raw,expected_sha256):
    """Decode expected pins from immutable transport; this grants no authority."""
    try:
        _check(type(raw) is bytes and 0<len(raw)<=20*MIB and hashlib.sha256(raw).hexdigest()==digest(expected_sha256))
        body=json.loads(raw);_check(type(body) is dict and canonical(body)==raw)
        if body.get('schema')=='synthetic-campaign-v1':
            _check('environment' not in body and 'clean_pair' not in body);return None
        _,pair,manifest,lane=clean_pair.detach_environment(raw,expected_sha256=expected_sha256)
        value=json.loads(pair.content)
        return validate_expected({'schema':'expected-clean-campaign-v1','pair_sha256':pair.sha256,'manifest_sha256':manifest.sha256,'lane':lane,'run_id':value[lane]['run_id']})
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED') from None


def check_input_state(raw,expected_sha256,state):
    expected=expected_from_input(raw,expected_sha256)
    _check(type(state) is dict and state.get('clean_environment')==expected)
    if expected is not None:_check(state.get('run_id')==expected['run_id'])


def check_attempt_environments(attempts,expected):
    for attempt in attempts:
        native=attempt.get('native_execution')
        if native is not None or attempt['status']=='COMPLETED':check_native(native,expected)
