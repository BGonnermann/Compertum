"""Independent audit of a fixed generated Final; no selection or owner authority."""
from dataclasses import dataclass
from decimal import Decimal as D,DecimalException
import hashlib,json
import numpy as np
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.data.calendar import utc_time
from compertum.final_plan import read_plan
from compertum.modeling.generated_tables import read_final
from compertum.modeling.generated_market import generate_market
from compertum.simulation.policy import fixed_decimal
from compertum.audit import _portfolio,_metrics,reconstruct_metrics
from compertum.audit_predictions import SourceEvidence,_check,_exact,_compare,_hash
from compertum.audit_execution import _policy_dates
from compertum.audit_generated_predictions import training,predictions
from compertum.modeling.qualification import QualificationInput,EvaluationSegment,HoldingInterval,PredictionRow,qualify_synthetic


@dataclass(frozen=True)
class GeneratedFinalAudit:
    content:bytes
    sha256:str


def _binding(plan,candidates,value,plan_sha256):
    expected=dict(schema='generated-final-batch-v1',status='SYNTHETIC_ENGINEERING',authority='NO_OWNER_ADMISSION_FROM_PURE_COMPUTATION',plan_sha256=plan_sha256,evaluation_id=plan['evaluation_id'],checkpoint_id=plan['checkpoint_id'],inputs=plan['inputs'],financial_accepted=False,full_M3=False)
    _check(type(value) is dict and set(value)==set(expected)|{'market','fits','candidates'})
    for key,want in expected.items():_exact(value[key],want)
    _check(type(value['candidates']) is list and len(value['candidates'])==len(candidates))
    for c,actual in zip(candidates,value['candidates']):
        _check(type(actual) is dict and set(actual)=={'candidate_id','folds','qualification'})
        _exact(actual['candidate_id'],c.candidate_id)
        _check(type(actual['folds']) is list and len(actual['folds'])==2)
        for year,fold in zip((2024,2025),actual['folds']):
            _check(type(fold) is dict and set(fold)=={'year','model_sha256','replays','checks','predictions'})
            _exact(fold['year'],year)
    _check(type(value['fits']) is list and len(value['fits'])==sum(c.kind=='ridge' for c in candidates)*2)
    _exact([(f['candidate_id'],f['year']) for f in value['fits']],[(c.candidate_id,year) for c in candidates if c.kind=='ridge' for year in (2024,2025)])


def _replay(source,c,dates,annual,value,model,independent_model,model_sha,cost):
    expected=dict(schema_version='1',policy='registered-candidate-synthetic-v1',financial_status='SYNTHETIC_UNVERIFIED',market_sha256=source.market.sha256,sectors=source.market.sectors,start=annual['start'],end=annual['end'],horizon=c.horizon,cost_bps=cost,ledger_precision=28,ledger_rounding='ROUND_HALF_EVEN',assumptions=['SYNTHETIC_ACTIVE_TRADABLE_ASSETS','SYNTHETIC_SECTORS','ZERO_UNVERIFIED_FEES','NO_INTEREST_OR_FINANCING','HISTORICAL_REFERENCE_FILLS','NO_CONTINUOUS_INTRADAY_RISK','NO_PROVIDER_COVERAGE_ACCEPTANCE','NO_LIVE_PLANNER_PARITY'],candidate_id=c.candidate_id,model_sha256=model_sha,financial_accepted=False,fit_activation='SYNTHETIC_FIT_AUDIT_READY_ASSUMPTION',generated_source='BUILTIN_GENERATED_ONLY')
    _check(set(value)==set(expected)|{'portfolios'})
    for key,want in expected.items():_exact(value[key],want)
    _check(set(value['portfolios'])=={'strategy','spy60','spy100','equal60','zero'})
    navs={};summaries={};recorded={}
    for name,book in value['portfolios'].items():
        _check(set(book)==set('trades actions observations days signals omissions checkpoints halt completed_intervals metrics'.split()))
        navs[name],summaries[name]=_portfolio(book,source.market,dates,D(cost)/10000,name=='strategy')
        recorded[name]=[D(10000)]+[D(row['nav']) for row in book['days']]
    for name,book in value['portfolios'].items():
        rebuilt=reconstruct_metrics(navs[name],navs['spy60']);from_records=reconstruct_metrics(recorded[name],recorded['spy60'])
        _metrics(book['metrics'],rebuilt);_metrics(from_records,rebuilt);_metrics(book['metrics'],from_records)
    policy=_policy_dates(source.market,value,model,dates,source)
    if independent_model is not None:_exact(_policy_dates(source.market,value,independent_model,dates,source),policy)
    return navs,recorded,dict(recorded_fill_accounting='VERIFIED_PASS',portfolios=summaries,policy=policy,independent_native_auditor_identity='UNVERIFIED',feature_label_fit_provenance='UNVERIFIED')


