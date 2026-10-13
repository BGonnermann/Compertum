"""Structural binding for fits already validated by an authenticated worker.

This reader grants no native or mathematical authority. The owner must verify
its committed seal, execution, successful receipt and exact frame first.
"""
import hashlib,json
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.campaign_contract import FEATURES,YEARS,variant

FIELDS={'schema','status','financial_accepted','candidate_id','year','training_start','training_end','source_market_sha256','dataset_assembly','fit_rows','fit_rows_sha256','fit_manifest','fit_manifest_sha256','model','model_sha256'}


def _check(ok):
    if not ok:raise DataError('FIT_CHECKPOINT_INVALID')


def read_binding(raw,*,expected_sha256,market_sha256,candidate_id,year,training_start,training_end):
    try:
        c=variant(candidate_id)
        _check(c.kind=='ridge' and type(year) is int and year in YEARS)
        _check(type(raw) is bytes and 0<len(raw)<=16*1024**2 and hashlib.sha256(raw).hexdigest()==expected_sha256)
        v=json.loads(raw);_check(type(v) is dict and set(v)==FIELDS and canonical(v)==raw)
        _check(v['schema']=='synthetic-fit-checkpoint-v1' and v['status']=='SYNTHETIC_ENGINEERING' and v['financial_accepted'] is False)
        _check(type(v['year']) is int and (v['candidate_id'],v['year'],v['training_start'],v['training_end'],v['source_market_sha256'])==(candidate_id,year,training_start,training_end,market_sha256))
        for field in ('fit_rows','fit_manifest','model'):
            _check(type(v[field]) is dict and hashlib.sha256(canonical(v[field])).hexdigest()==v[field+'_sha256'])
        rows,manifest,model,assembly=(v[k] for k in ('fit_rows','fit_manifest','model','dataset_assembly'))
        _check(rows['horizon']==manifest['horizon']==model['horizon']==c.horizon)
        _check(manifest['year']==year and manifest['bundle_sha256']==model['bundle_sha256']==v['fit_rows_sha256'])
        _check(model['candidate_id']==candidate_id and model['fit_manifest_sha256']==v['fit_manifest_sha256'] and model['fit_cutoff']==manifest['cutoff'])
        _check(type(model['observations']) is int and model['observations']==len(manifest['included']))
        _check(all(tuple(item['feature_order'])==FEATURES for item in (rows,manifest,model,assembly)))
        _check(assembly['schema']=='synthetic-dataset-assembly-v1' and assembly['status']=='SYNTHETIC_ENGINEERING' and assembly['financial_accepted'] is False and assembly['full_M2'] is False)
        _check((assembly['source_market_sha256'],assembly['start'],assembly['end'],assembly['horizon'],assembly['fit_rows_sha256'])==(market_sha256,training_start,training_end,c.horizon,v['fit_rows_sha256']))
        _check(assembly['assembled_rows']==len(rows['rows'])==len(assembly['row_provenance']) and assembly['expected_rows']==assembly['assembled_rows']+len(assembly['omissions']))
        return v
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('FIT_CHECKPOINT_INVALID') from None
