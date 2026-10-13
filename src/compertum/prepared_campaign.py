"""Lightweight prepared-input checks; calendar and numerical validation stay in workers."""
from dataclasses import asdict
import hashlib,json,re
from .campaign_contract import UNITS,YEARS,SEEDS
from .clean_pair import detach_environment
from .data.encoding import canonical
from .data.errors import DataError
from .data.snapshot_text import safe_text
from .evaluation_protocol import fixed_definition,identity as check_identity,digest


def _check(ok):
    if not ok:raise DataError('PREPARED_CAMPAIGN_UNVERIFIED')


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def read_prepared(raw,*,expected_sha256,identity):
    """Check canonical transport, fixed trial metadata and synthetic scope only."""
    try:
        mathematical,pair,manifest,lane=detach_environment(raw,expected_sha256=expected_sha256)
        value=json.loads(mathematical);_check(value['identity']==check_identity(identity))
        folds=value['folds'];_check(type(folds) is list and len(folds)==3)
        for fold,year in zip(folds,YEARS):
            _check(type(fold) is dict and set(fold)=={'year','training_start','training_end','start','end','scoring_as_of','snapshots','sectors','market_sha256'})
            _check(type(fold['year']) is int and fold['year']==year);digest(fold['market_sha256'])
            for k in ('training_start','training_end','start','end'):
                _check(type(fold[k]) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}',fold[k]) is not None)
            _check('2016-01-01'<=fold['training_start']<=fold['training_end']<str(year)+'-01-01'<=fold['start']<=fold['end']<str(year+1)+'-01-01')
            snapshots=fold['snapshots'];_check(type(snapshots) is list and 1<=len(snapshots)<=64)
            for snapshot in snapshots:
                safe_text(canonical(snapshot))
                _check(type(snapshot) is dict and set(snapshot)=={'schema_version','source','assets','feature_sessions','bars','actions'} and snapshot['schema_version']=='1')
                source=snapshot['source'];_check(type(source) is dict and set(source)=={'provider','feed','vintage','availability_basis','aggregation'})
                _check(source['provider']=='synthetic' and source['feed']=='iex' and source['availability_basis']=='SIMULATED_AVAILABILITY' and source['aggregation']=='PROVIDER_DAILY')
                for k,lower,upper in [('assets',1,13),('feature_sessions',1,256),('bars',1,1024),('actions',0,256)]:
                    _check(type(snapshot[k]) is list and lower<=len(snapshot[k])<=upper)
                dates=snapshot['feature_sessions']+[b['session_date'] for b in snapshot['bars']]
                _check(all(type(d) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}',d) and '2016-01-01'<=d<'2024-01-01' for d in dates))
        protocol=fixed_definition()
        definition={'features':protocol['features'],'universe':protocol['universe'],'registered_family':protocol['registered_family'],
            'cost_bps':[10,20],'seeds':SEEDS,'rng_state':'NO_RANDOM_DRAWS_SVD_DETERMINISTIC',
            'resolved_models':[{'scaler':protocol['models']['standard_scaler'],'ridge':ridge,'dtype':'float64','row_weights':'EQUAL'} for ridge in protocol['models']['ridge']],
            'identity':value['identity'],'fold_pins':[{'year':f['year'],'sha256':_sha(canonical(f))} for f in folds],
            'policy':'SYNTHETIC_PARTIAL_DEVELOPMENT_FOLDS','fit_activation':'SYNTHETIC_FIT_AUDIT_READY_ASSUMPTION'}
        trials=[{'candidate_id':v['candidate_id'],'sha256':_sha(canonical({'candidate':v,'definition':definition}))} for v in protocol['registered_family']]
        expected=dict(schema='synthetic-campaign-v1',input_kind='synthetic-campaign',financial_accepted=False,full_M2=False,
            **definition,folds=folds,trials=trials,units=[asdict(u) for u in UNITS],maximum_bytes=value['maximum_bytes'])
        _check(canonical(expected)==mathematical)
        return json.loads(raw),pair,lane
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('PREPARED_CAMPAIGN_UNVERIFIED') from None
