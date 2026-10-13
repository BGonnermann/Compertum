"""Pure fixed generated final batch. Admission and durable attempts live elsewhere."""
from dataclasses import dataclass
from decimal import Decimal as D
import hashlib,json,re
from uuid import UUID,uuid5
import numpy as np
from compertum.data.calendar import utc_time
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import fixed_definition,identity,identifier
from compertum.final_recipe import recipe_for_pin
from compertum.simulation.policy import fixed_decimal
from compertum.simulation.engine import _replay_market
from compertum.audit import _portfolio,_metrics,reconstruct_metrics
from compertum.audit_predictions import SourceEvidence
from compertum.audit_execution import _policy_dates
from .generated_market import generate_market
from .generated_tables import pack_final
from .generated_fits import _selection,_Vectors,_fit
from .candidate import _CandidateMarket,_predictions
from .ridge import RidgeArtifact,_numbers
from .registry import FEATURES
from .qualification import QualificationInput,EvaluationSegment,HoldingInterval,PredictionRow,qualify_synthetic


@dataclass(frozen=True)
class GeneratedFinal:
    content:bytes
    sha256:str


from compertum.final_plan import read_plan as _plan


class _GeneratedCandidate(_CandidateMarket):
    def __init__(self,market,candidate,fit,vectors):
        self.vectors=vectors
        if fit:
            model=fit['model'];raw=canonical(model)
            self.mean=_numbers(model['scaler']['mean'],(len(FEATURES),))
            self.scale=_numbers(model['scaler']['scale'],(len(FEATURES),))
            self.coef=_numbers(model['ridge']['coef'],(len(FEATURES),));self.intercept=model['ridge']['intercept']
            if np.any(self.scale<=0):raise DataError('INVALID_MODEL_SCALE')
            artifact=RidgeArtifact(raw,fit['model_sha256'])
        else:artifact=None
        super().__init__(market,candidate,artifact)

    def _vector(self,symbol,day):return self.vectors.get(symbol,day)

    def _prediction(self,values):
        x=_numbers(values,(len(FEATURES),))
        with np.errstate(over='raise',invalid='raise',divide='raise'):result=((x-self.mean)/self.scale)@self.coef+self.intercept
        if not np.isfinite(result):raise DataError('NONFINITE_PREDICTION')
        return float(result)

    def replay_metadata(self):
        value=super().replay_metadata()
        value['generated_source']='BUILTIN_GENERATED_ONLY'
        return value


def _check_replay(base,dates,replay,model,source):
    navs={};summaries={};cost=D(replay['cost_bps'])/10000
    for name,book in replay['portfolios'].items():
        navs[name],summaries[name]=_portfolio(book,base,dates,cost,name=='strategy')
    recorded={name:[D(10000)]+[D(row['nav']) for row in book['days']] for name,book in replay['portfolios'].items()}
    for name,book in replay['portfolios'].items():
        independent=reconstruct_metrics(navs[name],navs['spy60'])
        from_records=reconstruct_metrics(recorded[name],recorded['spy60'])
        _metrics(book['metrics'],independent);_metrics(from_records,independent);_metrics(book['metrics'],from_records)
    policy=_policy_dates(base,replay,model,dates,source)
    return dict(recorded_fill_accounting='VERIFIED_PASS',portfolios=summaries,policy=policy,
        independent_native_auditor_identity='UNVERIFIED',feature_label_fit_provenance='UNVERIFIED')


def _compound(folds,cost,name):
    navs=[D(10000)]
    for fold in folds:
        previous=D(10000)
        for row in fold['replays'][cost]['portfolios'][name]['days']:
            value=D(row['nav']);navs.append(navs[-1]*value/previous);previous=value
    return tuple(navs)


def _qualification(plan,candidate,metadata,folds):
    segments=[];points=[];intervals=[];predictions=[];offset=0
    for fold in folds:
        dates=[r['session'] for r in fold['predictions']['daily_rank_correlation']]
        policy=fold['checks']['10']['policy'];anchor=policy['first_eligible_index']
        segments.append(EvaluationSegment(offset,offset+len(dates)-1,None if anchor is None else offset+anchor))
        points.extend(offset+i for i in policy['checkpoints'])
        intervals.extend(HoldingInterval(r['symbol'],offset+r['start_index'],offset+r['end_index']) for r in policy['holding_intervals'])
        predictions.extend(PredictionRow(r['session'],r['symbol'],D(r['prediction']),D(r['momentum_prediction']),D(r['target'])) for r in fold['predictions']['rows'])
        offset+=len(dates)
    predictions.sort(key=lambda r:(r.session,r.symbol))
    result=qualify_synthetic(QualificationInput(plan['inputs']['protocol_sha256'],candidate.candidate_id,'HISTORICAL',tuple(metadata['scoring_sessions']),
        _compound(folds,'10','strategy'),_compound(folds,'10','spy60'),_compound(folds,'20','strategy'),_compound(folds,'20','spy60'),
        tuple(segments),tuple(points),tuple(intervals),tuple(predictions)))
    return json.loads(result.content)


@fixed_decimal
def evaluate_generated_final(raw,*,expected_sha256):
    plan,candidates=_plan(raw,expected_sha256)
    base,metadata=generate_market(canonical(plan['recipe']),expected_sha256=plan['inputs']['input_sha256'])
    vectors=_Vectors(base);source=SourceEvidence(base);fits=[];results=[]
    for candidate in candidates:
        folds=[]
        for year in (2024,2025):
            annual=metadata['annual'][str(year)];dates=[d for d in metadata['scoring_sessions'] if d[:4]==str(year)]
            fit=_fit(base,metadata,year,candidate,vectors) if candidate.kind=='ridge' else None
            if fit:fits.append(fit)
            market=_GeneratedCandidate(base,candidate,fit,vectors);replays={};checks={}
            for cost in (10,20):
                replay=json.loads(_replay_market(market,annual['start'],annual['end'],candidate.horizon,cost_bps=cost).content)
                replay['portfolios']['strategy']=replay['portfolios'].pop('momentum')
                replays[str(cost)]=replay
                checks[str(cost)]=_check_replay(base,dates,replay,fit['model'] if fit else None,source)
            predictions=_predictions(market,dates,utc_time(annual['scoring_as_of']))
            folds.append(dict(year=year,model_sha256=fit['model_sha256'] if fit else None,
                replays=replays,checks=checks,predictions=predictions))
        results.append(dict(candidate_id=candidate.candidate_id,folds=folds,qualification=_qualification(plan,candidate,metadata,folds)))
    value=dict(schema='generated-final-batch-v1',status='SYNTHETIC_ENGINEERING',
        authority='NO_OWNER_ADMISSION_FROM_PURE_COMPUTATION',plan_sha256=expected_sha256,
        evaluation_id=plan['evaluation_id'],checkpoint_id=plan['checkpoint_id'],inputs=plan['inputs'],
        market=metadata,fits=fits,candidates=results,financial_accepted=False,full_M3=False)
    content=pack_final(value)
    return GeneratedFinal(content,hashlib.sha256(content).hexdigest())
