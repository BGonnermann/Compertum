"""Verify bounded source journal bytes. This calculation grants no native authority."""
import hashlib
from uuid import UUID
from .data.encoding import canonical
from .paper_posted_fees import _arguments_json
from .fixture_economics import _id,_when,_amount,_hash,_need,_INVALID
from .runtime.errors import RuntimeRefused

_HEADER={'version','purpose','project_id','account_alias','asset_id','symbol','opening_cash','covered_after','fee_rules','action_events'}
_KINDS={'ACCRUAL':{'rule_id'},'PAYMENT':{'accrual_id','activity_id'},
 'REVERSAL':{'event_id_reversed','activity_id'},'UNLINKED_CREDIT':{'activity_id'}}

def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()

def decode_source_journal(raw):
    try:
        _need(type(raw) is bytes and 0<len(raw)<=128*1024 and raw.endswith(b'\n'))
        lines=raw.splitlines(keepends=True);_need(1<=len(lines)<=1025)
        rows=[]
        for line in lines:
            _need(line.endswith(b'\n') and len(line)<=16384)
            row=_arguments_json(line[:-1]);_need(type(row) is dict and canonical(row)+b'\n'==line);rows.append(row)
        first=rows[0]
        _need(set(first)=={'kind','version','producer_id','header'} and first['kind']=='SOURCE_BEGIN')
        _need(type(first['version']) is int and first['version']==1 and str(UUID(first['producer_id']))==first['producer_id'])
        header=first['header'];_need(type(header) is dict and set(header)==_HEADER)
        _need(type(header['version']) is int and header['version']==1 and header['purpose']=='CONTROLLED_LOCAL_ECONOMICS')
        _hash(header['project_id']);_amount(header['opening_cash'],zero=True)
        genesis=head=_sha(header);last=_when(header['covered_after']);closed=last-1;until=None;events=[];seen=set()
        for event in rows[1:]:
            kind=event.get('kind');at=_when(event['at'])
            _need(at>=last and event['previous_sha256']==head)
            _hash(event['sha256']);_need(event['sha256']==_sha({k:v for k,v in event.items() if k!='sha256'}))
            if kind=='CLOCK_ACK':
                _need(set(event)=={'kind','at','covered_until','previous_sha256','sha256'})
                boundary=_when(event['covered_until'])
                _need(closed<=boundary<=at and (at>last or boundary>closed))
                _need(not events or boundary>=_when(events[-1]['at']))
                closed=boundary;until=event['covered_until']
            else:
                _need(kind in _KINDS and len(events)<128 and at>closed)
                _need(set(event)=={'event_id','kind','amount','at','sequence','previous_sha256','sha256'}|_KINDS[kind])
                identity=_id(event['event_id']);_need(identity not in seen)
                _need(type(event['sequence']) is int and event['sequence']==len(events)+1)
                _amount(event['amount']);seen.add(identity);events.append(event);head=event['sha256']
            last=at
        ledger=dict(header,opening_sha256='0'*64,history_sha256='0'*64,covered_until=until,
                    events=events,event_count=len(events),ledger_head_sha256=head)
        return dict(producer_id=first['producer_id'],genesis_sha256=genesis,ledger=ledger,
                    journal_sha256=hashlib.sha256(raw).hexdigest(),source_qualified=False)
    except (*_INVALID,OSError):raise RuntimeRefused('FIXTURE_SOURCE_JOURNAL_UNVERIFIED') from None
