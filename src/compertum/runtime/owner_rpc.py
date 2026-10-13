"""Bounded supervisor-to-owner RPC on an inherited, native-bound private pipe."""
import hashlib
import hmac
import ctypes as c
import time
from ._windows import HANDLE,DWORD,BOOL
from .owner_channel import _remote_scope,_record,_dump,_session
from .owners import _owner_scope
from ._pipes import deadline_after
from .errors import RuntimeRefused


def call_owner(remote,action,payload,*,timeout=5):
    with _remote_scope(remote):
        if action not in remote.allowed_commands: raise RuntimeRefused('COMMAND_DENIED')
        deadline=deadline_after(timeout)
        raw=_dump({'schema_version':1,'session':remote.session,'sequence':remote.sequence,'action':action,'payload':payload},65536)
        remote.api.write_frame(remote.handle,raw,deadline)
        reply=remote.api.read_frame(remote.handle,deadline)
        obj=_record(reply,{'session','sequence','result','error'},65536)
        _session(obj,remote.session,remote.sequence)
        remote.api.write_frame(remote.handle,hashlib.sha256(reply).digest(),deadline)
        remote.sequence+=1
        refused=obj['error']
        if refused is not None:
            if not isinstance(refused,str) or obj['result'] is not None:raise RuntimeRefused('OWNER_CHANNEL_DENIED')
        elif not isinstance(obj['result'],dict):raise RuntimeRefused('OWNER_CHANNEL_DENIED')
    # The authenticated reply was acknowledged and the sequence advanced.
    # A domain refusal is not a broken transport; malformed/unacknowledged
    # exchanges still raise inside _remote_scope and retire the channel.
    if refused is not None:raise RuntimeRefused(refused)
    return obj['result']



def serve_owner_once(channel,handler,*,timeout=.2):
    with _owner_scope(channel.endpoint.lease):
        if channel.closed or channel.pending is not None: raise RuntimeRefused('OWNER_CHANNEL_DENIED')
        deadline=deadline_after(timeout)
        wait_input(channel,deadline)
        deadline=deadline_after(5)
        raw=channel.api.read_frame(channel.handle,deadline)
        # Once a request arrives allow the normal bounded exchange window.
        deadline=deadline_after(5)
        obj=_record(raw,{'session','sequence','action','payload'},65536)
        _session(obj,channel.session,channel.sequence)
        if obj['action'] not in channel.endpoint.allowed_commands or not isinstance(obj['payload'],dict):
            raise RuntimeRefused('COMMAND_DENIED')
        try: result=handler(obj['action'],obj['payload']);error=None
        except RuntimeRefused as refused: result=None;error=refused.code
        reply=_dump({'schema_version':1,'session':channel.session,'sequence':channel.sequence,'result':result,'error':error},65536)
        channel.api.write_frame(channel.handle,reply,deadline)
        if not hmac.compare_digest(channel.api.read_frame(channel.handle,deadline),hashlib.sha256(reply).digest()):
            raise RuntimeRefused('REPLY_ACK_DENIED')
        channel.sequence+=1
        return result


def wait_input(channel,deadline):
    # Idle polling must not consume half of a framed message at a short timeout.
    # Once the first byte exists, the normal full exchange deadline applies.
    kernel=c.WinDLL('kernel32',use_last_error=True)
    peek=kernel.PeekNamedPipe;peek.argtypes=[HANDLE,HANDLE,DWORD,HANDLE,c.POINTER(DWORD),HANDLE];peek.restype=BOOL
    while True:
        available=DWORD()
        channel.api.checked(peek(channel.handle.get(),None,0,None,c.byref(available),None),'PeekOwnerPipe')
        if available.value: return
        if time.monotonic()>=deadline: raise RuntimeRefused('PIPE_DEADLINE_EXCEEDED')
        time.sleep(.005)
