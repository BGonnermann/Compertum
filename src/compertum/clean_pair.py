"""Pure preregistered pair and campaign-envelope contracts; no owner authority."""
from dataclasses import dataclass
import hashlib,json,re
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import identifier,digest,identity,fixed_definition
from compertum import environment_manifest as environment

MAX_PAIR_BYTES=8192
MAX_CAMPAIGN_BYTES=20*1024**2
COMPARISON={'inputs':'EXACT_COMMON_MATHEMATICAL_BYTES','outcomes':'ALL_63_WITH_EXPLICIT_FAILURES_AND_SKIPS','payloads':'EXACT_DETERMINISTIC_MATH_BODIES','histories':'RETAIN_DISTINCT_NATIVE_PROVENANCE','matching_failures':'REMAIN_FAILED','admission':'COMMITTED_BEFORE_EITHER_RUN_EXISTS'}
PAIR_FIELDS={'schema','project_id','pair_id','mathematical_sha256','data_manifest_sha256','holdout_manifest_sha256','definition_sha256','shared_sha256','runtime','source','wheel','comparison'}
MEMBER_FIELDS={'run_id','seal_id','environment_id','manifest_sha256','origins_sha256','prefix','package_root'}

@dataclass(frozen=True)
class PairRecord:
    content:bytes
    sha256:str


def _check(ok):
    if not ok:raise DataError('CLEAN_PAIR_UNVERIFIED')
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _path_key(value):return str(environment._absolute(value)).casefold()
def _shared(value):
    base={**value['executables'][1],'path':_path_key(value['executables'][1]['path'])}
    return _sha(canonical({'runtime':value['runtime'],'dependencies':value['dependencies'],
        'source_archive':{k:value['source_archive'][k] for k in ('sha256','size_bytes')},
        'project_payload':value['project_payload'],'base_executable':base,
        'base_prefix':_path_key(value['origins']['base_prefix'])}))


