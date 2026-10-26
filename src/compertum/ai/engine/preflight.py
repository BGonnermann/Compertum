"""The preflight content check (25 October 2026). Before a practice run takes the owner lease or sends a request, it builds every
role task from each market of the run and from sample values, then checks the text. A broken task is refused before the model works.

Practice runs 5 to 10 sent the Engineer the literal text of a template, "{specification}", because one string had no f prefix.
Ten runs used the model on a task that no model could do. This check finds that class of error with no model and no sandbox.

The check uses the same builders as the cycle (tasks.py). It imports no engine library, so the product environment can run it.
"""
import json
import re
from types import SimpleNamespace
from compertum.runtime.errors import RuntimeRefused
from .prompts import ROLES,load_prompt,load_routing_text,parse_routing
from .tasks import (REVIEW_LENGTH_RULE,SAMPLE_ROWS,STARTER_MAIN,agenda_task,approve_task,engineer_task,market_brief,memo_task,pick_task,retry_task,review_task,specify_task)

TASK_BYTES=65536  # no task may be larger than one reply bound
# An unfilled Python format field: {name}, {name.attr}, {name[key]} or {name(args)}. JSON text starts with {" and does not match.
PLACEHOLDER=re.compile(r'\{[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\]|\.[A-Za-z_]\w*|\([^)]*\))*\}')
MAX_PROBLEMS=50

# Sample values. Each one is a word that no builder, market or prompt contains, so its presence in a task proves that the value arrived.
SPEC='PREFLIGHT_SPECIFICATION_TEXT'
MEMO='PREFLIGHT_MEMO_TEXT'
REPLY='PREFLIGHT_PREVIOUS_REPLY'
REVIEW='PREFLIGHT_REVIEW_TEXT'
HYPOTHESIS={'id':'preflight-h1','title':'PREFLIGHT_TITLE','idea':'PREFLIGHT_IDEA'}
SUMMARY={'preflight':'PREFLIGHT_SUMMARY','lessons':[]}
CODE={'/main.py':'print("PREFLIGHT_CODE")'}
ERROR_CODE='ENGINE_REPLY_INVALID'


class PreflightFailed(RuntimeRefused):
    """ENGINE_PREFLIGHT_FAILED with the list of problems. The list names roles and checks only; it holds no market data."""

    def __init__(self,problems):
        super().__init__('ENGINE_PREFLIGHT_FAILED');self.problems=list(problems)[:MAX_PROBLEMS]


def _text_problems(name,text,required):
    out=[]
    if not isinstance(text,str) or not text.strip(): return [f'{name}: the task is empty']
    size=len(text.encode('utf-8'))
    if size>TASK_BYTES: out.append(f'{name}: the task is {size} bytes, above {TASK_BYTES}')
    for match in PLACEHOLDER.finditer(text): out.append(f'{name}: unfilled placeholder {match.group(0)}')
    if '\\n' in text: out.append(f'{name}: the task holds a literal backslash-n, a broken escape')
    for label,value in required.items():
        if value not in text: out.append(f'{name}: the task does not hold the {label}')
    return out


