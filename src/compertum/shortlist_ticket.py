"""Bounded immutable shortlist ticket bytes; committed owner checks are separate."""
from dataclasses import dataclass
import json
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier,digest
from .clean_pair import read_pair
from .shortlist import build_from_comparison
from .review_evidence import sha

MAX_TICKET_BYTES=24*1024
PIN_FIELDS={'task_id','kind','source_run_id','state_sha256','history_sha256','request_sha256','artifact','payload_sha256','payload_bytes'}

@dataclass(frozen=True)
class ShortlistTicket:
    content:bytes
    sha256:str


def _check(ok):
    if not ok:raise DataError('SHORTLIST_TICKET_UNVERIFIED')


def review_pin(state,history):
    """Called with a revalidated completed ReviewRuns state and exact history rows."""
    _check(state['state']=='COMPLETED')
    return {**{k:state[k] for k in ('task_id','kind','source_run_id','request_sha256','artifact','payload_sha256','payload_bytes')},
        'state_sha256':sha(canonical(state)),'history_sha256':sha(canonical(history))}


def _pin(value,kind,run):
    _check(type(value) is dict and set(value)==PIN_FIELDS and value['kind']==kind and value['source_run_id']==run)
    identifier(value['task_id']);_check(value['task_id']!=run)
    for key in ('state_sha256','history_sha256','request_sha256','payload_sha256'):digest(value[key])
    _check(type(value['payload_bytes']) is int and 0<value['payload_bytes']<16*1024**2)
    a=value['artifact'];_check(type(a) is dict and set(a)=={'artifact_id','task_id','path','size_bytes','sha256'})
    identifier(a['artifact_id']);digest(a['sha256'])
    _check(a['task_id']==value['task_id'] and type(a['size_bytes']) is int and value['payload_bytes']<a['size_bytes']<=16*1024**2)
    _check(a['path'] in [f"artifacts/runs/{value['task_id']}/review/{kind}-attempt-{n}.review" for n in (1,2)])


def build_ticket(*,project_id,pair,pair_sha256,protocol_sha256,reviews,comparison):
    """Freeze exact compact evidence; neither a hash nor this function grants access."""
    try:
        digest(project_id);p=read_pair(canonical(pair),expected_sha256=pair_sha256);_check(p['project_id']==project_id)
        _check(type(protocol_sha256) is dict and set(protocol_sha256)=={'source','wheel'})
        for value in protocol_sha256.values():digest(value)
        _check(type(reviews) is dict and set(reviews)=={'scorecard','source_aggregate','wheel_aggregate','comparison'})
        for name,kind,lane in (('scorecard','scorecard','source'),('source_aggregate','aggregate','source'),('wheel_aggregate','aggregate','wheel'),('comparison','pair_compare','source')):
            _pin(reviews[name],kind,p[lane]['run_id'])
        _check(len({v['task_id'] for v in reviews.values()}|{p['source']['run_id'],p['wheel']['run_id']})==6)
        _check(len({v['artifact']['artifact_id'] for v in reviews.values()})==4)
        shortlist=build_from_comparison(comparison,expected_sha256=reviews['comparison']['payload_sha256']);s=json.loads(shortlist.content)
        _check(len(comparison)==reviews['comparison']['payload_bytes'] and s['pair_sha256']==pair_sha256 and s['source_run_id']==p['source']['run_id'] and s['wheel_run_id']==p['wheel']['run_id'])
        _check(s['scorecard_sha256']==reviews['scorecard']['payload_sha256'] and s['aggregate_payloads']=={lane:reviews[lane+'_aggregate']['payload_sha256'] for lane in ('source','wheel')})
        value=dict(schema='synthetic-shortlist-ticket-v1',project_id=project_id,pair=pair,pair_sha256=pair_sha256,protocol_sha256=protocol_sha256,reviews=reviews,
            comparison=json.loads(comparison),shortlist_sha256=shortlist.sha256,financial_accepted=False)
        raw=canonical(value);_check(len(raw)<=MAX_TICKET_BYTES);return ShortlistTicket(raw,sha(raw))
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError):
        raise DataError('SHORTLIST_TICKET_UNVERIFIED') from None


def read_ticket(raw,*,expected_sha256,comparison=None):
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAX_TICKET_BYTES and sha(raw)==digest(expected_sha256));value=json.loads(raw)
        _check(type(value) is dict and set(value)=={'schema','project_id','pair','pair_sha256','protocol_sha256','reviews','comparison','shortlist_sha256','financial_accepted'})
        retained=canonical(value['comparison'])
        if comparison is not None:_check(comparison==retained)
        comparison=retained
        rebuilt=build_ticket(**{k:value[k] for k in ('project_id','pair','pair_sha256','protocol_sha256','reviews')},comparison=comparison)
        _check(rebuilt.content==raw);return value
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError):
        raise DataError('SHORTLIST_TICKET_UNVERIFIED') from None
