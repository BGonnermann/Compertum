"""Kernel listener tables are evidence only after native owner authentication."""
import socket,struct
import pytest
from compertum.runtime.errors import RuntimeRefused
PORT=49100;PID=12345

def table4(*rows):return struct.pack('<I',len(rows))+b''.join(struct.pack('<6I',*r) for r in rows)
def row4(*,pid=PID,address='127.0.0.1',port=PORT,state=2):
    return state,int.from_bytes(socket.inet_aton(address),'little'),socket.htons(port),0,0,pid
def table6(port=PORT):
    return struct.pack('<I16sII16sIIII',1,bytes(15)+b'\1',0,socket.htons(port),bytes(16),0,0,2,PID)
def parse(v4=None,v6=None,port=PORT):
    from compertum.runtime.fixture_source_binding import listener_pid
    return listener_pid(table4(row4()) if v4 is None else v4,table4() if v6 is None else v6,port)

def test_one_exact_loopback_listener_identifies_the_process():assert parse()==PID
def test_unrelated_listener_does_not_change_original_process():assert parse(table4(row4(),row4(port=PORT+1)))==PID

@pytest.mark.parametrize('problem',['wildcard','other-address','absent','wrong-state','duplicate','other-process',
 'ipv6-same-port','truncated','count','oversized','zero-pid','boolean-port','zero-port','large-port'])
def test_ambiguous_or_malformed_listener_table_refuses(problem):
    raw=table4(row4());v6=table4();port=PORT
    if problem=='wildcard':raw=table4(row4(address='0.0.0.0'))
    elif problem=='other-address':raw=table4(row4(address='127.0.0.2'))
    elif problem=='absent':raw=table4()
    elif problem=='wrong-state':raw=table4(row4(state=5))
    elif problem=='duplicate':raw=table4(row4(),row4())
    elif problem=='other-process':raw=table4(row4(),row4(pid=PID+1))
    elif problem=='ipv6-same-port':v6=table6()
    elif problem=='truncated':raw=raw[:-1]
    elif problem=='count':raw=struct.pack('<I',16385)
    elif problem=='oversized':raw=b'\0'*(1024**2+1)
    elif problem=='zero-pid':raw=table4(row4(pid=0))
    elif problem=='boolean-port':port=True
    elif problem=='zero-port':port=0
    else:port=65536
    with pytest.raises(RuntimeRefused):parse(raw,v6,port)

def test_ordinary_transport_cannot_create_a_source_witness():
    from compertum.runtime.fixture_source_binding import finish_if_present
    assert finish_if_present(object(),object(),object(),object()) is None

def test_public_objects_cannot_start_a_trusted_fixture_get():
    from compertum.runtime.fixture_source_binding import start_fixture_get
    with pytest.raises(RuntimeRefused):start_fixture_get(object(),object(),PORT,1)
