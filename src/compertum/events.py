"""Bounded durable-event contracts. No external side effects are dispatched."""
import hashlib
import json
from uuid import UUID
from compertum.domain import _plain
from compertum.runtime.errors import RuntimeRefused

ROLES = frozenset({'coordinator','evaluation','execution'})
KINDS = frozenset({'FIXTURE_TRANSITION','CHECKPOINT','CONTROL','BROKER_SIDE_EFFECT'})
MAX_RECORD = 65536


def canonical(value):
    try:
        raw = json.dumps(_plain(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if len(raw)>MAX_RECORD: raise ValueError()
        return raw
    except (ValueError, TypeError, RecursionError):
        raise RuntimeRefused('EVENT_INVALID') from None


def uuid(value):
    try:
        if str(UUID(value)) != value: raise ValueError()
    except (ValueError, TypeError, AttributeError): raise RuntimeRefused('EVENT_INVALID') from None
    return value


def prepare_event(item, lease):
    if (not isinstance(item,dict) or set(item) != {'event_id','kind','target_role','payload'}
            or item['kind'] not in KINDS or item['target_role'] not in ROLES
            or not isinstance(item['payload'],dict)):
        raise RuntimeRefused('EVENT_INVALID')
    uuid(item['event_id'])
    value = {**item, 'project_id':lease.project_id, 'source_role':lease.identity.role,
             'source_generation':lease.generation, 'replayable':item['kind']!='BROKER_SIDE_EFFECT'}
    raw=canonical(value)
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def validate_message(value, lease):
    if not isinstance(value,dict) or set(value)!={'event_id','kind','target_role','payload','project_id','source_role','source_generation','replayable'}:
        raise RuntimeRefused('EVENT_INVALID')
    uuid(value['event_id'])
    if (value['project_id']!=lease.project_id or value['target_role']!=lease.identity.role
            or value['source_role'] not in ROLES or value['kind'] not in KINDS
            or type(value['source_generation']) is not int or value['source_generation']<1
            or not isinstance(value['payload'],dict)
            or type(value['replayable']) is not bool
            or value['replayable'] != (value['kind']!='BROKER_SIDE_EFFECT')):
        raise RuntimeRefused('EVENT_INVALID')
    raw=canonical(value)
    return hashlib.sha256(raw).hexdigest()
