"""Controlled-source client identity. No actual account or broker authority."""
import os,socket,struct
from types import SimpleNamespace
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_source_binding import table4

CLIENT=49200;SERVER=49300;PID=12345
def row(*,pid=PID,local='127.0.0.1',remote='127.0.0.1',state=5,client=CLIENT,server=SERVER):
 return state,int.from_bytes(socket.inet_aton(local),'little'),socket.htons(client),int.from_bytes(socket.inet_aton(remote),'little'),socket.htons(server),pid

def test_exact_established_connection_identifies_client():
 from helpers.fixture_order_peer import connection_pid
 assert connection_pid(table4(row()),table4(),CLIENT,SERVER)==PID

@pytest.mark.parametrize('fault',['absent','duplicate','other-process','local','remote','state','client','server','zero','truncated','boolean'])
def test_ambiguous_or_wrong_connection_refuses(fault):
 from helpers.fixture_order_peer import connection_pid
 raw=table4(row());client=CLIENT
 if fault=='absent':raw=table4()
 elif fault=='duplicate':raw=table4(row(),row())
 elif fault=='other-process':raw=table4(row(),row(pid=PID+1))
 elif fault=='local':raw=table4(row(local='0.0.0.0'))
 elif fault=='remote':raw=table4(row(remote='127.0.0.2'))
 elif fault=='state':raw=table4(row(state=2))
 elif fault=='client':raw=table4(row(client=CLIENT+1))
 elif fault=='server':raw=table4(row(server=SERVER+1))
 elif fault=='zero':raw=table4(row(pid=0))
 elif fault=='truncated':raw=raw[:-1]
 else:client=True
 with pytest.raises(RuntimeRefused):connection_pid(raw,table4(),client,SERVER)

def test_actual_windows_connection_and_process_identity():
 from helpers.fixture_order_peer import connection_pid,verify_process_identity,connections
 from compertum.runtime._windows import WindowsAPI
 api=WindowsAPI()
 with socket.socket() as listener,socket.socket() as client:
  listener.bind(('127.0.0.1',0));listener.listen(1);client.connect(listener.getsockname())
  with listener.accept()[0],api.open_process(os.getpid()) as process:
   pid=connection_pid(connections(2),connections(23),client.getsockname()[1],listener.getsockname()[1]);assert pid==os.getpid()
   operator,logon=api.token_sids(process)
   identity=SimpleNamespace(pid=pid,creation_filetime=api.creation_time(process),operator_sid=operator)
   verify_process_identity(pid,identity,logon)
   with pytest.raises(RuntimeRefused):verify_process_identity(pid,SimpleNamespace(pid=pid,creation_filetime=1,operator_sid=operator),logon)
   with pytest.raises(RuntimeRefused):verify_process_identity(pid,identity,'S-1-0-0')
