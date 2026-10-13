"""Protocol pins are strict and definitions agree with the actual engine."""
from dataclasses import asdict
import hashlib
import json
import subprocess
import sys
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import build_protocol,read_protocol,fixed_definition,MAX_PROTOCOL_BYTES


def arguments():
    return dict(development_run_id='00000000-0000-4000-8000-000000000001',development_sha256='a'*64,
        data_manifest_sha256='b'*64,holdout_manifest_sha256='c'*64,
        runtime={'package_sha256':'d'*64,'lock_sha256':'e'*64,'python':'3.14.7','distributions':[['numpy','2.4.3']]})


def test_fixed_roundtrip_and_no_authority():
    result=build_protocol(**arguments());value=read_protocol(result.content,expected_sha256=result.sha256)
    assert result==build_protocol(**arguments()) and len(result.content)<MAX_PROTOCOL_BYTES
    assert value['financial_accepted'] is False and value['full_M3'] is False
    assert value['definition']['data']['real_protected_access'] is False
    assert value['definition']['qualification']['historical_minimum_sessions']==400
    assert value['definition']['qualification']['forward']['halves']==[126,126]
    assert value['definition']['selection']['retain_all_trials']==12


def test_model_and_feature_contract_matches_engine():
    from compertum.modeling.registry import FEATURES,VARIANTS
    from compertum.modeling.campaign import SEEDS
    from compertum.modeling.ridge import _estimators
    from compertum.simulation.market import WATCHLIST
    d=fixed_definition()
    assert d['features']==list(FEATURES) and d['universe']==list(WATCHLIST)
    assert d['registered_family']==[asdict(v) for v in VARIANTS] and d['seeds']==SEEDS
    for a,expected in zip((1,10,100),d['models']['ridge']):
        scaler,ridge=_estimators(a)
        assert scaler.get_params()==d['models']['standard_scaler'] and ridge.get_params()==expected


def test_lightweight_import_does_not_load_numerics():
    code="import sys; from compertum.evaluation_protocol import fixed_definition; fixed_definition(); assert not any(k in sys.modules for k in ('numpy','pandas','sklearn','exchange_calendars')); print('LIGHTWEIGHT')"
    result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=10)
    assert result.returncode==0 and result.stdout.strip()=='LIGHTWEIGHT'


@pytest.mark.parametrize('field',['development_run_id','development_sha256','data_manifest_sha256','holdout_manifest_sha256'])
def test_changed_pin_has_new_identity(field):
    first=arguments();changed={**first,field:str(uuid4()) if field.endswith('id') else 'f'*64}
    assert build_protocol(**first).sha256!=build_protocol(**changed).sha256


@pytest.mark.parametrize('field',['package_sha256','lock_sha256','distributions'])
def test_changed_runtime_has_new_identity(field):
    first=arguments();other=arguments();other['runtime'][field]=[['numpy','2.4.4']] if field=='distributions' else 'f'*64
    assert build_protocol(**first).sha256!=build_protocol(**other).sha256


@pytest.mark.parametrize('bad',[None,False,1,'A'*64,'x'*64,'a'*63,'a'*65])
def test_malformed_digest_refused(bad):
    args=arguments();args['development_sha256']=bad
    with pytest.raises(DataError,match='PROTOCOL_PIN_INVALID'):build_protocol(**args)


@pytest.mark.parametrize('bad',[None,False,1,'bad','00000000-0000-0000-0000-000000000000','{00000000-0000-4000-8000-000000000001}'])
def test_malformed_id_refused(bad):
    args=arguments();args['development_run_id']=bad
    with pytest.raises(DataError,match='PROTOCOL_ID_INVALID'):build_protocol(**args)


@pytest.mark.parametrize('versions',[[],[['numpy','2'],['NumPy','2']],[['b','1'],['a','1']],[['n','x y']],[['n']],[['n',False]]])
def test_invalid_package_list_refused(versions):
    args=arguments();args['runtime']['distributions']=versions
    with pytest.raises(DataError,match='PROTOCOL_ENVIRONMENT_INVALID'):build_protocol(**args)


@pytest.mark.parametrize('field',['universe','features','seeds','selection','numeric','qualification','fits','portfolio','time','data','metrics','models','lifecycle','family_size'])
def test_changed_definition_cannot_be_rehashed_into_valid_protocol(field):
    result=build_protocol(**arguments());value=json.loads(result.content);value['definition'][field]=None
    raw=canonical(value)
    with pytest.raises(DataError,match='PROTOCOL_DEFINITION_CHANGED'):read_protocol(raw,expected_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('mutation',['duplicate','whitespace','extra','authority','missing','wrong_hash','large','not_bytes'])
def test_noncanonical_corrupt_and_authority_forms_denied(mutation):
    result=build_protocol(**arguments());raw=result.content;value=json.loads(raw)
    if mutation=='duplicate':raw=b'{"schema":"synthetic-protocol-v1",'+raw[1:]
    elif mutation=='whitespace':raw=b' '+raw
    elif mutation=='extra':value['extra']=True;raw=canonical(value)
    elif mutation=='authority':value['financial_accepted']=True;raw=canonical(value)
    elif mutation=='missing':del value['runtime'];raw=canonical(value)
    elif mutation=='large':raw=b' '*(MAX_PROTOCOL_BYTES+1)
    elif mutation=='not_bytes':raw=bytearray(raw)
    expected='f'*64 if mutation=='wrong_hash' else hashlib.sha256(raw).hexdigest()
    with pytest.raises(DataError):read_protocol(raw,expected_sha256=expected)


def test_returned_definition_cannot_mutate_later_seal():
    original=build_protocol(**arguments());d=fixed_definition();d['qualification']['sharpe_minimum']='0'
    assert build_protocol(**arguments())==original


def test_owner_contract_import_and_runtime_pins_stay_lightweight():
    code="import sys; from compertum.evaluation_seals import EvaluationSeals; from compertum.runtime.identity_pins import runtime_identity; v=runtime_identity(); assert len(v['package_sha256'])==64; assert not any(k in sys.modules for k in ('numpy','pandas','sklearn','exchange_calendars')); print('LIGHTWEIGHT_OWNER')"
    result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=10)
    assert result.returncode==0 and result.stdout.strip()=='LIGHTWEIGHT_OWNER'


def test_extracted_identity_preserves_existing_package_hash():
    from compertum.runtime.identity_pins import runtime_identity
    from compertum.recovery import _package_hash
    from compertum.simulation.runs import runtime_identity as saved_identity
    assert runtime_identity()['package_sha256']==_package_hash()
    assert runtime_identity()==saved_identity()
