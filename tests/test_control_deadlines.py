"""Authenticated work may be long; a stalled acknowledgement stays bounded."""
from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
import pytest
from compertum.runtime import control
from compertum.runtime.errors import RuntimeRefused


def test_reply_ack_retains_five_seconds_after_long_handler(monkeypatch):
    clock=[100.0];deadlines=[];reads=[]
    monkeypatch.setattr(control,'deadline_after',lambda seconds:clock[0]+seconds)
    monkeypatch.setattr(control,'_owner_scope',lambda lease:nullcontext(SimpleNamespace(project=SimpleNamespace(operator_sid='o',logon_sid='l'))))
    monkeypatch.setattr(control,'require_live_owner',lambda lease:None)
    monkeypatch.setattr(control,'decode_request_frame',lambda raw:({'actor':{'kind':'operator'},'action':'checkpoint','payload':{}},None))
    @dataclass
    class Decision:
        allowed:bool=True
    def read(handle,deadline):
        reads.append(deadline)
        if len(reads)==1:return b'request'
        raise RuntimeRefused('PIPE_TIMEOUT')
    api=SimpleNamespace(connect=lambda *args:None,peer=lambda *args,**kwargs:nullcontext(SimpleNamespace(operator_sid='o',logon_sid='l')),
        read_frame=read,write_frame=lambda handle,reply,deadline:deadlines.append(deadline),disconnect=lambda handle:None)
    endpoint=SimpleNamespace(lease=SimpleNamespace(identity=SimpleNamespace(role='supervisor')),closed=False,_owner_channel=None,
        _lock=nullcontext(),api=api,handle=1,_authorize_peer=lambda *args:Decision())
    def handler(*args):clock[0]+=200;return {'status':'done'}
    with pytest.raises(RuntimeRefused,match='PIPE_TIMEOUT'):control.serve_control_once(endpoint,handler)
    assert deadlines==[305.0] and reads==[105.0,305.0]
