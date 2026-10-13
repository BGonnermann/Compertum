"""Immutable synthetic annual fits, reusable under a caller-owned expected digest."""
from dataclasses import dataclass
import hashlib,json,re
from compertum.data.calendar import session_times
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.market import load_market,WATCHLIST
from compertum.simulation.policy import fixed_decimal
from .registry import variant,annual_cutoff,FEATURES
from .dataset import assemble_training_rows,DatasetAssembly
from .ridge import FitRows,FitManifest,RidgeArtifact,prepare_fit,fit_ridge,predict

from compertum.simulation.fit_record import FIELDS

@dataclass(frozen=True)
class FitCheckpoint:
    content:bytes
    sha256:str


def _check(condition):
    if not condition:raise DataError('FIT_CHECKPOINT_INVALID')


def _identity(candidate_id,year,start,end):
    c=variant(candidate_id);cutoff=annual_cutoff(year)
    _check(c.kind=='ridge' and type(start) is str and type(end) is str)
    session_times(start);session_times(end)
    _check('2016-01-01'<=start<=end<cutoff.date().isoformat())
    return c


@fixed_decimal
def prepare_fit_checkpoint(chunks,sectors,training_start,training_end,year,candidate_id):
    c=_identity(candidate_id,year,training_start,training_end);market=load_market(chunks,sectors)
    if any(not '2016-01-01'<=day<'2024-01-01' for _,day,_ in market.rows):raise DataError('DEVELOPMENT_PRICES_ONLY')
    assembly=assemble_training_rows(chunks,sectors,training_start,training_end,c.horizon)
    if assembly.rows is None:raise DataError('NO_TRAINING_ROWS')
    manifest=prepare_fit(assembly.rows,year);model=fit_ridge(assembly.rows,manifest,candidate_id)
    value={'schema':'synthetic-fit-checkpoint-v1','status':'SYNTHETIC_ENGINEERING','financial_accepted':False,'candidate_id':candidate_id,'year':year,'training_start':training_start,'training_end':training_end,'source_market_sha256':market.sha256,'dataset_assembly':json.loads(assembly.content),'fit_rows':json.loads(assembly.rows.content),'fit_rows_sha256':assembly.rows.sha256,'fit_manifest':json.loads(manifest.content),'fit_manifest_sha256':manifest.sha256,'model':json.loads(model.content),'model_sha256':model.sha256}
    raw=canonical(value)
    if len(raw)>16*1024**2:raise DataError('OUTPUT_BOUND')
    return FitCheckpoint(raw,hashlib.sha256(raw).hexdigest())


@fixed_decimal
def read_fit_checkpoint(checkpoint,*,expected_sha256,market_sha256,candidate_id,year,training_start,training_end):
    """Verify a trusted pinned artifact's binding without calling any fitter.

    Its trusted caller must obtain expected_sha256 from its committed record,
    not from unchecked input content. Pure hashes do not authenticate an author.
    """
    try:
        c=_identity(candidate_id,year,training_start,training_end)
        _check(type(checkpoint) is FitCheckpoint and type(checkpoint.content) is bytes and 0<len(checkpoint.content)<=16*1024**2)
        _check(type(expected_sha256) is str and hashlib.sha256(checkpoint.content).hexdigest()==checkpoint.sha256==expected_sha256)
        v=json.loads(checkpoint.content);_check(type(v) is dict and set(v)==FIELDS and canonical(v)==checkpoint.content)
        _check(v['schema']=='synthetic-fit-checkpoint-v1' and v['status']=='SYNTHETIC_ENGINEERING' and v['financial_accepted'] is False)
        _check(type(v['year']) is int and (v['candidate_id'],v['year'],v['training_start'],v['training_end'],v['source_market_sha256'])==(candidate_id,year,training_start,training_end,market_sha256))
        rows_raw=canonical(v['fit_rows']);_check(hashlib.sha256(rows_raw).hexdigest()==v['fit_rows_sha256']);rows=FitRows(rows_raw,v['fit_rows_sha256'])
        manifest=prepare_fit(rows,year);_check(manifest.content==canonical(v['fit_manifest']) and manifest.sha256==v['fit_manifest_sha256'])
        _check(v['fit_rows']['horizon']==v['fit_manifest']['horizon']==c.horizon)
        model_raw=canonical(v['model']);_check(hashlib.sha256(model_raw).hexdigest()==v['model_sha256']);model=RidgeArtifact(model_raw,v['model_sha256'])
        _check(v['model']['candidate_id']==candidate_id and v['model']['horizon']==c.horizon and v['model']['bundle_sha256']==rows.sha256 and v['model']['fit_manifest_sha256']==manifest.sha256 and v['model']['fit_cutoff']==annual_cutoff(year).isoformat())
        _check(v['model']['observations']==len(v['fit_manifest']['included']))
        predict(model,[[0.0]*len(FEATURES)],feature_names=FEATURES)
        assembly=v['dataset_assembly']
        _check(assembly['schema']=='synthetic-dataset-assembly-v1' and assembly['status']=='SYNTHETIC_ENGINEERING' and assembly['financial_accepted'] is False and assembly['full_M2'] is False)
        _check((assembly['source_market_sha256'],assembly['start'],assembly['end'],assembly['horizon'],assembly['fit_rows_sha256'])==(market_sha256,training_start,training_end,c.horizon,rows.sha256))
        _check(type(assembly['horizon']) is int and tuple(assembly['feature_order'])==FEATURES and tuple(assembly['frozen_universe'])==WATCHLIST and assembly['availability_basis']=='SIMULATED_AVAILABILITY')
        _check(all(type(assembly[k]) is int for k in ['assembled_rows','expected_rows']))
        _check(assembly['assembled_rows']==len(v['fit_rows']['rows'])==len(assembly['row_provenance']) and assembly['expected_rows']==assembly['assembled_rows']+len(assembly['omissions']))
        dates=[training_start]
        while dates[-1]!=training_end:
            _check(len(dates)<1024);dates.append(session_times(dates[-1]).next_date)
        expected={(s,session_times(d).decision.isoformat()) for d in dates for s in WATCHLIST}
        def identity(row):return row['symbol'],row['decision_at']
        admitted=[identity(r) for r in v['fit_rows']['rows']]
        omitted=[identity(r) for r in assembly['omissions']]
        _check(len(admitted)+len(omitted)==len(expected)==assembly['expected_rows'] and set(admitted+omitted)==expected)
        _check([identity(r) for r in assembly['row_provenance']]==admitted)
        for row,source in zip(v['fit_rows']['rows'],assembly['row_provenance']):
            _check(all(type(source[k]) is str and re.fullmatch('[0-9a-f]{64}',source[k]) is not None for k in ['feature_sha256','label_sha256']))
            _check(source['selected_label_revision_id']==row['label_revision_id']=='label-'+source['label_sha256'] and source['label_available_at']==row['simulated_label_available_at'])
        raw=canonical(assembly);_check(len(raw)<=8*1024**2)
        return DatasetAssembly(raw,hashlib.sha256(raw).hexdigest(),rows),manifest,model
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('FIT_CHECKPOINT_INVALID') from exc
