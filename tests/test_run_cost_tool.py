import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_cost  # noqa: E402


def write_run(root,name,records):
    folder=root/run_cost.TRANSCRIPTS;folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{name}.jsonl'
    path.write_text('\n'.join(json.dumps(r) for r in records)+'\nnot json\n',encoding='utf-8')
    return path


def test_cost_totals(tmp_path,capsys):
    """Each role and the total add calls, seconds, tokens and cost; a call without a reported cost is counted as unpriced."""
    write_run(tmp_path,'run-20261102-0000000a',[
        {'role':'engineer','elapsed_seconds':6.0,'usage':{'prompt_tokens':1000,'completion_tokens':50,'cached_tokens':800,'cost':0.002}},
        {'role':'engineer','elapsed_seconds':4.0,'usage':{'prompt_tokens':500,'completion_tokens':25}},
        {'role':'director','elapsed_seconds':2.0,'usage':None}])
    roles,total=run_cost.add_up((tmp_path/run_cost.TRANSCRIPTS/'run-20261102-0000000a.jsonl').read_text(encoding='utf-8').splitlines())
    assert roles['engineer']=={'calls':2,'seconds':10.0,'prompt':1500,'cached':800,'completion':75,'priced':1,'cost':0.002}
    assert total['calls']==3 and total['seconds']==12.0 and total['priced']==1
    assert run_cost.main(['--project',str(tmp_path)])==0
    out=capsys.readouterr().out
    assert 'run-20261102-0000000a' in out and '(1 of 3 calls priced)' in out and 'no cost reported' in out


def test_cost_refusals(tmp_path):
    """A bad run ID, a missing run and an empty folder stop with a message."""
    with pytest.raises(SystemExit,match='not a run ID'): run_cost.main(['../x','--project',str(tmp_path)])
    with pytest.raises(SystemExit,match='no transcript'): run_cost.main(['run-20261102-0000000b','--project',str(tmp_path)])
    with pytest.raises(SystemExit,match='no transcripts'): run_cost.main(['--project',str(tmp_path)])
