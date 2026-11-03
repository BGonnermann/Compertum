"""The Engineer's code library (owner, 3 November 2026: "lets do" the R&D-Agent idea; docs/RESEARCH_20261103.md, section 1).

Every practice candidate leaves one record: its specification, its code, its status and the last error. No score is stored.
Before a build, the Engineer receives the closest earlier programs that produced valid signals on the same layout, matched by the words of
the specification. The match never looks at a result, so no VALIDATION selection reaches the Engineer through the library.
Bench, holdout and GEPA cycles neither write nor read the library: they must start with no history.
"""
import hashlib
import json
from pathlib import Path
import re
import threading

from compertum.runtime.errors import RuntimeRefused

LIBRARY_DIR=Path('state')/'engine'/'code_library'
LAYOUTS=('single','panel')
WORKING='SCORED'
STATUSES=('SCORED','INVALID_SIGNALS','NO_SIGNALS','BUILD_FAILED')
EXAMPLES=2
CODE_BYTES=8192
SPEC_BYTES=4096
ERROR_BYTES=1024
WORD=re.compile(r'[a-z][a-z0-9_]{2,}')
COMMON=frozenset(('the','and','for','with','each','that','this','from','are','its','then','than','not','but','all','any','one','per','use','into',
                  'when','where','which','will','over','only','both','them','they','their','session','sessions','asset','assets','weight','weights'))
_LOCK=threading.Lock()
_SAFE=re.compile(r'[^A-Za-z0-9_.-]')


def words(text):
    return sorted({w for w in WORD.findall(str(text).lower()) if w not in COMMON})


def _clip(text,limit):
    data=str(text).encode('utf-8')
    return text if len(data)<=limit else data[:limit].decode('utf-8','ignore')


def folder(project_root,layout):
    if layout not in LAYOUTS: raise RuntimeRefused('ENGINE_LIBRARY_DENIED')
    return Path(project_root).absolute()/LIBRARY_DIR/layout


def save_entry(project_root,*,layout,candidate_id,specification,files,status,error=None):
    """Write one candidate's record once, and add its line to the layout's index. A second record for the same candidate is refused."""
    if status not in STATUSES or not isinstance(candidate_id,str) or not 1<=len(candidate_id)<=128 or not isinstance(files,dict): raise RuntimeRefused('ENGINE_LIBRARY_DENIED')
    code={p:_clip(c,CODE_BYTES) for p,c in sorted(files.items()) if isinstance(p,str) and p.endswith('.py') and isinstance(c,str)}
    record={'candidate_id':candidate_id,'layout':layout,'status':status,'specification':_clip(specification or '',SPEC_BYTES),'files':code,
            'error':None if error is None else _clip(error,ERROR_BYTES)}
    data=json.dumps(record,sort_keys=True,separators=(',',':')).encode('utf-8')
    base=folder(project_root,layout);path=base/(_SAFE.sub('_',candidate_id)+'.json')
    with _LOCK:
        base.mkdir(parents=True,exist_ok=True)
        try:
            with open(path,'xb') as out: out.write(data)
        except FileExistsError: raise RuntimeRefused('ENGINE_LIBRARY_DUPLICATE') from None
        line={'candidate_id':candidate_id,'status':status,'file':path.name,'sha256':hashlib.sha256(data).hexdigest(),'words':words(specification)}
        with open(base/'index.jsonl','a',encoding='utf-8',newline='\n') as index: index.write(json.dumps(line,sort_keys=True)+'\n')
    return line


def closest(project_root,layout,specification,count=EXAMPLES):
    """The working records nearest to the specification by word overlap (Jaccard), nearest first. A changed or missing file is skipped."""
    try: lines=(folder(project_root,layout)/'index.jsonl').read_text(encoding='utf-8').splitlines()
    except OSError: return []
    wanted=set(words(specification));ranked=[]
    for order,raw in enumerate(lines):
        try: line=json.loads(raw)
        except ValueError: continue
        if not isinstance(line,dict) or line.get('status')!=WORKING or not isinstance(line.get('words'),list): continue
        theirs=set(line['words']);union=wanted|theirs
        ranked.append((-(len(wanted&theirs)/len(union) if union else 0.0),-order,line))
    ranked.sort(key=lambda r:(r[0],r[1]));out=[]
    for _,_,line in ranked:
        if len(out)==count: break
        try: data=(folder(project_root,layout)/Path(line['file']).name).read_bytes()
        except (OSError,KeyError,TypeError): continue
        if hashlib.sha256(data).hexdigest()!=line.get('sha256'): continue
        out.append(json.loads(data))
    return out


def examples_text(records):
    """The task block that shows the examples. It says what they are for: reading the files and writing the output."""
    if not records: return ''
    parts=['\n\nWORKING EXAMPLES (earlier programs of this firm that ran and wrote a valid output file; chosen by how close their specification is '
           'to yours, not by their results. Use them for how to read the input files and write the output. Your strategy is the specification above.)']
    for i,r in enumerate(records,1):
        parts.append(f"\nEXAMPLE {i} SPECIFICATION\n{r['specification']}")
        for p,c in r['files'].items(): parts.append(f'\nEXAMPLE {i} {p}\n```python\n{c}\n```')
    return '\n'.join(parts)
