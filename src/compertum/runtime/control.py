"""Effectful operator control over the authenticated supervisor endpoint.

The inspection protocol stays effect-free. Only the supervisor routes an
OS-authenticated operator decision to its coordinator-owned durable ledger.
"""
from dataclasses import asdict
import hashlib
import hmac
import json
import os
import time
from ._windows import NativeCallError
from .errors import RuntimeRefused
from .ipc import (PipeDescriptor,encode_envelope,authorize_envelope,_operator_registration)
from .identity import PeerObservation
from .bootstrap import _load,decode_request_frame
from .owners import _owner_scope,require_live_owner
from ._pipes import NativePipeAPI,deadline_after,verify_peer
from compertum.events import canonical


def serve_control_once(endpoint,handler,*,timeout=5):
    with _owner_scope(endpoint.lease) as guard,endpoint._lock:
        if endpoint.closed or endpoint.lease.identity.role!='supervisor' or endpoint._owner_channel is not None:
            raise RuntimeRefused('CONTROL_ENDPOINT_DENIED')
        deadline=deadline_after(timeout)
        try:
            endpoint.api.connect(endpoint.handle,deadline)
            deadline=deadline_after(5)
            with endpoint.api.peer(endpoint.handle,server_side=True) as observed:
                if (observed.operator_sid,observed.logon_sid)!=(guard.project.operator_sid,guard.project.logon_sid):
                    raise RuntimeRefused('PEER_MISMATCH')
                value,secret=decode_request_frame(endpoint.api.read_frame(endpoint.handle,deadline))
                decision=endpoint._authorize_peer(value,observed,secret)
                if value['actor']['kind']!='operator': raise RuntimeRefused('ROLE_DENIED')
                require_live_owner(endpoint.lease)
                try: result=handler(decision,value['action'],value['payload']);error=None
                except RuntimeRefused as refused: result=None;error=refused.code
                reply=canonical({'schema_version':1,'decision':asdict(decision),'result':result,'error':error})
                endpoint.api.write_frame(endpoint.handle,reply,deadline)
                if not hmac.compare_digest(endpoint.api.read_frame(endpoint.handle,deadline),hashlib.sha256(reply).digest()):
                    raise RuntimeRefused('REPLY_ACK_DENIED')
                return result
        finally:
            if not endpoint.closed: endpoint.api.disconnect(endpoint.handle)


def durable_request(endpoint,command,*,timeout=5):
    if not isinstance(endpoint,PipeDescriptor) or endpoint.registration.identity.role!='supervisor':
        raise RuntimeRefused('CONTROL_ENDPOINT_DENIED')
    raw=encode_envelope(command)
    if command['actor']['kind']!='operator': raise RuntimeRefused('ROLE_DENIED')
    api=NativePipeAPI();deadline=deadline_after(timeout)
    while True:
        try:return _request_once(api,endpoint,command,raw,deadline)
        except RuntimeRefused as error:
            # Reconnect with the exact same authenticated request and absolute
            # deadline. The durable request ledger prevents duplicate effects.
            if not disconnected(error) or time.monotonic()+.01>=deadline:raise
            time.sleep(.01)


def disconnected(error):
    return error.code=='PIPE_EOF' or (isinstance(error,NativeCallError) and error.winerror in (109,232,233))


def _request_once(api,endpoint,command,raw,deadline):
    with _connect(api,endpoint.registration,deadline) as handle,api.peer(handle,server_side=False) as observed:
        verify_peer(endpoint.registration,observed)
        with api.open_process(os.getpid()) as process:
            sid,logon=api.token_sids(process)
            own=PeerObservation(os.getpid(),api.creation_time(process),sid,logon)
        if (sid,logon)!=(endpoint.registration.identity.operator_sid,endpoint.registration.logon_sid):
            raise RuntimeRefused('PEER_MISMATCH')
        expected=authorize_envelope(command,registration=_operator_registration(own,endpoint.registration),
            observed=own,target_project_id=endpoint.registration.project_id,target_role='supervisor',
            target_generation=endpoint.registration.generation,allowed_commands=frozenset({command['action']}))
        api.write_frame(handle,raw,deadline)
        reply=api.read_frame(handle,deadline);obj=_load(reply,65536,'REPLY_DENIED')
        if (not isinstance(obj,dict) or set(obj)!={'schema_version','decision','result','error'}
                or type(obj['schema_version']) is not int or obj['schema_version']!=1
                or canonical(obj['decision'])!=canonical(asdict(expected))
                or (obj['error'] is None and not isinstance(obj['result'],dict))
                or (obj['error'] is not None and (not isinstance(obj['error'],str) or obj['result'] is not None))):
            raise RuntimeRefused('REPLY_DENIED')
        verify_peer(endpoint.registration,observed)
        api.write_frame(handle,hashlib.sha256(reply).digest(),deadline)
        if obj['error'] is not None: raise RuntimeRefused(obj['error'])
        return obj['result']


def _connect(api,registration,deadline):
    # Waiting for the previous client to disconnect sends no request and has no
    # effect to retry. Once bytes are sent, only a caller's stable request ID may
    # resolve an uncertain response through the durable ledger.
    while True:
        try: return api.client(registration)
        except NativeCallError as error:
            if error.winerror not in (2,231) or time.monotonic()+.01>=deadline: raise
            time.sleep(.01)

