"""The Engineer's code library: records once, offers only working code, matches by specification words, never by results; a tie goes to the newest."""
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from compertum.ai.engine import codebook  # noqa: E402
from compertum.runtime.errors import RuntimeRefused  # noqa: E402


def save(root,cid,spec,status='SCORED',layout='panel',code='print(1)\n',error=None):
    return codebook.save_entry(root,layout=layout,candidate_id=cid,specification=spec,files={'/main.py':code,'/spec.md':spec},status=status,error=error)


def test_closest_working(tmp_path):
    save(tmp_path,'c1','monthly momentum ranking top quartile industries')
    save(tmp_path,'c2','volatility scaling calm industries tilt')
    save(tmp_path,'c3','monthly momentum ranking top quartile industries skip month',status='INVALID_SIGNALS',error='ENGINE_SIGNALS_INVALID')
    save(tmp_path,'c4','momentum ranking',layout='single')
    found=codebook.closest(tmp_path,'panel','momentum ranking top quartile, monthly rebalance')
    assert [r['candidate_id'] for r in found]==['c1','c2'] and found[0]['files']=={'/main.py':'print(1)\n'} and 'score' not in json.dumps(found)
    assert [r['candidate_id'] for r in codebook.closest(tmp_path,'single','momentum')]==['c4'] and codebook.closest(tmp_path,'panel','x',count=1)[0]['candidate_id']=='c2'
    text=codebook.examples_text(found)
    assert text.startswith('\n\nWORKING EXAMPLES') and 'not by their results' in text and 'EXAMPLE 2 /main.py' in text and codebook.examples_text([])==''


def test_records_once(tmp_path):
    """A second record is refused; a changed record file is skipped; long code and errors are clipped; a bad status or layout is refused."""
    line=save(tmp_path,'c1','alpha beta gamma',code='x'*20000,error='e'*5000)
    assert line['status']=='SCORED' and line['words']==['alpha','beta','gamma']
    with pytest.raises(RuntimeRefused,match='^ENGINE_LIBRARY_DUPLICATE$'): save(tmp_path,'c1','alpha')
    record=json.loads((codebook.folder(tmp_path,'panel')/'c1.json').read_text(encoding='utf-8'))
    assert len(record['files']['/main.py'])==codebook.CODE_BYTES and len(record['error'])==codebook.ERROR_BYTES
    save(tmp_path,'c2','alpha beta');(codebook.folder(tmp_path,'panel')/'c2.json').write_text('{}',encoding='utf-8')
    assert [r['candidate_id'] for r in codebook.closest(tmp_path,'panel','alpha beta')]==['c1']
    for status,layout in (('GOOD','panel'),('SCORED','vault')):
        with pytest.raises(RuntimeRefused,match='^ENGINE_LIBRARY_DENIED$'): save(tmp_path,'c9','a',status=status,layout=layout)
    assert codebook.closest(tmp_path/'empty','panel','alpha')==[]
