"""Closed final plan contract shared by owners and workers; no data access."""
import hashlib,json,re
from uuid import UUID,uuid5
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import fixed_definition,identity,identifier
from .final_recipe import recipe_for_pin
from .campaign_contract import variant

def selection(candidate_ids):
    if type(candidate_ids) not in (tuple,list) or not 1<=len(candidate_ids)<=3:
        raise DataError('GENERATED_SELECTION_BOUND')
    candidates=tuple(variant(name) for name in candidate_ids)
    if len({c.horizon for c in candidates})!=len(candidates):raise DataError('GENERATED_SELECTION_BOUND')
    return tuple(sorted(candidates,key=lambda c:c.horizon))


def _require(condition):
    if not condition:raise DataError('GENERATED_FINAL_PLAN_INVALID')


def read_plan(raw,expected_sha256):
    _require(type(raw) is bytes and 0<len(raw)<=32768 and hashlib.sha256(raw).hexdigest()==expected_sha256)
    try:
        v=json.loads(raw)
        _require(type(v) is dict and set(v)==set('schema project_id seal_id evaluation_id checkpoint_id inputs shortlist_ticket_sha256 selected recipe runtime yearly_fits budget checkpoint financial_accepted full_M3'.split()))
        _require(canonical(v)==raw and v['schema']=='synthetic-final-plan-v1' and v['financial_accepted'] is False and v['full_M3'] is False)
        _require(type(v['inputs']) is dict and set(v['inputs'])=={'input_sha256','protocol_sha256','shortlist_sha256'})
        for sha in [v['project_id'],v['shortlist_ticket_sha256'],*v['inputs'].values()]:_require(type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha) is not None)
        for key in ('seal_id','evaluation_id','checkpoint_id'):identifier(v[key])
        _require(v['checkpoint_id']==str(uuid5(UUID(v['evaluation_id']),'synthetic-final-initial-v1')))
        _require(canonical(v['checkpoint'])==canonical(dict(schema='synthetic-final-checkpoint-v1',position='BEFORE_BATCH',price_reads=0)))
        _require(canonical(v['budget'])==canonical(dict(attempts=2,wall_seconds=120,cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*1024**2)))
        _require(canonical(v['yearly_fits'])==canonical(fixed_definition()['fits']))
        identity(v['runtime'])
        recipe=recipe_for_pin(v['inputs']['input_sha256'])
        _require(recipe['schema']=='builtin-generated-final-recipe-v2' and canonical(recipe)==canonical(v['recipe']))
        candidates=selection(v['selected']);_require(v['selected']==[c.candidate_id for c in candidates])
        return v,candidates
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('GENERATED_FINAL_PLAN_INVALID') from None


