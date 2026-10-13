import json,subprocess,sys
from pathlib import Path

def invoke(root,*args):
    return subprocess.run([sys.executable,'-B','-m','compertum','--root',str(root),*args,'--json'],capture_output=True,text=True,timeout=20)

def test_read_only_and_financial_commands(tmp_path):
    (tmp_path/'sentinel').write_text('preserve');before={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    for args in [('doctor','--read-only'),('status',)]:assert invoke(tmp_path,*args).returncode==0
    for args in [('start','--mode','supervised-paper'),('data','fetch'),('evaluate','final'),('paper','arm'),('orders','cancel'),('positions','close')]:
        r=invoke(tmp_path,*args);assert r.returncode==3 and json.loads(r.stdout)['reason']=='CAPABILITY_UNAVAILABLE'
    after={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert before==after
