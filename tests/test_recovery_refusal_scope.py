"""Recovery scope error boundaries with injected transport/native observations."""
from contextlib import ExitStack
from dataclasses import replace
import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from compertum.runtime import owner_channel as channel
from compertum.runtime.owner_rpc import call_owner
from compertum.runtime.recovery_adapter import RemoteStore
from compertum.runtime.errors import RuntimeRefused
from test_owner_channel import remote


@pytest.fixture
def recovery_remote(remote):
 item,_,_=remote;r=item.descriptor.registration
 item.descriptor=replace(item.descriptor,registration=replace(r,identity=replace(r.identity,role='execution')))
 return remote


def replies(item, errors):
 sent=[]
 def read(*args):
  error=errors.pop(0)
  return json.dumps(dict(schema_version=1,session=item.session,sequence=item.sequence,
                         result={} if error is None else None,error=error)).encode()
 item.api.read_frame=read
 item.api.write_frame=lambda handle,raw,deadline:sent.append(raw)
 return sent


@pytest.mark.parametrize('depth',[1,3])
def test_acknowledged_checkpoint_refusal_preserves_nested_recovery_channels(recovery_remote,tmp_path,depth):
 item,_,_=recovery_remote;store=RemoteStore(item,tmp_path);sent=replies(item,['MARKET_CHECKPOINT_BUSY',None])
 with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):
  with ExitStack() as stack:
   for _ in range(depth):stack.enter_context(channel._remote_scope(item))
   stack.enter_context(store._live())
   call_owner(item,'status',{})
 assert item.sequence==2 and len(sent)==2 and len(sent[-1])==32
 assert not item.closed and not item.handle.closed and not item.process.closed
 assert call_owner(item,'status',{})=={} and item.sequence==3


@pytest.mark.parametrize('fault',['malformed','sequence','ack_write','native_read'])
def test_unverified_exchange_still_retires_nested_recovery_channel(recovery_remote,tmp_path,fault):
 item,_,_=recovery_remote;store=RemoteStore(item,tmp_path)
 def read(*args):
  if fault=='native_read':raise OSError('injected pipe loss')
  if fault=='malformed':return b'{}'
  return json.dumps(dict(schema_version=1,session=item.session,sequence=item.sequence+(fault=='sequence'),result=None,error='MARKET_CHECKPOINT_BUSY')).encode()
 def write(handle,raw,deadline):
  if fault=='ack_write' and len(raw)==32:raise RuntimeRefused('REPLY_ACK_DENIED')
 item.api.read_frame=read;item.api.write_frame=write
 with pytest.raises((RuntimeRefused,OSError)):
  with store._live():call_owner(item,'status',{})
 assert item.closed and item.handle.closed and item.process.closed


def test_barrier_release_refusal_retires_channel_and_closes_snapshot(recovery_remote,tmp_path):
 item,_,_=recovery_remote;store=RemoteStore(item,tmp_path);item.allowed_commands|={'checkpoint'}
 closed=[];connection=SimpleNamespace(close=lambda:closed.append(True))
 replies(item,['BARRIER_MISMATCH'])
 with pytest.raises(RuntimeRefused,match='BARRIER_MISMATCH'):
  with store._live():store.barrier=str(uuid4());store.conn=connection
 assert item.closed and store.barrier is None and store.conn is None and closed==[True]


def test_local_unverified_error_still_retires_recovery_scope(recovery_remote,tmp_path):
 item,_,_=recovery_remote;store=RemoteStore(item,tmp_path)
 with pytest.raises(RuntimeRefused,match='RECOVERY_OWNER_MISMATCH'):
  with store._live():raise RuntimeRefused('RECOVERY_OWNER_MISMATCH')
 assert item.closed


@pytest.mark.parametrize('result',[{}, {'status':'UNKNOWN'}, {'status':'BARRIER_RELEASED','extra':True}],ids=['empty','wrong','extra'])
def test_barrier_release_requires_exact_acknowledgement(recovery_remote,tmp_path,result):
 item,_,_=recovery_remote;store=RemoteStore(item,tmp_path);item.allowed_commands|={'checkpoint'}
 closed=[];item.api.write_frame=lambda *args:None
 item.api.read_frame=lambda *args:json.dumps(dict(schema_version=1,session=item.session,sequence=item.sequence,result=result,error=None)).encode()
 with pytest.raises(RuntimeRefused,match='BARRIER_RELEASE_UNVERIFIED'):
  with store._live():store.barrier=str(uuid4());store.conn=SimpleNamespace(close=lambda:closed.append(True))
 assert item.closed and store.barrier is None and store.conn is None and closed==[True]


def test_exact_barrier_release_closes_snapshot_and_keeps_channel_usable(recovery_remote,tmp_path):
 item,_,_=recovery_remote;store=RemoteStore(item,tmp_path);item.allowed_commands|={'checkpoint'}
 closed=[];item.api.write_frame=lambda *args:None
 item.api.read_frame=lambda *args:json.dumps(dict(schema_version=1,session=item.session,sequence=item.sequence,result={'status':'BARRIER_RELEASED'},error=None)).encode()
 with store._live():store.barrier=str(uuid4());store.conn=SimpleNamespace(close=lambda:closed.append(True))
 assert not item.closed and item.sequence==2 and store.barrier is None and store.conn is None and closed==[True]
