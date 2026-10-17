"""Map bounded original fill fields into declared fee batches. No billing authority."""
from datetime import datetime,timedelta,timezone
import json,re
from uuid import UUID,uuid5

from .data.calendar import NY
from .data.encoding import canonical
from .domain import ContractError
from .paper_activity_records import _FILL,_token
from .paper_contracts import identifier
from .paper_fees import FeeBatch
from .runtime.errors import RuntimeRefused
from .runtime.paper_read_packet import _nanoseconds

_NAMESPACE=UUID('6d73c957-99dd-426a-9254-a920b7a9081f')
_EPOCH=datetime(1970,1,1,tzinfo=timezone.utc)


def _need(value):
    if not value:
        raise RuntimeRefused('PAPER_FEE_INPUTS_UNVERIFIED')


def _time(value):
    nanoseconds=_nanoseconds(value)
    seconds,fraction=divmod(nanoseconds,10**9)
    stamp=_EPOCH+timedelta(seconds=seconds-_EPOCH.toordinal()*86400)
    _need(2000<=stamp.year<=2100)
    return nanoseconds,stamp.astimezone(NY).date().isoformat(),stamp.strftime('%Y-%m-%dT%H:%M:%S')+f'.{fraction:09}Z'


def build_fee_batches(*,project_id,account_identity_sha256,account_alias,activities,empty_at):
    """Retain original times and IDs. Internal UUIDs are never provider execution IDs."""
    try:
        for value in (project_id,account_identity_sha256):
            _need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)
        _need(type(activities) is tuple and len(activities)<=200)
        _need(len(canonical(activities))<=1024**2)
        days={};mapping=[];original_ids=set();internal_ids=set();previous=None
        for row in activities:
            _need(type(row) is dict and set(row)==_FILL and row['activity_type']=='FILL')
            original=_token(row['id']);identifier(row['order_id'])
            _need(original not in original_ids);original_ids.add(original)
            at,day,stamp=_time(row['transaction_time'])
            _need(previous is None or at>=previous);previous=at
            _need(row['side'] in ('buy','sell'))
            framed=canonical(['COMPERTUM_DECLARED_FEE_EXECUTION_V1',project_id,account_identity_sha256,original]).decode()
            internal=str(uuid5(_NAMESPACE,framed))
            _need(internal not in internal_ids);internal_ids.add(internal)
            values=days.setdefault(day,[])
            _need(len(days)<=8 and len(values)<128)
            values.append(dict(execution_id=internal,order_id=row['order_id'],symbol=row['symbol'],
                side=row['side'].upper(),executed_at=stamp,quantity=row['qty'],price=row['price']))
            mapping.append(dict(original_activity_id=original,execution_id=internal,
                order_id=row['order_id'],original_time=row['transaction_time'],executed_at=stamp))
        if not days:
            _,day,_=_time(empty_at);days[day]=[]
        result=tuple(FeeBatch(canonical(dict(version=1,project_id=project_id,account_alias=account_alias,
            execution_date=day,currency='USD',product='NMS_EQUITY',executions=values)))
            for day,values in sorted(days.items()))
        _need(len(canonical([json.loads(batch.content) for batch in result]))+len(canonical(mapping))<=1024**2)
        return result,tuple(mapping)
    except (ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        raise RuntimeRefused('PAPER_FEE_INPUTS_UNVERIFIED') from None
