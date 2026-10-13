"""Fixed shortlist ranking over fabricated complete scorecards; no authority."""
from copy import deepcopy
from dataclasses import asdict
import hashlib,json
from uuid import uuid4
import pytest
from compertum.campaign_contract import VARIANTS,YEARS
from compertum.data.encoding import canonical
from compertum.data.errors import DataError


def sha(raw):return hashlib.sha256(raw).hexdigest()


def fixture():
    history=[];candidates=[]
    for c in VARIANTS:
        history.extend(dict(candidate_id=c.candidate_id,year=y,state='COMPLETED',artifact_sha256='c'*64,failure_reason=None) for y in YEARS)
        candidates.append(dict(candidate_id=c.candidate_id,kind=c.kind,horizon=c.horizon,state='COMPLETE_DIAGNOSTIC',completed_years=list(YEARS),missing_years=[],failed_folds=[],trading={'10':dict(method='CONCATENATED_FOLD_DAILY_RETURNS',observations=93,metrics={'annual_mean_excess':'-0.1'},total_turnover='1')},prediction={'ml_contribution_gate':'FAIL'}))
    card=dict(schema='synthetic-campaign-scorecard-v1',financial_accepted=False,full_M2=False,registered_family=[asdict(c) for c in VARIANTS],family_size=12,counts=dict(completed=36,failed=0,pending=0),search_history=history,candidates=candidates,diagnostic_rankings={},shortlist=[],selection_status='UNQUALIFIED_SYNTHETIC_EVIDENCE',trust_basis='HASH_BOUND_TRUSTED_ENGINE_OUTPUTS_NOT_AUTHENTICATED_ORIGIN')
    compare=dict(schema='synthetic-campaign-comparison-v1',status='EXACT_MATCH',matched_units=63,index_sha256='d'*64,scorecard_sha256='',unit_counts=dict(COMPLETED=63,FAILED=0,SKIPPED=0),scope='DETERMINISTIC_OUTCOMES_PAYLOADS_DEPENDENCIES_SCORECARD_AND_INNER_AUDITS',financial_accepted=False,full_M3=False,pair_sha256='a'*64,source_run_id=str(uuid4()),wheel_run_id=str(uuid4()),aggregate_payloads={'source':'e'*64,'wheel':'f'*64})
    return card,compare


def build(card,compare):
    from compertum.shortlist import build_shortlist,project_scorecard
    raw=canonical(card);compare=deepcopy(compare);compare['scorecard_sha256']=sha(raw);compare['selection_projection']=project_scorecard(raw,expected_sha256=sha(raw));other=canonical(compare)
    return build_shortlist(raw,other,scorecard_sha256=sha(raw),comparison_sha256=sha(other))


def test_one_per_horizon_and_negative_returns_do_not_add_an_unsealed_gate():
    card,compare=fixture();result=build(card,compare);v=json.loads(result.content)
    assert v['selected']==['momentum-h01','momentum-h05','momentum-h21']
    assert len(v['dispositions'])==12 and len(v['evaluation_slots'])==36
    assert v['financial_accepted'] is False and v['full_M3'] is False and v['authority']=='AWAITING_EVALUATION_OWNER_FREEZE'
    assert result.sha256==sha(result.content) and len(result.content)<=24*1024


@pytest.mark.parametrize('criterion',['excess','turnover','momentum','lexical'])
def test_exact_sealed_tie_breaks_and_no_ridge_mse_prerequisite(criterion):
    card,compare=fixture();rows={r['candidate_id']:r for r in card['candidates']}
    expected='momentum-h01'
    if criterion=='excess':rows['ridge-h01-a100']['trading']['10']['metrics']['annual_mean_excess']='0.2';expected='ridge-h01-a100'
    elif criterion=='turnover':rows['ridge-h01-a100']['trading']['10']['total_turnover']='0.5';expected='ridge-h01-a100'
    elif criterion=='lexical':rows['momentum-h01']['trading']['10']['metrics']['annual_mean_excess']='-0.2';expected='ridge-h01-a001'
    assert json.loads(build(card,compare).content)['selected'][0]==expected


def fail_candidate(card,name):
    row=next(r for r in card['candidates'] if r['candidate_id']==name)
    row.update(state='FAILED',completed_years=[],failed_folds=[dict(year=y,reason='MISSING_REFERENCE') for y in YEARS],trading=None,prediction=None)
    for h in card['search_history']:
        if h['candidate_id']==name:h.update(state='FAILED',artifact_sha256=None,failure_reason='MISSING_REFERENCE')
    card['counts']['completed']-=3;card['counts']['failed']+=3


