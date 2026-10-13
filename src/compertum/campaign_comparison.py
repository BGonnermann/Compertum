"""Compact deterministic campaign comparison; owner evidence supplies authority."""
from collections import Counter
from dataclasses import asdict
import hashlib,re
from .campaign_contract import UNITS
from .data.encoding import canonical
from .data.errors import DataError

MAX_INDEX_BYTES=64*1024
SCHEMA='synthetic-campaign-comparison-index-v1'


def _check(ok):
    if not ok:raise DataError('CAMPAIGN_COMPARISON_UNVERIFIED')


def _digest(value):
    _check(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)
    return value


def validate_index(value):
    """Require all fixed outcomes, explicit reasons and exact fit dependencies."""
    try:
        _check(type(value) is dict and set(value)=={'schema','scorecard_sha256','outcomes','selection_projection','financial_accepted','full_M3'})
        _check(value['schema']==SCHEMA and value['financial_accepted'] is False and value['full_M3'] is False)
        _digest(value['scorecard_sha256']);rows=value['outcomes'];_check(type(rows) is list and len(rows)==len(UNITS))
        for i,(u,row) in enumerate(zip(UNITS,rows)):
            _check(type(row) is dict and type(row['unit']) is int and row['unit']==i)
            status=row['status'];_check(status in ('COMPLETED','FAILED','SKIPPED'))
            base={'unit','status'};parent=rows[u.fit_unit] if u.fit_unit is not None else None
            if status=='SKIPPED':
                _check(set(row)==base|{'reason'} and parent is not None and parent['status']=='FAILED' and row['reason']=='DEPENDENCY_FAILED')
            else:
                _check(parent is None or parent['status']=='COMPLETED')
                if status=='FAILED':
                    _check(set(row)==base|{'reason'} and type(row['reason']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',row['reason']) is not None)
                else:
                    _check(set(row)==base|{'payload_sha256','dependency_sha256','audit_sha256'})
                    _digest(row['payload_sha256']);_check(row['dependency_sha256']==(parent['payload_sha256'] if parent else None))
                    if u.phase=='evaluate':_digest(row['audit_sha256'])
                    else:_check(row['audit_sha256'] is None)
        from .shortlist import validate_projection
        projection=validate_projection(value['selection_projection']);_check(projection['scorecard_sha256']==value['scorecard_sha256'])
        slots={(s['candidate_id'],s['year']):s for s in projection['evaluation_slots']}
        for i,u in enumerate(UNITS):
            if u.phase!='evaluate':continue
            slot=slots[(u.candidate_id,u.year)];outcome=rows[i]
            _check(slot['state']==('COMPLETED' if outcome['status']=='COMPLETED' else 'FAILED'))
            if outcome['status']=='COMPLETED':_check(slot['artifact_sha256']==outcome['payload_sha256'])
            else:_check(slot['failure_reason']==outcome['reason'])
        _check(len(canonical(value))<=MAX_INDEX_BYTES)
        return value
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError):
        raise DataError('CAMPAIGN_COMPARISON_UNVERIFIED') from None


def build_index(source,*,scorecard_sha256,unit_audits,selection_projection):
    """Call only after aggregate worker verification of history, frames and audits."""
    try:
        _check(source['state']=='COMPLETED' and type(source['outcomes']) is dict and set(source['outcomes'])=={u.key for u in UNITS})
        _check(type(unit_audits) is list and len(unit_audits)<=36)
        audits={}
        for audit in unit_audits:
            i=audit['unit'];_check(type(i) is int and 0<=i<len(UNITS) and i not in audits and UNITS[i].phase=='evaluate')
            audits[i]=_digest(audit['audit_sha256'])
        rows=[];needed=set()
        for i,u in enumerate(UNITS):
            outcome=source['outcomes'][u.key]
            _check(type(outcome['unit']) is int and outcome['unit']==i and canonical(outcome['identity'])==canonical(asdict(u)))
            row=dict(unit=i,status=outcome['status'])
            if row['status']=='COMPLETED':
                if u.phase=='evaluate':needed.add(i)
                row.update(payload_sha256=outcome['payload_sha256'],dependency_sha256=outcome['dependency_sha256'],audit_sha256=audits.get(i))
            else:row['reason']=outcome['reason']
            rows.append(row)
        _check(set(audits)==needed)
        return validate_index(dict(schema=SCHEMA,scorecard_sha256=scorecard_sha256,outcomes=rows,selection_projection=selection_projection,financial_accepted=False,full_M3=False))
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError):
        raise DataError('CAMPAIGN_COMPARISON_UNVERIFIED') from None


def compare_indices(source,wheel):
    """Exact math equality includes failures; it cannot qualify failed candidates."""
    a=canonical(validate_index(source));b=canonical(validate_index(wheel));_check(a==b)
    counts=Counter(r['status'] for r in source['outcomes'])
    return dict(schema='synthetic-campaign-comparison-v1',status='EXACT_MATCH',matched_units=len(UNITS),
        index_sha256=hashlib.sha256(a).hexdigest(),scorecard_sha256=source['scorecard_sha256'],unit_counts={k:counts[k] for k in ('COMPLETED','FAILED','SKIPPED')},
        scope='DETERMINISTIC_OUTCOMES_PAYLOADS_DEPENDENCIES_SCORECARD_AND_INNER_AUDITS',selection_projection=source['selection_projection'],financial_accepted=False,full_M3=False)
