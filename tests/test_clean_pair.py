"""Pure pair transport fixtures; native authority is tested by later owner work."""
import copy,hashlib,json
from uuid import uuid4
from pathlib import Path
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from test_environment_manifest import environment
from compertum import environment_manifest as manifest
from compertum import clean_pair as m


def sha(raw):return hashlib.sha256(raw).hexdigest()

@pytest.fixture
def pair_inputs(environment):
    a=environment('source');b=environment('wheel')
    # Pure transport fixture: common immutable payload expectations, distinct origins.
    for key in ('runtime','dependencies','source_archive','project_archive','project_payload'):b[key]=copy.deepcopy(a[key])
    b['origins']['base_prefix']=a['origins']['base_prefix'];b['origins']['base_executable']=a['origins']['base_executable'];b['executables'][1]=copy.deepcopy(a['executables'][1])
    mathematical=canonical({'schema':'synthetic-campaign-v1','input_kind':'synthetic-campaign','financial_accepted':False,'identity':a['runtime'],'maximum_bytes':128*1024**2,'trials':[{'sentinel':'unchanged'}],'folds':[{'sentinel':'unchanged'}]})
    args={'project_id':'c'*64,'pair_id':str(uuid4()),'mathematical_sha256':sha(mathematical),'data_manifest_sha256':'a'*64,'holdout_manifest_sha256':'b'*64,'source':manifest.build_manifest(a),'wheel':manifest.build_manifest(b),'source_run_id':str(uuid4()),'source_seal_id':str(uuid4()),'wheel_run_id':str(uuid4()),'wheel_seal_id':str(uuid4())}
    return args,mathematical


def test_distinct_lane_envelopes_preserve_identical_math_bytes(pair_inputs):
    args,raw=pair_inputs;pair=m.build_pair(**args);frames=[]
    for lane in ('source','wheel'):
        result=m.attach_environment(raw,pair=pair,manifest=args[lane],lane=lane);frames.append(result)
        decoded,p,environment,actual=m.detach_environment(result,expected_sha256=sha(result))
        assert decoded==raw and p==pair and environment==args[lane] and actual==lane
    assert frames[0]!=frames[1] and sha(frames[0])!=sha(frames[1])
    assert json.loads(pair.content)['comparison']['matching_failures']=='REMAIN_FAILED'


@pytest.mark.parametrize('field',['source_run_id','source_seal_id','wheel_seal_id'])
def test_run_and_seal_membership_must_be_distinct(pair_inputs,field):
    args,_=pair_inputs;args[field]=args['wheel_run_id']
    with pytest.raises(DataError):m.build_pair(**args)


@pytest.mark.parametrize('fault',['runtime','dependency','source_archive','base_executable','environment_id'])
def test_cross_lane_common_pins_cannot_diverge(pair_inputs,fault):
    args,_=pair_inputs;v=json.loads(args['wheel'].content)
    if fault=='runtime':v['runtime']['package_sha256']='0'*64
    elif fault=='dependency':v['dependencies'][0]['payload']['archive_sha256']='0'*64
    elif fault=='source_archive':v['source_archive']['sha256']='0'*64
    elif fault=='base_executable':v['executables'][1]['sha256']='0'*64
    else:v['environment_id']=json.loads(args['source'].content)['environment_id']
    args['wheel']=manifest.build_manifest(v)
    with pytest.raises(DataError):m.build_pair(**args)


@pytest.mark.parametrize('fault',['definition','comparison','unknown_field','bad_digest','float_identifier'])
def test_rehashed_pair_cannot_change_contract(pair_inputs,fault):
    args,_=pair_inputs;pair=m.build_pair(**args);v=json.loads(pair.content)
    if fault=='definition':v['definition_sha256']='0'*64
    elif fault=='comparison':v['comparison']['matching_failures']='PASS'
    elif fault=='unknown_field':v['admitted']=True
    elif fault=='bad_digest':v['mathematical_sha256']='bad'
    else:v['source']['run_id']=1.0
    raw=canonical(v)
    with pytest.raises(DataError):m.read_pair(raw,expected_sha256=sha(raw))