def check_market(market,max_hypotheses=3,cycle_index=1):
    """The problems in the tasks that one market produces. An empty list means that every task is complete."""
    label=market.get('label','market')
    train_lines=market['train_csv'].splitlines();validation_lines=market['validation_csv'].splitlines()
    engine=SimpleNamespace(train_csv=market['train_csv'],validation_rows=market['validation_rows'],max_hypotheses=max_hypotheses)
    brief=market_brief(engine)
    summary_json=json.dumps(SUMMARY,sort_keys=True);hypothesis_json=json.dumps(HYPOTHESIS,sort_keys=True);code_json=json.dumps(CODE,sort_keys=True)
    pick=pick_task(max_hypotheses,cycle_index,brief,SUMMARY)
    built={
        'director pick':(pick,{'market brief':brief,'ledger summary':summary_json,'hypothesis limit':f'at most {max_hypotheses} hypotheses'}),
        'researcher memo':(memo_task(brief,HYPOTHESIS),{'market brief':brief,'hypothesis':hypothesis_json}),
        'director approve':(approve_task(HYPOTHESIS['id'],MEMO),{'hypothesis id':HYPOTHESIS['id'],'memo':MEMO}),
        'mathematician specify':(specify_task(brief,MEMO),{'market brief':brief,'memo':MEMO}),
        'mathematician review':(review_task(SPEC,CODE),{'specification':SPEC,'code':code_json,'length limit':REVIEW_LENGTH_RULE}),
        'director agenda':(agenda_task(brief,SUMMARY),{'market brief':brief,'ledger summary':summary_json}),
        'retry':(retry_task(pick,ERROR_CODE,REPLY),{'original task':pick,'error code':ERROR_CODE,'previous reply':REPLY}),
        # The routed variants (26 October 2026): every input that a routing setting can add must arrive.
        'researcher memo with lessons':(memo_task(brief,HYPOTHESIS,SUMMARY),{'market brief':brief,'hypothesis':hypothesis_json,'ledger summary':summary_json}),
        'mathematician specify with hypothesis':(specify_task(brief,MEMO,HYPOTHESIS),{'market brief':brief,'memo':MEMO,'hypothesis':hypothesis_json}),
    }
    problems=[]
    if f'train.csv ({max(len(train_lines)-1,0)} sessions)' not in brief or f'validation.csv ({len(market["validation_rows"])} sessions)' not in brief:
        problems.append(f'{label}: the market brief gives the wrong session counts')
    sample='\n'.join(train_lines[:SAMPLE_ROWS+1])
    for retry,previous in (('engineer build',None),('engineer build retry',REPLY)):
        task,files=engineer_task(engine,SPEC,previous_reply=previous)
        required={'specification':SPEC,'train sample':sample}
        if previous is not None: required['previous reply']=previous
        built[retry]=(task,required)
        if set(files)!={'/main.py','/spec.md'}: problems.append(f'{label}: {retry}: the start files are {sorted(files)}, not /main.py and /spec.md')
        if files.get('/spec.md')!=SPEC: problems.append(f'{label}: {retry}: /spec.md does not equal the specification')
        if files.get('/main.py')!=STARTER_MAIN: problems.append(f'{label}: {retry}: /main.py is not the starter program')
    task,_=engineer_task(engine,SPEC,memo=MEMO);built['engineer build with memo']=(task,{'specification':SPEC,'train sample':sample,'memo':MEMO})
    task,files=engineer_task(engine,SPEC,memo=MEMO,review=REVIEW,code=CODE)
    built['engineer rebuild']=(task,{'specification':SPEC,'train sample':sample,'memo':MEMO,'review':REVIEW})
    if files.get('/main.py')!=CODE['/main.py'] or files.get('/spec.md')!=SPEC: problems.append(f'{label}: engineer rebuild: the start files are not the built code and the specification')
    validation_body=set(validation_lines[1:])
    for name,(text,required) in built.items():
        problems+= [f'{label}: {p}' for p in _text_problems(name,text,required)]
        # No task may show a validation row: a model that has read the validation returns can type positions from memory.
        if isinstance(text,str) and any(line in validation_body for line in text.splitlines()): problems.append(f'{label}: {name}: the task shows a validation row')
    return problems


def check_prompts(project_root):
    """The committed role prompts: each must load (role line, size bound, UTF-8) and hold no unfilled placeholder."""
    problems=[]
    for role in ROLES:
        try: text=load_prompt(project_root,role)
        except RuntimeRefused as error: problems.append(f'prompt {role}: {error.code}');continue
        for match in PLACEHOLDER.finditer(text): problems.append(f'prompt {role}: unfilled placeholder {match.group(0)}')
    try: load_routing_text(project_root)
    except RuntimeRefused as error: problems.append(f'routing: {error.code}')
    return problems


def check_given_prompts(prompts):
    """Prompts the run will use instead of the committed ones (a GEPA candidate on the bench): the role line and no unfilled placeholder."""
    problems=[]
    for role in ROLES:
        text=prompts.get(role) if isinstance(prompts,dict) else None
        if not isinstance(text,str) or not text.startswith(f'ROLE: {role}\n'): problems.append(f'prompt {role}: ENGINE_PROMPT_INVALID');continue
        for match in PLACEHOLDER.finditer(text): problems.append(f'prompt {role}: unfilled placeholder {match.group(0)}')
    if isinstance(prompts,dict) and 'routing' in prompts:
        try: parse_routing(prompts['routing'])
        except RuntimeRefused as error: problems.append(f'routing: {error.code}')
    return problems


def preflight(project_root,markets,*,max_hypotheses=3,prompts=None):
    """Raise PreflightFailed when any task or prompt has a problem. Returns the number of checked tasks when all are complete.
    prompts: the prompts the run uses instead of the committed ones, or None."""
    problems=check_prompts(project_root) if prompts is None else check_given_prompts(prompts)
    for market in markets: problems+=check_market(market,max_hypotheses)
    if problems: raise PreflightFailed(problems)
    return {'markets':len(markets),'tasks_per_market':13,'prompts':len(ROLES)}
