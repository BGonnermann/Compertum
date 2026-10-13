import importlib
import pytest

def api():
    try: return importlib.import_module('compertum.runtime.ipc')
    except ImportError: pytest.fail('native IPC missing')

def test_native_pipe_authentication_replay_and_denials(tmp_path):
    m=api(); from compertum.runtime.owners import acquire_owner,resolve_project
    owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    effects=[]
    server=m.start_role_pipe(owner,frozenset({'status'}),lambda c: effects.append(c['action']) or {'value':len(effects)})
    try:
        from dataclasses import replace
        wrong=replace(server.endpoint,process={**server.endpoint.process,'creation_time':server.endpoint.process['creation_time']-1})
        with pytest.raises(PermissionError,match='SERVER_IDENTITY'):m.request(wrong,{'action':'status'})
        command={'action':'status','request_id':'repeat'}
        first=m.request(server.endpoint,command); second=m.request(server.endpoint,command)
        assert first==second and len(effects)==1
        assert m.request(server.endpoint,{'action':'status','request_id':'changed','generation':'wrong'})['exit_code']==3
        assert m.request(server.endpoint,{'action':'status','request_id':'spoof','role':'execution'})['exit_code']==3
        assert m.request(server.endpoint,{'action':'status','request_id':'pid','pid':1})['exit_code']==3
        assert m.request(server.endpoint,{'action':'paper','request_id':'bad'})['exit_code']==3
        assert m.request(server.endpoint,{'action':'status','request_id':'repeat','different':True})['exit_code']==3
        token=server.register_peer(owner.process,'fixture',frozenset({'status'}))
        assert m.request(server.endpoint,{'action':'status','request_id':'worker','role':'fixture','capability':token})['exit_code']==0
        assert m.request(server.endpoint,{'action':'status','request_id':'wrong','role':'fixture','capability':'wrong'})['exit_code']==3
    finally: server.close(); owner.close()