def read_pair(raw,*,expected_sha256):
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAX_PAIR_BYTES and _sha(raw)==digest(expected_sha256))
        value=json.loads(raw);_check(canonical(value)==raw and set(value)==PAIR_FIELDS and value['schema']=='synthetic-clean-pair-v1')
        digest(value['project_id']);identifier(value['pair_id']);identity(value['runtime'])
        for key in ('mathematical_sha256','data_manifest_sha256','holdout_manifest_sha256','definition_sha256','shared_sha256'):digest(value[key])
        _check(value['definition_sha256']==_sha(canonical(fixed_definition())) and canonical(value['comparison'])==canonical(COMPARISON))
        for lane in ('source','wheel'):
            member=value[lane];_check(type(member) is dict and set(member)==MEMBER_FIELDS)
            identifier(member['run_id']);identifier(member['seal_id']);digest(member['manifest_sha256']);digest(member['origins_sha256'])
            for key in ('prefix','package_root'):_check(member[key]==_path_key(member[key]))
            _check(type(member['environment_id']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,95}',member['environment_id']))
        _check(len({value[l][k] for l in ('source','wheel') for k in ('run_id','seal_id')})==4)
        _check(value['source']['environment_id']!=value['wheel']['environment_id'] and value['source']['manifest_sha256']!=value['wheel']['manifest_sha256'] and value['source']['origins_sha256']!=value['wheel']['origins_sha256'])
        _check(all(value['source'][key]!=value['wheel'][key] for key in ('prefix','package_root')))
        return value
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('CLEAN_PAIR_UNVERIFIED') from None


def build_pair(*,project_id,pair_id,mathematical_sha256,data_manifest_sha256,holdout_manifest_sha256,source,wheel,source_run_id,source_seal_id,wheel_run_id,wheel_seal_id):
    """Freeze two validated expectations; registration requires the owner ledger."""
    values={};records={}
    for lane,record,run,seal in [('source',source,source_run_id,source_seal_id),('wheel',wheel,wheel_run_id,wheel_seal_id)]:
        _check(type(record) is environment.EnvironmentManifest)
        value=environment.read_manifest(record.content,expected_sha256=record.sha256);_check(value['lane']==lane);values[lane]=value
        records[lane]={'run_id':identifier(run),'seal_id':identifier(seal),'environment_id':value['environment_id'],'manifest_sha256':record.sha256,'origins_sha256':_sha(canonical(value['origins'])),**{key:_path_key(value['origins'][key]) for key in ('prefix','package_root')}}
    a,b=values['source'],values['wheel']
    _check(_shared(a)==_shared(b))
    value={'schema':'synthetic-clean-pair-v1','project_id':digest(project_id),'pair_id':identifier(pair_id),'mathematical_sha256':digest(mathematical_sha256),'data_manifest_sha256':digest(data_manifest_sha256),'holdout_manifest_sha256':digest(holdout_manifest_sha256),'definition_sha256':_sha(canonical(fixed_definition())),'shared_sha256':_shared(a),'runtime':a['runtime'],'source':records['source'],'wheel':records['wheel'],'comparison':COMPARISON}
    raw=canonical(value);pin=_sha(raw);read_pair(raw,expected_sha256=pin);return PairRecord(raw,pin)


def check_environment(pair,manifest,*,lane):
    _check(lane in {'source','wheel'} and type(pair) is PairRecord and type(manifest) is environment.EnvironmentManifest)
    value=read_pair(pair.content,expected_sha256=pair.sha256);observed=environment.read_manifest(manifest.content,expected_sha256=manifest.sha256);member=value[lane]
    _check(observed['lane']==lane and observed['environment_id']==member['environment_id'] and manifest.sha256==member['manifest_sha256'] and _sha(canonical(observed['origins']))==member['origins_sha256'] and canonical(observed['runtime'])==canonical(value['runtime']))
    _check(_shared(observed)==value['shared_sha256'] and all(_path_key(observed['origins'][key])==member[key] for key in ('prefix','package_root')))
    return value,observed


def attach_environment(mathematical,*,pair,manifest,lane):
    """Versioned transport preserves every byte of the registered math input."""
    try:
        value,observed=check_environment(pair,manifest,lane=lane)
        _check(type(mathematical) is bytes and 0<len(mathematical)<=MAX_CAMPAIGN_BYTES and _sha(mathematical)==value['mathematical_sha256'])
        body=json.loads(mathematical);_check(canonical(body)==mathematical and body['schema']=='synthetic-campaign-v1' and body['input_kind']=='synthetic-campaign' and body['financial_accepted'] is False)
        _check('environment' not in body and 'clean_pair' not in body and canonical(body['identity'])==canonical(value['runtime']))
        _check(type(body['maximum_bytes']) is int and 0<body['maximum_bytes']<=128*1024**2)
        raw=canonical({**body,'schema':'synthetic-campaign-v2','environment':observed,'clean_pair':{'record':value,'sha256':pair.sha256,'lane':lane}})
        _check(len(raw)<=MAX_CAMPAIGN_BYTES and len(raw)<=body['maximum_bytes']);return raw
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('CLEAN_PAIR_UNVERIFIED') from None


def detach_environment(raw,*,expected_sha256):
    """Structural decoding only; native/owner expected pins remain compulsory."""
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAX_CAMPAIGN_BYTES and _sha(raw)==digest(expected_sha256))
        body=json.loads(raw);_check(canonical(body)==raw and body['schema']=='synthetic-campaign-v2')
        binding=body.pop('clean_pair');observed=body.pop('environment');body['schema']='synthetic-campaign-v1'
        _check(type(binding) is dict and set(binding)=={'record','sha256','lane'})
        pair_raw=canonical(binding['record']);pair=PairRecord(pair_raw,binding['sha256']);read_pair(pair_raw,expected_sha256=pair.sha256)
        manifest=environment.build_manifest(observed);mathematical=canonical(body)
        _check(attach_environment(mathematical,pair=pair,manifest=manifest,lane=binding['lane'])==raw)
        return mathematical,pair,manifest,binding['lane']
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('CLEAN_PAIR_UNVERIFIED') from None
