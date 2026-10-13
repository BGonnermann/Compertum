"""Opaque metadata export bounds do not grant native audit authority."""
import copy,json
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.aggregate_evidence import encode_exports,decode_exports,export_plan

MIB=1024**2

def entry(unit,padding=''):
    return {'state':{'request':{'unit':unit},'padding':padding},'history':[]}


def test_bounded_exports_round_trip_preserves_all_metadata():
    card={'state':{'task_id':str(uuid4())},'history':[]};units=[entry(0),entry(4)]
    raws=encode_exports(card,units);assert decode_exports(raws)==(card,units)
    task=str(uuid4());plan=export_plan(task,raws)
    assert len(plan)==1 and plan[0]['role']=='audit_history' and plan[0]['index']==0
    assert plan[0]['path']==f'artifacts/runs/{task}/review/input/unit-audits-0.json' and plan[0]['size_bytes']==len(raws[0])


def test_two_exports_have_fixed_order_and_third_is_refused():
    units=[entry(0,'x'*(9*MIB)),entry(1,'y'*(9*MIB))]
    raws=encode_exports({},units);assert len(raws)==2 and all(len(r)<=16*MIB for r in raws)
    assert decode_exports(raws)==({},units)
    with pytest.raises(DataError):encode_exports({},units+[entry(2,'z'*(9*MIB))])


def test_exact_per_export_limit_and_one_byte_excess():
    size=len(encode_exports({'padding':''},[])[0]);card={'padding':'x'*(16*MIB-size)}
    assert len(encode_exports(card,[])[0])==16*MIB
    card['padding']+='x'
    with pytest.raises(DataError):encode_exports(card,[])


@pytest.mark.parametrize('case',['duplicate','reordered','fit','boolean','outside','count','extra_entry'])
def test_bad_unit_export_identity_is_refused(case):
    units=[entry(0),entry(4)]
    if case=='duplicate':units[1]['state']['request']['unit']=0
    elif case=='reordered':units.reverse()
    elif case=='fit':units[1]['state']['request']['unit']=3
    elif case=='boolean':units[0]['state']['request']['unit']=False
    elif case=='outside':units[1]['state']['request']['unit']=63
    elif case=='count':units=[entry(i) for i in range(37)]
    else:units[0]['authority']=True
    with pytest.raises(DataError):encode_exports({},units)


@pytest.mark.parametrize('case',['empty','extra_field','index_bool','whitespace','missing_scorecard','unneeded_second'])
def test_decoding_refuses_noncanonical_or_inconsistent_exports(case):
    raw=encode_exports({},[entry(0)])[0];v=json.loads(raw)
    if case=='empty':raws=[]
    elif case=='whitespace':raws=[raw+b' ']
    elif case=='unneeded_second':raws=[raw,canonical(dict(schema=v['schema'],index=1,scorecard=None,unit_audits=[]))]
    else:
        if case=='extra_field':v['authority']=True
        elif case=='index_bool':v['index']=False
        else:v['scorecard']=None
        raws=[canonical(v)]
    with pytest.raises(DataError):decode_exports(raws)