@pytest.mark.parametrize('fault',['wrong_lane','changed_manifest','changed_math','extra_binding','lost_manifest','wrong_pair_pin'])
def test_envelope_cannot_relabel_or_strip_pins(pair_inputs,fault):
    args,raw=pair_inputs;pair=m.build_pair(**args);wrapped=m.attach_environment(raw,pair=pair,manifest=args['source'],lane='source');v=json.loads(wrapped)
    if fault=='wrong_lane':v['clean_pair']['lane']='wheel'
    elif fault=='changed_manifest':v['environment']['environment_id']='new-environment'
    elif fault=='changed_math':v['trials'][0]['sentinel']='changed'
    elif fault=='extra_binding':v['clean_pair']['admitted']=True
    elif fault=='lost_manifest':del v['environment']
    else:v['clean_pair']['sha256']='0'*64
    raw=canonical(v)
    with pytest.raises(DataError):m.detach_environment(raw,expected_sha256=sha(raw))


def test_metadata_counts_toward_existing_campaign_bound(pair_inputs,monkeypatch):
    args,raw=pair_inputs;pair=m.build_pair(**args);wrapped=m.attach_environment(raw,pair=pair,manifest=args['source'],lane='source')
    monkeypatch.setattr(m,'MAX_CAMPAIGN_BYTES',len(wrapped)-1)
    with pytest.raises(DataError):m.attach_environment(raw,pair=pair,manifest=args['source'],lane='source')


def test_structural_pair_does_not_claim_registration_or_authority(pair_inputs):
    args,_=pair_inputs;value=json.loads(m.build_pair(**args).content)
    assert not {'admitted','verified','registered','financial_accepted'}.intersection(value)
    assert value['comparison']['admission']=='COMMITTED_BEFORE_EITHER_RUN_EXISTS'

@pytest.mark.parametrize('fault',['dependency','source_archive','base_executable','base_prefix'])
def test_redecoded_lane_cannot_change_shared_pins(pair_inputs,fault):
    args,raw=pair_inputs;pair=m.build_pair(**args)
    wrapped=json.loads(m.attach_environment(raw,pair=pair,manifest=args['wheel'],lane='wheel'))
    v=wrapped['environment']
    if fault=='dependency':v['dependencies'][0]['payload']['archive_sha256']='0'*64
    elif fault=='source_archive':v['source_archive']['sha256']='0'*64
    elif fault=='base_executable':v['executables'][1]['sha256']='0'*64
    else:
        new=str(Path(v['origins']['base_prefix']).parent/'different-python')
        v['origins']['base_prefix']=new;v['origins']['base_executable']=str(Path(new)/'python.exe');v['executables'][1]['path']=v['origins']['base_executable']
    changed=manifest.build_manifest(v)
    member=wrapped['clean_pair']['record']['wheel'];member['manifest_sha256']=changed.sha256;member['origins_sha256']=sha(canonical(v['origins']))
    wrapped['clean_pair']['sha256']=sha(canonical(wrapped['clean_pair']['record']))
    result=canonical(wrapped)
    with pytest.raises(DataError):m.detach_environment(result,expected_sha256=sha(result))


def test_distinct_prefixes_reject_windows_case_alias(pair_inputs):
    args,_=pair_inputs;a=json.loads(args['source'].content);b=json.loads(args['wheel'].content)
    old=b['origins']['prefix'];alias=a['origins']['prefix'].swapcase()
    def replace(value):
        if isinstance(value,str):return value.replace(old,alias)
        if isinstance(value,list):return [replace(v) for v in value]
        if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
        return value
    args['wheel']=manifest.build_manifest(replace(b))
    with pytest.raises(DataError):m.build_pair(**args)


@pytest.mark.parametrize('project',[str(uuid4()),'','g'*64,True])
def test_pair_uses_existing_project_fingerprint_format(pair_inputs,project):
    args,_=pair_inputs;args['project_id']=project
    with pytest.raises(DataError):m.build_pair(**args)
