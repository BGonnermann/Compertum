"""Synthetic consumption journal outside replaceable SQLite snapshots.

No protected reader or evaluator exists here. A missing/uncertain chain never
establishes unused authority, and a failed mirror never returns admission.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from .events import canonical, uuid
from .runtime.errors import RuntimeRefused
from .runtime.owners import _owner_scope, require_live_owner

ZERO='0'*64
MAX_EVENTS=1024


def _directory(project):
    from .persistence import checked_path
    return checked_path(project.root_path,project.root_path/'state/evaluation-consumption')


def _flush_event(path,raw):
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def _provision(lease,project):
    require_live_owner(lease,'evaluation')
    directory=_directory(project)
    if directory.exists():
        if verify_consumption_guard(project)['status']!='VERIFIED': raise RuntimeRefused('EVALUATION_COMPROMISED')
        return
    directory.mkdir()  # Interrupted provisioning remains visible and fails closed.
    _flush_event(directory/'identity.json',canonical({'project_id':project.project_id,'schema_version':1}))
    _flush_event(directory/'head.json',canonical({'sequence':0,'sha256':ZERO}))


def _read(path):
    from .persistence import checked_path
    checked_path(path.parent,path)
    with path.open('rb') as stream: raw=stream.read(8193)
    if len(raw)>8192: raise ValueError()
    return json.loads(raw)


def verify_consumption_guard(project):
    failed={'status':'EVALUATION_COMPROMISED','consumed':{},'sequence':None,'sha256':None}
    try:
        directory=_directory(project)
        if _read(directory/'identity.json')!={'project_id':project.project_id,'schema_version':1}: return failed
        head=_read(directory/'head.json')
        if set(head)!={'sequence','sha256'} or type(head['sequence']) is not int or not 0<=head['sequence']<=MAX_EVENTS: return failed
        consumed={}; previous=ZERO
        names={p.name for p in directory.iterdir()}
        expected={'identity.json','head.json'} | {f'{n:08d}.json' for n in range(1,head['sequence']+1)}
        # Partial events, abandoned head writes and missing files are uncertainty.
        if names!=expected: return failed
        for sequence in range(1,head['sequence']+1):
            item=_read(directory/f'{sequence:08d}.json')
            if set(item)!={'schema_version','sequence','previous_sha256','record'} or item['schema_version']!=1 or item['sequence']!=sequence or item['previous_sha256']!=previous: return failed
            record=item['record']
            _validate_record(record)
            if record['seal_id'] in consumed: return failed
            consumed[record['seal_id']]=record
            previous=hashlib.sha256(canonical(item)).hexdigest()
        if previous!=head['sha256']: return failed
        return {'status':'VERIFIED','consumed':consumed,'sequence':head['sequence'],'sha256':previous}
    except (OSError,ValueError,TypeError,KeyError,RuntimeRefused): return failed


def _validate_inputs(inputs):
    if not isinstance(inputs,dict) or set(inputs)!={'input_sha256','protocol_sha256','shortlist_sha256'} or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in inputs.values()):
        raise RuntimeRefused('CONSUMPTION_INPUT_DENIED')


def _validate_record(record):
    from .domain import validate_record,ContractError
    try: validate_record('consumption_event.v1',record)
    except ContractError: raise RuntimeRefused('CONSUMPTION_INPUT_DENIED') from None

def consume_once(lease,seal_id,evaluation_id,inputs):
    require_live_owner(lease,'evaluation'); uuid(seal_id); uuid(evaluation_id); _validate_inputs(inputs)
    from .persistence import _STORES
    with _owner_scope(lease) as guard:
        store=_STORES.get(lease)
        if store is None or store.closed: raise RuntimeRefused('STORE_REQUIRED')
        if store.get_state('evaluation_status')=='EVALUATION_COMPROMISED': raise RuntimeRefused('EVALUATION_COMPROMISED')
        evidence=verify_consumption_guard(guard.project)
        if evidence['status']!='VERIFIED': raise RuntimeRefused('EVALUATION_COMPROMISED')
        prior=evidence['consumed'].get(seal_id)
        if prior and (prior['evaluation_id']!=evaluation_id or prior['inputs']!=inputs):
            raise RuntimeRefused('SEAL_ALREADY_CONSUMED')
        record=prior or {'schema_version':1,'status':'CONSUMED','seal_id':seal_id,'evaluation_id':evaluation_id,
                        'inputs':dict(inputs),'created_at':datetime.now(timezone.utc).isoformat()}
        try:
            if prior is None:
                sequence=evidence['sequence']+1
                if sequence>MAX_EVENTS: raise RuntimeRefused('CONSUMPTION_BOUND_EXCEEDED')
                item={'schema_version':1,'sequence':sequence,'previous_sha256':evidence['sha256'],'record':record}
                raw=canonical(item); directory=_directory(guard.project)
                with guard.api.open_directory(directory):
                    _flush_event(directory/f'{sequence:08d}.json',raw)
                    guard.api.publish_metadata(directory/'head.json',canonical({'sequence':sequence,'sha256':hashlib.sha256(raw).hexdigest()}))
            store.mirror_consumption(record)
            return record
        except (OSError,RuntimeRefused):
            raise RuntimeRefused('CONSUMPTION_UNVERIFIED') from None