def test_all_failures_produce_explicit_empty_selection_with_every_trial_retained():
    card,compare=fixture()
    for c in VARIANTS:fail_candidate(card,c.candidate_id)
    compare['unit_counts']=dict(COMPLETED=27,FAILED=36,SKIPPED=0)
    v=json.loads(build(card,compare).content)
    assert v['selected']==[] and v['status']=='EMPTY_SHORTLIST' and len(v['dispositions'])==12
    assert {r['disposition'] for r in v['dispositions']}=={'FAILED'}


@pytest.mark.parametrize('fault',['pending','missing_candidate','duplicate_candidate','missing_slot','duplicate_slot','failed_promoted','year_bool','candidate_kind','counts','nan','negative_turnover','method','scorecard_schema','financial','comparison_status','comparison_missing_audit','comparison_counts','comparison_legacy','same_run'])
def test_missing_failed_or_inconsistent_evidence_cannot_select(fault):
    card,compare=fixture()
    if fault=='pending':card['search_history'][0]['state']='PENDING'
    elif fault=='missing_candidate':card['candidates'].pop()
    elif fault=='duplicate_candidate':card['candidates'][-1]=deepcopy(card['candidates'][0])
    elif fault=='missing_slot':card['search_history'].pop()
    elif fault=='duplicate_slot':card['search_history'][-1]=deepcopy(card['search_history'][0])
    elif fault=='failed_promoted':fail_candidate(card,'momentum-h01');card['candidates'][0]['state']='COMPLETE_DIAGNOSTIC'
    elif fault=='year_bool':card['search_history'][0]['year']=True
    elif fault=='candidate_kind':card['candidates'][0]['kind']='ridge'
    elif fault=='counts':card['counts']['completed']=True
    elif fault=='nan':card['candidates'][0]['trading']['10']['metrics']['annual_mean_excess']='NaN'
    elif fault=='negative_turnover':card['candidates'][0]['trading']['10']['total_turnover']='-1'
    elif fault=='method':card['candidates'][0]['trading']['10']['method']='AVERAGE_ANNUAL_METRICS'
    elif fault=='scorecard_schema':card['schema']='future'
    elif fault=='financial':card['financial_accepted']=True
    elif fault=='comparison_status':compare['status']='FAILED'
    elif fault=='comparison_missing_audit':compare['aggregate_payloads'].pop('wheel')
    elif fault=='comparison_counts':compare['matched_units']=True
    elif fault=='comparison_legacy':compare.pop('scorecard_sha256');compare['schema']='old'
    else:compare['wheel_run_id']=compare['source_run_id']
    with pytest.raises(DataError):build(card,compare)


@pytest.mark.parametrize('fault',['selection','rank','omitted','failed_reason','policy','scorecard','oversize'])
def test_compact_projection_rejects_edited_selection_inputs(fault):
    from compertum.shortlist import project_scorecard,validate_projection
    card,_=fixture();raw=canonical(card);p=project_scorecard(raw,expected_sha256=sha(raw))
    if fault=='selection':p['selected'][0]='ridge-h01-a001'
    elif fault=='rank':p['dispositions'][0]['ranking']['annual_mean_excess']='-9'
    elif fault=='omitted':p['evaluation_slots'].pop()
    elif fault=='failed_reason':p['evaluation_slots'][0]['failure_reason']='IGNORED'
    elif fault=='policy':p['selection_rule_sha256']='f'*64
    elif fault=='scorecard':p['scorecard_sha256']='bad'
    else:p['extra']='x'*(24*1024)
    with pytest.raises(DataError):validate_projection(p)


def test_compact_comparison_produces_same_shortlist_without_decoding_scorecard():
    from compertum.shortlist import project_scorecard,build_from_comparison
    card,compare=fixture();raw=canonical(card);compare['scorecard_sha256']=sha(raw);compare['selection_projection']=project_scorecard(raw,expected_sha256=sha(raw));other=canonical(compare)
    assert build_from_comparison(other,expected_sha256=sha(other))==build(card,compare)

@pytest.mark.parametrize('fault',['failed_fit_with_completed_child','skipped_momentum','skipped_without_dependency_reason'])
def test_compact_counts_must_match_the_fixed_fit_dependency_schedule(fault):
    card,compare=fixture()
    if fault=='failed_fit_with_completed_child':compare['unit_counts']=dict(COMPLETED=36,FAILED=27,SKIPPED=0)
    else:
        name='momentum-h01' if fault=='skipped_momentum' else 'ridge-h01-a001';fail_candidate(card,name)
        compare['unit_counts']=dict(COMPLETED=57,FAILED=3,SKIPPED=3)
    with pytest.raises(DataError):build(card,compare)
