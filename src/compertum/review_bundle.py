"""Exact bounded evidence manifest for native campaign review workers.

The first inherited input contains this header and metadata. It counts as one
of four exports. Hashes describe evidence; the coordinator authenticates it.
"""
import hashlib,json,re
from uuid import UUID
from .data.encoding import canonical
from .data.errors import DataError
from .development_seals import validate_binding
from .evaluation_protocol import identity as _identity

MIB=1024**2
MAX_EXPORT=16*MIB
MAX_HEADER=64*1024
ORDER={'campaign':0,'frame':1,'unit_audit':2,'audit_history':3,'scorecard':4}


def _check(value):
    if not value:raise DataError('REVIEW_BUNDLE_INVALID')


def _uuid(value):
    _check(type(value) is str and str(UUID(value))==value)


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _records(records,kind,task,source):
    _check(type(records) is list and 1<=len(records)<=103)
    counts={k:0 for k in ORDER};keys=[];paths=set();ids=set();auditors=set();campaign_bytes=0;export_bytes=0;total=0;frames=set()
    for record in records:
        _check(type(record) is dict and set(record)=={'kind','index','artifact'})
        k=record['kind'];i=record['index'];a=record['artifact'];_check(type(k) is str and k in ORDER)
        _check(type(a) is dict and set(a)=={'artifact_id','task_id','path','size_bytes','sha256'})
        _uuid(a['artifact_id']);_uuid(a['task_id'])
        _check(type(a['sha256']) is str and re.fullmatch('[0-9a-f]{64}',a['sha256']) is not None)
        size=a['size_bytes'];path=a['path'];owner=a['task_id']
        _check(type(size) is int and 0<size<=(20*MIB if k=='campaign' else MAX_EXPORT))
        _check(type(path) is str and path not in paths and a['artifact_id'] not in ids)
        paths.add(path);ids.add(a['artifact_id']);counts[k]+=1;total+=size
        base=f'artifacts/runs/{source}/baseline/'
        if k=='campaign':
            _check(i is None and owner==source and path==base+'inputs.json');campaign_bytes+=size
        elif k=='frame':
            _check(type(i) is int and 0<=i<63 and owner==source and path in [base+f'unit-{i:02}-attempt-{n}.campaign' for n in (1,2)])
            campaign_bytes+=size;frames.add(i)
        elif k=='unit_audit':
            _check(kind=='aggregate' and type(i) is int and 0<=i<63 and i%21 not in range(3,21,2) and i in frames)
            _check(owner not in {task,source} and owner not in auditors and path in [f'artifacts/runs/{owner}/audit/attempt-{n}.json' for n in (1,2)])
            auditors.add(owner)
        elif k=='audit_history':
            _check(kind=='aggregate' and type(i) is int and i==counts[k]-1 and i<2 and owner==task and path==f'artifacts/runs/{task}/review/input/unit-audits-{i}.json');export_bytes+=size
        else:
            _check(kind=='aggregate' and i is None and owner not in {task,source}|auditors and path in [f'artifacts/runs/{owner}/review/scorecard-attempt-{n}.review' for n in (1,2)]);export_bytes+=size
        keys.append((ORDER[k],-1 if i is None else i))
    _check(keys==sorted(set(keys)) and counts['campaign']==1 and counts['frame']<=63 and counts['unit_audit']<=36 and counts['audit_history']<=2)
    _check(counts['scorecard']==(1 if kind=='aggregate' else 0) and campaign_bytes<=128*MIB)
    return export_bytes,total


def build_bundle(*,kind,task_id,source_run_id,identity,protocol_seal,metadata,records):
    try:
        _check(type(kind) is str and kind in ('scorecard','aggregate','pair_compare'))
        _uuid(task_id);_uuid(source_run_id);_check(task_id!=source_run_id)
        identity=_identity(identity);validate_binding(protocol_seal)
        _check(type(metadata) is bytes and 0<len(metadata)<MAX_EXPORT)
        value=json.loads(metadata)
        _check(canonical(value)==metadata)
        if kind=='pair_compare':
            from .pair_review import validate_metadata
            validate_metadata(value,task=task_id,run=source_run_id,identity=identity,seal=protocol_seal,records=records)
            export_bytes=0;total=sum(r['artifact']['size_bytes'] for r in records)
        else:
            _check(type(value) is dict and set(value)=={'final_state','history','controls'})
            _check(type(value['final_state']) is str and 0<len(value['final_state'].encode())<=512*1024)
            _check(type(value['history']) is list and len(value['history'])<=1024 and type(value['controls']) is list and len(value['controls'])<=128)
            export_bytes,total=_records(records,kind,task_id,source_run_id)
        header=canonical(dict(schema='synthetic-campaign-review-bundle-v1',kind=kind,task_id=task_id,source_run_id=source_run_id,
            identity=identity,protocol_seal=protocol_seal,records=records,metadata_bytes=len(metadata),metadata_sha256=_sha(metadata),financial_accepted=False))
        size=len(header)+1+len(metadata)
        _check(len(header)+1<=MAX_HEADER and size<=MAX_EXPORT and size+export_bytes<=48*MIB and size+total<=752*MIB)
        return header+b'\n'+metadata
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError) as error:
        if isinstance(error,DataError):raise
        raise DataError('REVIEW_BUNDLE_INVALID') from None


def read_bundle(raw,*,expected_sha256,expected_kind,expected_task_id,expected_source_run_id,expected_identity):
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAX_EXPORT and _sha(raw)==expected_sha256)
        split=raw.find(b'\n',0,MAX_HEADER);_check(split>=0)
        header=json.loads(raw[:split]);metadata=raw[split+1:]
        _check(type(header) is dict and header.get('kind')==expected_kind and header.get('task_id')==expected_task_id and header.get('source_run_id')==expected_source_run_id)
        _check(canonical(header['identity'])==canonical(_identity(expected_identity)))
        rebuilt=build_bundle(kind=expected_kind,task_id=expected_task_id,source_run_id=expected_source_run_id,identity=expected_identity,
            protocol_seal=header['protocol_seal'],metadata=metadata,records=header['records'])
        _check(raw==rebuilt)
        return header,metadata
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError) as error:
        if isinstance(error,DataError):raise
        raise DataError('REVIEW_BUNDLE_INVALID') from None


def read_declared_bundle(raw,*,expected_sha256,expected_kind,expected_task_id,expected_source_run_id):
    """Bounded structure only; identity here is declared, not observed.

    Native callers must verify the campaign environment before inspecting the
    actual runtime and comparing it with this declaration.
    """
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAX_EXPORT and _sha(raw)==expected_sha256)
        split=raw.find(b'\n',0,MAX_HEADER);_check(split>=0)
        header=json.loads(raw[:split]);_check(type(header) is dict)
        return read_bundle(raw,expected_sha256=expected_sha256,expected_kind=expected_kind,
            expected_task_id=expected_task_id,expected_source_run_id=expected_source_run_id,expected_identity=header['identity'])
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError):raise DataError('REVIEW_BUNDLE_INVALID') from None
