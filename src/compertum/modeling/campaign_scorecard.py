"""Compute a complete campaign scorecard in a bounded numerical worker.

Hash and shape checks do not authenticate the source or confer shortlist authority.
"""
import hashlib,json
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.campaign_runs import validate_state,_binding
from compertum.simulation.campaign_record import verify_result
from compertum.runtime.startup_record import outcome_proof
from compertum.runtime.campaign_environment import outcome_environment,check_input_state
from .campaign import UNITS,read_campaign
from .candidate import CandidateResult
from .scorecards import FailedFold,build_scorecard

MIB=1024**2


def _check(condition):
    if not condition:raise DataError('CAMPAIGN_SCORECARD_INPUT_INVALID')


def build_from_campaign(campaign,final_state,frames,*,expected_campaign_sha256,expected_identity):
    try:
        _check(type(final_state) is bytes and 0<len(final_state)<=512*1024)
        state=json.loads(final_state);_check(canonical(state)==final_state);check_input_state(campaign,expected_campaign_sha256,state);validate_state(state)
        bundle=read_campaign(campaign,expected_sha256=expected_campaign_sha256,identity=expected_identity)
        _check(state['state']=='COMPLETED' and len(state['outcomes'])==63 and canonical(state['identity'])==canonical(expected_identity)
            and state['request_sha256']==expected_campaign_sha256 and state['maximum_bytes']==bundle['maximum_bytes'])
        primary=state['input_artifact']
        _check(primary['task_id']==state['run_id'] and primary['path']==f"artifacts/runs/{state['run_id']}/baseline/inputs.json"
            and primary['sha256']==expected_campaign_sha256 and type(primary['size_bytes']) is int and primary['size_bytes']==len(campaign))
        _check(type(frames) is dict and len(frames)<=63 and all(type(raw) is bytes and 0<len(raw)<=16*MIB for raw in frames.values()))
        _check(len(campaign)+sum(map(len,frames.values()))<=bundle['maximum_bytes'])
        _check(set(frames)=={o['artifact']['path'] for o in state['outcomes'].values() if o['status']=='COMPLETED'})
        results=[];failures=[];parent=None
        for index,unit in enumerate(UNITS):
            record=state['outcomes'][unit.key]
            if record['status']!='COMPLETED':
                parent=None
                if unit.phase=='evaluate':failures.append(FailedFold(unit.candidate_id,unit.year,record['reason']))
                continue
            artifact=record['artifact'];raw=frames[artifact['path']]
            _check(len(raw)==artifact['size_bytes'] and hashlib.sha256(raw).hexdigest()==artifact['sha256'])
            body=verify_result(raw,expected_campaign_sha256,index,record['dependency_sha256'],expected_startup=outcome_proof(state,index),expected_environment=outcome_environment(state,index))
            _check(hashlib.sha256(body).hexdigest()==record['payload_sha256'])
            _binding(body,bundle,index,parent[1] if parent is not None and parent[0]==unit.fit_unit else None)
            if unit.phase=='evaluate' and unit.fit_unit is not None:
                child=json.loads(body);fit=json.loads(parent[1])
                _check(all(canonical(child[k])==canonical(fit[k]) for k in ('dataset_assembly','fit_rows','fit_manifest','fit_manifest_sha256','model','model_sha256')))
            parent=(index,body) if unit.phase=='fit' else None
            if unit.phase=='evaluate':results.append(CandidateResult(body,record['payload_sha256']))
        _check(len(results)+len(failures)==36)
        return build_scorecard(results,failures=failures)
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError) as error:
        if isinstance(error,DataError):raise
        raise DataError('CAMPAIGN_SCORECARD_INPUT_INVALID') from None
