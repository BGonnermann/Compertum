"""Fixed synthetic shortlist calculation; only the evaluation owner can freeze it."""
from collections import Counter
from dataclasses import asdict,dataclass
from decimal import Decimal,DecimalException
import hashlib,json,re
from .campaign_contract import VARIANTS,YEARS
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import digest,identifier,fixed_definition

MAX_SHORTLIST_BYTES=24*1024

@dataclass(frozen=True)
class Shortlist:
    content:bytes
    sha256:str


def _check(ok):
    if not ok:raise DataError('SHORTLIST_EVIDENCE_UNVERIFIED')


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _read(raw,pin,maximum):
    _check(type(raw) is bytes and 0<len(raw)<=maximum and _sha(raw)==digest(pin))
    value=json.loads(raw);_check(type(value) is dict and canonical(value)==raw);return value


def _number(value):
    _check(type(value) is str and 0<len(value)<=128);number=Decimal(value)
    _check(number.is_finite() and number.copy_abs()<=Decimal('1e32'));return number


def read_comparison(raw,*,expected_sha256):
    try:
        compare=_read(raw,expected_sha256,64*1024)
        _check(set(compare)=={'schema','status','matched_units','index_sha256','scorecard_sha256','unit_counts','scope','financial_accepted','full_M3','pair_sha256','source_run_id','wheel_run_id','aggregate_payloads','selection_projection'})
        _check(compare['schema']=='synthetic-campaign-comparison-v1' and compare['status']=='EXACT_MATCH' and type(compare['matched_units']) is int and compare['matched_units']==63)
        _check(compare['scope']=='DETERMINISTIC_OUTCOMES_PAYLOADS_DEPENDENCIES_SCORECARD_AND_INNER_AUDITS' and compare['financial_accepted'] is False and compare['full_M3'] is False)
        for key in ('index_sha256','scorecard_sha256','pair_sha256'):digest(compare[key])
        for key in ('source_run_id','wheel_run_id'):identifier(compare[key])
        _check(compare['source_run_id']!=compare['wheel_run_id'])
        _check(type(compare['aggregate_payloads']) is dict and set(compare['aggregate_payloads'])=={'source','wheel'})
        for value in compare['aggregate_payloads'].values():digest(value)
        counts=compare['unit_counts'];_check(type(counts) is dict and set(counts)=={'COMPLETED','FAILED','SKIPPED'} and all(type(n) is int and 0<=n<=63 for n in counts.values()) and sum(counts.values())==63)
        projection=validate_projection(compare['selection_projection'])
        _check(projection['scorecard_sha256']==compare['scorecard_sha256'])
        totals=Counter(s['state'] for s in projection['evaluation_slots'])
        # Each failed fit replaces one failed evaluation with its skipped child.
        # Thus failed-unit count equals failed evaluation-slot count. Only ridge
        # slots bearing the fixed dependency reason can account for skips.
        ridge={c.candidate_id for c in VARIANTS if c.kind=='ridge'}
        possible_skips=sum(s['state']=='FAILED' and s['candidate_id'] in ridge and s['failure_reason']=='DEPENDENCY_FAILED' for s in projection['evaluation_slots'])
        _check(counts['FAILED']==totals['FAILED'] and counts['SKIPPED']<=possible_skips)
        return compare
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError,DecimalException):
        raise DataError('SHORTLIST_EVIDENCE_UNVERIFIED') from None


def build_from_comparison(raw,*,expected_sha256):
    """Owner must first authenticate this exact committed native comparison."""
    compare=read_comparison(raw,expected_sha256=expected_sha256)
    selection={k:compare['selection_projection'][k] for k in ('selected','dispositions','evaluation_slots')}
    value=dict(schema='synthetic-shortlist-v1',status='SHORTLIST_PREPARED' if selection['selected'] else 'EMPTY_SHORTLIST',authority='AWAITING_EVALUATION_OWNER_FREEZE',
        pair_sha256=compare['pair_sha256'],source_run_id=compare['source_run_id'],wheel_run_id=compare['wheel_run_id'],scorecard_sha256=compare['scorecard_sha256'],comparison_sha256=expected_sha256,
        aggregate_payloads=compare['aggregate_payloads'],selection_rule=fixed_definition()['selection'],**selection,financial_accepted=False,full_M3=False)
    content=canonical(value);_check(len(content)<=MAX_SHORTLIST_BYTES);return Shortlist(content,_sha(content))


