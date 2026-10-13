"""Compact mathematical comparison has no native or financial authority."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import pytest
from compertum.campaign_contract import UNITS
from compertum.data.encoding import canonical
from compertum.data.errors import DataError


def fixture():
    outcomes={};audits=[]
    for i,u in enumerate(UNITS):
        outcomes[u.key]=dict(unit=i,identity=asdict(u),status='COMPLETED',artifact={'different_native_provenance':i},payload_sha256=hashlib.sha256(str(i).encode()).hexdigest(),dependency_sha256=outcomes[UNITS[u.fit_unit].key]['payload_sha256'] if u.fit_unit is not None else None)
        if u.phase=='evaluate':audits.append(dict(unit=i,audit_sha256=hashlib.sha256(('audit'+str(i)).encode()).hexdigest(),task_id='native-author'))
    return dict(state='COMPLETED',outcomes=outcomes),audits


def build(source=None,audits=None):
    from compertum.campaign_comparison import build_index
    if source is None:source,audits=fixture()
    from test_shortlist import fixture as scorecard_fixture
    from compertum.shortlist import project_scorecard
    card,_=scorecard_fixture();mapping={(u.candidate_id,u.year):source['outcomes'].get(u.key) for u in UNITS if u.phase=='evaluate'}
    for slot in card['search_history']:
        o=mapping[(slot['candidate_id'],slot['year'])]
        if o is None:continue
        if o['status'] in ('FAILED','SKIPPED'):slot.update(state='FAILED',artifact_sha256=None,failure_reason=o['reason'])
        elif o['status']=='COMPLETED':slot['artifact_sha256']=o['payload_sha256']
    for row in card['candidates']:
        slots=[s for s in card['search_history'] if s['candidate_id']==row['candidate_id']]
        row['completed_years']=[s['year'] for s in slots if s['state']=='COMPLETED']
        row['failed_folds']=[dict(year=s['year'],reason=s['failure_reason']) for s in slots if s['state']=='FAILED']
        row['state']='FAILED' if row['failed_folds'] else 'COMPLETE_DIAGNOSTIC'
    failed=sum(s['state']=='FAILED' for s in card['search_history']);card['counts']=dict(completed=36-failed,failed=failed,pending=0)
    raw=canonical(card);pin=hashlib.sha256(raw).hexdigest();projection=project_scorecard(raw,expected_sha256=pin)
    return build_index(source,scorecard_sha256=pin,unit_audits=audits,selection_projection=projection)


def test_all_fixed_units_are_compared_without_native_provenance():
    from compertum.campaign_comparison import compare_indices
    source,audits=fixture();a=build(source,audits)
    for o in source['outcomes'].values():o['artifact']={'another_lane':True}
    for audit in audits:audit['task_id']='another-native-author'
    b=build(source,audits)
    assert a==b and len(canonical(a))<64*1024
    result=compare_indices(a,b)
    assert result['matched_units']==63 and result['unit_counts']=={'COMPLETED':63,'FAILED':0,'SKIPPED':0}
    assert result['financial_accepted'] is False and result['full_M3'] is False


def test_equal_failures_stay_failed_and_failed_parent_requires_skipped_child():
    from compertum.campaign_comparison import compare_indices
    source,audits=fixture()
    for i,status,reason in ((3,'FAILED','NUMERICAL_FIT_FAILURE'),(4,'SKIPPED','DEPENDENCY_FAILED')):
        source['outcomes'][UNITS[i].key]=dict(unit=i,identity=asdict(UNITS[i]),status=status,reason=reason)
    audits=[a for a in audits if a['unit']!=4];a=build(source,audits)
    result=compare_indices(a,a)
    assert result['unit_counts']=={'COMPLETED':61,'FAILED':1,'SKIPPED':1}
    assert a['outcomes'][3]['reason']=='NUMERICAL_FIT_FAILURE'


@pytest.mark.parametrize('fault',['missing','extra','pending','unit_bool','identity','dependency','audit_missing','audit_extra','audit_duplicate','bad_audit','bad_payload','reason','skipped_without_failed_parent','state'])
def test_index_rejects_incomplete_or_inconsistent_inputs(fault):
    source,audits=fixture();o=source['outcomes'][UNITS[4].key]
    if fault=='missing':source['outcomes'].pop(UNITS[-1].key)
    elif fault=='extra':source['outcomes']['foreign']=deepcopy(o)
    elif fault=='pending':o['status']='PENDING'
    elif fault=='unit_bool':source['outcomes'][UNITS[0].key]['unit']=False
    elif fault=='identity':o['identity']['year']=2024
    elif fault=='dependency':o['dependency_sha256']='f'*64
    elif fault=='audit_missing':audits.pop()
    elif fault=='audit_extra':audits.append(dict(unit=3,audit_sha256='b'*64))
    elif fault=='audit_duplicate':audits.append(deepcopy(audits[0]))
    elif fault=='bad_audit':audits[0]['audit_sha256']='oops'
    elif fault=='bad_payload':o['payload_sha256']=None
    elif fault in ('reason','skipped_without_failed_parent'):
        o.clear();o.update(unit=4,identity=asdict(UNITS[4]),status='FAILED' if fault=='reason' else 'SKIPPED',reason='' if fault=='reason' else 'DEPENDENCY_FAILED');audits=[a for a in audits if a['unit']!=4]
    else:source['state']='READY'
    with pytest.raises(DataError):build(source,audits)


@pytest.mark.parametrize('fault',['payload','dependency','audit','scorecard','omit','extra','order','boolean','missing_index','schema','financial'])
def test_comparison_refuses_altered_math_or_old_missing_index(fault):
    from compertum.campaign_comparison import compare_indices
    a=build();b=deepcopy(a)
    if fault in ('payload','dependency','audit'):
        key={'payload':'payload_sha256','dependency':'dependency_sha256','audit':'audit_sha256'}[fault];b['outcomes'][4][key]='f'*64
    elif fault=='scorecard':b['scorecard_sha256']='f'*64
    elif fault=='omit':b['outcomes'].pop()
    elif fault=='extra':b['extra']=True
    elif fault=='order':b['outcomes'][0],b['outcomes'][1]=b['outcomes'][1],b['outcomes'][0]
    elif fault=='boolean':b['outcomes'][0]['unit']=False
    elif fault=='missing_index':b=None
    elif fault=='schema':b['schema']='future'
    else:b['financial_accepted']=True
    with pytest.raises(DataError):compare_indices(a,b)