def _qualification(plan,c,metadata,folds,*,independent):
    # Assemble from audited source/fill records, never embedded qualification inputs.
    streams={name:[D(10000)] for name in ('navs','benchmark','stress_navs','stress_benchmark')}
    segments=[];points=[];intervals=[];rows=[];offset=0
    for fold in folds:
        policy=fold['policy'];anchor=policy['first_eligible_index'];count=len(fold['dates'])
        segments.append(EvaluationSegment(offset,offset+count-1,None if anchor is None else offset+anchor))
        points.extend(offset+i for i in policy['checkpoints'])
        intervals.extend(HoldingInterval(r['symbol'],offset+r['start_index'],offset+r['end_index']) for r in policy['holding_intervals'])
        predictions=fold['independent_predictions'] if independent else fold['recorded_predictions']
        rows.extend(PredictionRow(r['session'],r['symbol'],D(r['prediction']),D(r['momentum_prediction']),D(r['target'])) for r in predictions)
        for cost,name,key in (('10','strategy','navs'),('10','spy60','benchmark'),('20','strategy','stress_navs'),('20','spy60','stress_benchmark')):
            navs=fold['independent_navs' if independent else 'recorded_navs'][cost][name]
            for previous,current in zip(navs,navs[1:]):streams[key].append(streams[key][-1]*current/previous)
        offset+=count
    rows.sort(key=lambda r:(r.session,r.symbol))
    value=QualificationInput(plan['inputs']['protocol_sha256'],c.candidate_id,'HISTORICAL',tuple(metadata['scoring_sessions']),*(tuple(streams[key]) for key in ('navs','benchmark','stress_navs','stress_benchmark')),tuple(segments),tuple(points),tuple(intervals),tuple(rows))
    return json.loads(qualify_synthetic(value).content)


@fixed_decimal
def audit_generated_final(plan_raw,payload_raw,*,plan_sha256,payload_sha256):
    try:
        plan,candidates=read_plan(plan_raw,plan_sha256)
        value=read_final(payload_raw,expected_sha256=payload_sha256)
        _binding(plan,candidates,value,plan_sha256)
        market,metadata=generate_market(canonical(plan['recipe']),expected_sha256=plan['inputs']['input_sha256'])
        _exact(value['market'],metadata);source=SourceEvidence(market)
        fits={(f['candidate_id'],f['year']):f for f in value['fits']};summaries=[]
        for c,record in zip(candidates,value['candidates']):
            checked=[];annual_reports=[]
            for fold in record['folds']:
                year=fold['year'];annual=metadata['annual'][str(year)];dates=[d for d in metadata['scoring_sessions'] if d[:4]==str(year)]
                fit=fits.get((c.candidate_id,year));model=solved=independent_model=fit_report=None
                if fit:
                    fit_report,solved,independent_model=training(source,c,metadata,year,fit,plan['runtime']);model=fit['model']
                _exact(fold['model_sha256'],fit['model_sha256'] if fit else None)
                independent_predictions,prediction_report=predictions(source,c,dates,utc_time(annual['scoring_as_of']),fold['predictions'],solved,model)
                _check(set(fold['replays'])==set(fold['checks'])=={'10','20'})
                independent_navs={};recorded_navs={};policies={}
                for cost in ('10','20'):
                    independent_navs[cost],recorded_navs[cost],checks=_replay(source,c,dates,annual,fold['replays'][cost],model,independent_model,fold['model_sha256'],int(cost))
                    _exact(fold['checks'][cost],checks);policies[cost]=checks['policy']
                checked.append(dict(dates=dates,policy=policies['10'],independent_predictions=independent_predictions,recorded_predictions=fold['predictions']['rows'],independent_navs=independent_navs,recorded_navs=recorded_navs))
                annual_reports.append(dict(year=year,fit=fit_report,predictions=prediction_report,policy_sha256={k:_hash(v) for k,v in policies.items()}))
            recorded_q=_qualification(plan,c,metadata,checked,independent=False);_exact(record['qualification'],recorded_q)
            independent_q=_qualification(plan,c,metadata,checked,independent=True)
            for field in ('numeric_gates','trading_arithmetic_pass','ml_contribution_gate'):_exact(recorded_q[field],independent_q[field])
            summaries.append(dict(candidate_id=c.candidate_id,folds=annual_reports,qualification_sha256=_hash(recorded_q),independent_qualification_sha256=_hash(independent_q),numeric_gates=recorded_q['numeric_gates'],trading_arithmetic_pass=recorded_q['trading_arithmetic_pass'],ml_contribution_gate=recorded_q['ml_contribution_gate'],paper_eligible=False,strategy_accepted=False))
        report=dict(schema='generated-final-independent-audit-v1',status='VERIFIED_PASS',scope='FIXED_GENERATED_FINAL_SOURCE_FIT_PREDICTION_ACCOUNTING_POLICY_QUALIFICATION',evaluation_id=plan['evaluation_id'],checkpoint_id=plan['checkpoint_id'],plan_sha256=plan_sha256,payload_sha256=payload_sha256,inputs=plan['inputs'],market_sha256=market.sha256,candidates=summaries,independent_native_auditor_identity='AWAITING_COORDINATOR_RECEIPT',financial_accepted=False,full_M3=False,limitations=metadata['limitations'])
        raw=canonical(report);_check(len(raw)<=1024**2,'AUDIT_OUTPUT_BOUND')
        return GeneratedFinalAudit(raw,hashlib.sha256(raw).hexdigest())
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,DecimalException,RecursionError,np.linalg.LinAlgError) as error:
        if isinstance(error,DataError):raise
        raise DataError('GENERATED_FINAL_AUDIT_INVALID') from None
