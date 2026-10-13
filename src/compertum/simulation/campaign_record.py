"""Explicit campaign unit framing; artifacts and payloads have distinct hashes."""
from dataclasses import asdict
import hashlib,json,re
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.campaign_contract import UNITS
from compertum.campaign_contract import variant
from compertum.runtime.startup_record import validate_proof
from compertum.runtime.campaign_environment import validate_observed
_UNCHECKED=object()


def _unit(index,dependency):
    if type(index) is not int or not 0<=index<len(UNITS):raise DataError('CAMPAIGN_UNIT_INVALID')
    unit=UNITS[index]
    if (unit.fit_unit is None and dependency is not None) or (unit.fit_unit is not None and (not isinstance(dependency,str) or re.fullmatch('[0-9a-f]{64}',dependency) is None)):
        raise DataError('CAMPAIGN_DEPENDENCY_INVALID')
    return unit


def _body(raw,unit):
    value=json.loads(raw)
    if canonical(value)!=raw or value['financial_accepted'] is not False or type(value['year']) is not int or value['year']!=unit.year:raise DataError('RUN_ARTIFACT_CORRUPT')
    if unit.phase=='fit':
        if value['schema']!='synthetic-fit-checkpoint-v1' or value['candidate_id']!=unit.candidate_id:raise DataError('RUN_ARTIFACT_CORRUPT')
    elif value['schema']!='synthetic-candidate-fold-v1' or value['candidate']!=asdict(variant(unit.candidate_id)) or value['full_M2'] is not False:raise DataError('RUN_ARTIFACT_CORRUPT')
    if value['status']!='SYNTHETIC_ENGINEERING':raise DataError('RUN_ARTIFACT_CORRUPT')
    return value


def pack_result(raw,input_sha256,index,dependency_sha256=None,*,startup=None,environment=None):
    unit=_unit(index,dependency_sha256);_body(raw,unit)
    header={'format':'compertum-campaign-unit-v1','unit':index,**asdict(unit),'input_sha256':input_sha256,
        'dependency_sha256':dependency_sha256,'financial_accepted':False,'payload_sha256':hashlib.sha256(raw).hexdigest(),'payload_bytes':len(raw)}
    if startup is not None:header.update(format='compertum-campaign-unit-v2',startup=validate_proof(startup))
    if environment is not None:
        if startup is None:raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED')
        header.update(format='compertum-campaign-unit-v3',environment=validate_observed(environment))
    result=canonical(header)+b'\n'+raw
    if len(result)>16*1024**2:raise DataError('OUTPUT_BOUND')
    return result


def verify_result(raw,input_sha256,index,dependency_sha256=None,*,expected_startup=_UNCHECKED,expected_environment=_UNCHECKED):
    try:
        if not isinstance(raw,bytes) or not 0<len(raw)<=16*1024**2:raise DataError('RUN_ARTIFACT_CORRUPT')
        boundary=raw.index(b'\n',0,4096);body=raw[boundary+1:]
        header=json.loads(raw[:boundary]);startup=header.get('startup') if expected_startup is _UNCHECKED else expected_startup
        environment=header.get('environment') if expected_environment is _UNCHECKED else expected_environment
        if pack_result(body,input_sha256,index,dependency_sha256,startup=startup,environment=environment)!=raw:raise DataError('RUN_ARTIFACT_CORRUPT')
        return body
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):raise DataError('RUN_ARTIFACT_CORRUPT') from None