def build_shortlist(scorecard_raw,comparison_raw,*,scorecard_sha256,comparison_sha256):
    """Optional exact source-card check; only owner-backed provenance grants freeze."""
    compare=read_comparison(comparison_raw,expected_sha256=comparison_sha256)
    projection=project_scorecard(scorecard_raw,expected_sha256=scorecard_sha256)
    _check(canonical(projection)==canonical(compare['selection_projection']))
    return build_from_comparison(comparison_raw,expected_sha256=comparison_sha256)


def _select_card(card,*,projection=False):
    _check(set(card)=={'schema','financial_accepted','full_M2','registered_family','family_size','counts','search_history','candidates','diagnostic_rankings','shortlist','selection_status','trust_basis'})
    _check(card['schema']=='synthetic-campaign-scorecard-v1' and card['financial_accepted'] is False and card['full_M2'] is False and type(card['family_size']) is int and card['family_size']==12)
    _check(canonical(card['registered_family'])==canonical([asdict(c) for c in VARIANTS]) and card['shortlist']==[] and card['selection_status']=='UNQUALIFIED_SYNTHETIC_EVIDENCE')
    _check(card['trust_basis']=='HASH_BOUND_TRUSTED_ENGINE_OUTPUTS_NOT_AUTHENTICATED_ORIGIN')
    history=card['search_history'];rows=card['candidates'];_check(type(history) is list and len(history)==36 and type(rows) is list and len(rows)==12)
    slots={};totals=Counter()
    for h in history:
        _check(type(h) is dict and set(h)=={'candidate_id','year','state','artifact_sha256','failure_reason'})
        _check(type(h['year']) is int and h['year'] in YEARS and h['candidate_id'] in {c.candidate_id for c in VARIANTS})
        key=(h['candidate_id'],h['year']);_check(key not in slots);slots[key]=h;state=h['state'];_check(state in ('COMPLETED','FAILED'));totals[state]+=1
        if state=='COMPLETED':digest(h['artifact_sha256']);_check(h['failure_reason'] is None)
        else:_check(h['artifact_sha256'] is None and type(h['failure_reason']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',h['failure_reason']) is not None)
    _check(canonical(card['counts'])==canonical(dict(completed=totals['COMPLETED'],failed=totals['FAILED'],pending=0)))
    dispositions=[];eligible={1:[],5:[],21:[]};seen=set()
    for row in rows:
        _check(type(row) is dict and set(row)=={'candidate_id','kind','horizon','state','completed_years','missing_years','failed_folds','trading','prediction'})
        candidate=next((c for c in VARIANTS if c.candidate_id==row['candidate_id']),None);_check(candidate is not None and candidate.candidate_id not in seen);seen.add(candidate.candidate_id)
        _check(row['kind']==candidate.kind and type(row['horizon']) is int and row['horizon']==candidate.horizon and row['missing_years']==[])
        complete=[y for y in YEARS if slots[(candidate.candidate_id,y)]['state']=='COMPLETED']
        failures=[dict(year=y,reason=slots[(candidate.candidate_id,y)]['failure_reason']) for y in YEARS if y not in complete]
        _check(canonical(row['completed_years'])==canonical(complete) and canonical(row['failed_folds'])==canonical(failures))
        _check(row['state']==('FAILED' if failures else 'COMPLETE_DIAGNOSTIC'))
        out=dict(candidate_id=candidate.candidate_id,kind=candidate.kind,horizon=candidate.horizon,disposition='FAILED' if failures else 'NOT_SELECTED',failed_folds=failures,ranking=None)
        if not failures:
            t=row['trading']['10'];_check(t['method']=='CONCATENATED_FOLD_DAILY_RETURNS')
            if not projection:_check(type(t['observations']) is int and t['observations']>0)
            excess=_number(t['metrics']['annual_mean_excess']);turnover=_number(t['total_turnover']);_check(turnover>=0)
            out['ranking']=dict(annual_mean_excess=t['metrics']['annual_mean_excess'],total_turnover=t['total_turnover'])
            eligible[candidate.horizon].append(((excess.copy_negate(),turnover,candidate.kind!='momentum',candidate.candidate_id),out))
        dispositions.append(out)
    selected=[]
    for horizon in (1,5,21):
        if eligible[horizon]:
            chosen=min(eligible[horizon],key=lambda entry:entry[0])[1];chosen['disposition']='SELECTED';selected.append(chosen['candidate_id'])
    by_id={r['candidate_id']:r for r in dispositions}
    return dict(selected=selected,dispositions=[by_id[c.candidate_id] for c in VARIANTS],evaluation_slots=[slots[(c.candidate_id,y)] for c in VARIANTS for y in YEARS])


def project_scorecard(raw,*,expected_sha256):
    """Worker calls after independent aggregate audit; no authority by itself."""
    try:
        card=_read(raw,expected_sha256,16*1024**2);selection=_select_card(card)
        result=dict(schema='synthetic-shortlist-projection-v1',scorecard_sha256=expected_sha256,
            selection_rule_sha256=_sha(canonical(fixed_definition()['selection'])),**selection)
        validate_projection(result);return result
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError,DecimalException):
        raise DataError('SHORTLIST_EVIDENCE_UNVERIFIED') from None


def validate_projection(value):
    """Check compact dispositions and ranking without numerical-library imports."""
    try:
        _check(type(value) is dict and set(value)=={'schema','scorecard_sha256','selection_rule_sha256','selected','dispositions','evaluation_slots'})
        _check(value['schema']=='synthetic-shortlist-projection-v1' and value['selection_rule_sha256']==_sha(canonical(fixed_definition()['selection'])))
        digest(value['scorecard_sha256']);_check(len(canonical(value))<=MAX_SHORTLIST_BYTES)
        rows=value['dispositions'];slots=value['evaluation_slots'];_check(type(rows) is list and len(rows)==12 and type(slots) is list and len(slots)==36)
        # Reconstruct only the fixed selection inputs, not a numerical scorecard.
        candidates=[]
        for c,row in zip(VARIANTS,rows):
            _check(type(row) is dict and set(row)=={'candidate_id','kind','horizon','disposition','failed_folds','ranking'})
            _check(row['candidate_id']==c.candidate_id and row['disposition'] in ('SELECTED','NOT_SELECTED','FAILED'))
            chosen=[s for s in slots if type(s) is dict and s.get('candidate_id')==c.candidate_id]
            complete=[s['year'] for s in chosen if s['state']=='COMPLETED'];failed=row['disposition']=='FAILED'
            t=None
            if failed:_check(row['ranking'] is None)
            else:
                ranking=row['ranking'];_check(type(ranking) is dict and set(ranking)=={'annual_mean_excess','total_turnover'})
                t={'10':dict(method='CONCATENATED_FOLD_DAILY_RETURNS',metrics={'annual_mean_excess':ranking['annual_mean_excess']},total_turnover=ranking['total_turnover'])}
            candidates.append(dict(candidate_id=c.candidate_id,kind=row['kind'],horizon=row['horizon'],state='FAILED' if failed else 'COMPLETE_DIAGNOSTIC',completed_years=complete,missing_years=[],failed_folds=row['failed_folds'],trading=t,prediction=None))
        counts=Counter(s['state'] for s in slots)
        card=dict(schema='synthetic-campaign-scorecard-v1',financial_accepted=False,full_M2=False,registered_family=[asdict(c) for c in VARIANTS],family_size=12,
            counts=dict(completed=counts['COMPLETED'],failed=counts['FAILED'],pending=counts['PENDING']),search_history=slots,candidates=candidates,diagnostic_rankings={},shortlist=[],selection_status='UNQUALIFIED_SYNTHETIC_EVIDENCE',trust_basis='HASH_BOUND_TRUSTED_ENGINE_OUTPUTS_NOT_AUTHENTICATED_ORIGIN')
        expected=_select_card(card,projection=True)
        _check(canonical(expected)==canonical({k:value[k] for k in expected}));return value
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError,DecimalException):
        raise DataError('SHORTLIST_EVIDENCE_UNVERIFIED') from None
