"""Read the two explicitly disjoint record kinds in one attempt history."""
from .domain import ExecutionIntent,ExecutionDecision
from .execution_contracts import instant,record_sha256
from .execution_risk import client_order_id
from .runtime.paper_read_packet import _local_time
from .paper_intent_records import PAPER_TYPE,validate_pair as paper_pair

def is_paper(intent):return type(intent) is dict and intent.get('record_type')==PAPER_TYPE

def validate_pair(intent,decision):
    if is_paper(intent):return paper_pair(intent,decision)
    i=ExecutionIntent(intent);d=ExecutionDecision(decision);p=i.to_payload();v=d.to_payload()
    if not(v['allowed'] and v['intent_sha256']==record_sha256(i) and v['snapshot_sha256']==p['snapshot_sha256']
           and v['account_alias']==p['account_alias'] and v['generation']==p['generation']):raise ValueError()
    return p,v,client_order_id(i)

def record_key(record):
    if type(record) is not dict or set(record)!={'intent','decision','attempted_at','client_order_id'}:raise ValueError()
    p,_,client=validate_pair(record['intent'],record['decision']);at=(_local_time if is_paper(p) else instant)(record['attempted_at'])
    if record['client_order_id']!=client or not instant(p['created_at'])<=at<instant(p['expires_at']):raise ValueError()
    return p['account_alias'],p['intent_id']
