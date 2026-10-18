"""Test-only native execution identity for the controlled source listener."""
import ctypes as c
import socket
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.fixture_source_binding import _rows,_Row4,_Row6,_Table4,_Table6,D
from compertum.runtime._windows import WindowsAPI
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import _metadata

def need(value):
 if not value:raise RuntimeRefused('CONTROLLED_SOURCE_CLIENT_UNVERIFIED')

def connections(family):
 # Owner-PID ALL is class 5. The product's class 3 lists listeners only.
 fn=c.WinDLL('iphlpapi',use_last_error=True).GetExtendedTcpTable
 fn.restype=D;fn.argtypes=[c.c_void_p,c.POINTER(D),c.c_int,D,c.c_int,D]
 size=D();need(fn(None,c.byref(size),False,family,5,0) in (0,122))
 for _ in range(3):
  need(4<=size.value<=1024**2);buffer=c.create_string_buffer(size.value)
  code=fn(buffer,c.byref(size),False,family,5,0)
  if code==0:need(size.value<=len(buffer));return buffer.raw[:size.value]
  need(code==122)
 raise RuntimeRefused('CONTROLLED_SOURCE_CLIENT_UNVERIFIED')

def connection_pid(ipv4,ipv6,client_port,server_port):
 need(all(type(p) is int and 1<=p<=65535 for p in (client_port,server_port)))
 def matches(row):return row.state==5 and socket.ntohs(row.port&65535)==client_port and socket.ntohs(row.remote_port&65535)==server_port
 rows=[r for r in _rows(ipv4,_Row4,_Table4) if matches(r)]
 other=[r for r in _rows(ipv6,_Row6,_Table6) if matches(r)]
 loopback=int.from_bytes(socket.inet_aton('127.0.0.1'),'little')
 need(len(rows)==1 and not other and rows[0].pid>0 and rows[0].address==rows[0].remote==loopback)
 return rows[0].pid

def verify_process_identity(pid,identity,logon_sid):
 need(type(pid) is int and pid>0 and pid==identity.pid);api=WindowsAPI()
 with api.open_process(pid) as process:
  need(api.creation_time(process)==identity.creation_filetime)
  need(api.token_sids(process)==(identity.operator_sid,logon_sid))
  need(api.WaitForSingleObject(process.get(),0)==258)

def require_native_execution(root,client,server):
 need(client[0]==server[0]=='127.0.0.1');project=resolve_project(root);api=WindowsAPI()
 path=project.root_path/'state/locks/execution.json';raw=api.read_regular(path)
 generation,identity=_metadata(raw,project,'execution')
 pid=connection_pid(connections(2),connections(23),client[1],server[1])
 verify_process_identity(pid,identity,project.logon_sid)
 need(api.read_regular(path)==raw and connection_pid(connections(2),connections(23),client[1],server[1])==pid)
 return generation,pid
