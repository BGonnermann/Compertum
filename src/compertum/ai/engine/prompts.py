"""The role prompts and the other texts GEPA may change: names, size bounds and the bounded loaders. No engine library; the product environment imports this module."""
import ast
from pathlib import Path
from compertum.domain import ContractError,resolve_project_path
from compertum.runtime.errors import RuntimeRefused
from .tasks import STARTER_MAIN

ROLES=('director','researcher','mathematician','engineer')
PROMPT_BYTES=16384


def load_prompt(project_root,role):
    """Read one bounded role prompt from inside the project. The first line must name the role."""
    if role not in ROLES: raise RuntimeRefused('AI_ROLE_DENIED')
    root=Path(project_root).absolute()
    try:
        with resolve_project_path(f'config/engine_prompts/{role}.md',root).open('rb') as stream: raw=stream.read(PROMPT_BYTES+1)
    except ContractError as error: raise RuntimeRefused(error.reason) from None
    except OSError: raise RuntimeRefused('ENGINE_PROMPT_UNAVAILABLE') from None
    if len(raw)>PROMPT_BYTES: raise RuntimeRefused('ENGINE_PROMPT_TOO_LARGE')
    try: text=raw.decode('utf-8')
    except UnicodeError: raise RuntimeRefused('ENGINE_PROMPT_INVALID') from None
    if not text.startswith(f'ROLE: {role}\n') or len(text.strip())<40: raise RuntimeRefused('ENGINE_PROMPT_INVALID')
    return text


# The firm's other parts as GEPA slots (owner direction, 26 October 2026: "USE GEPA to improve the firm", "No GEPA limits").
# Each slot is a text that GEPA rewrites like a prompt. Code reads it in one fixed way, so a proposal can change what the firm does
# and never what the referee does: the judge, the Auditor, the deflation gate, the ledger and the limits are not slots.
#   routing   which inputs each role receives, and where the review and the tool's output go (fixed keys and values)
#   settings  hypotheses per cycle, retries, Engineer runs, and each role's output cap and temperature (fixed keys and values)
#   tool      a Python analysis program; it runs in the sandbox on train.csv only, never on validation rows
#   starter   the Python starter program that the Engineer edits; it runs only in the sandbox, as the Engineer's code
# Without a file the cycle uses the defaults below, which are the cycle as it was before these slots existed.
COMPONENTS=ROLES+('routing','settings','tool','starter')  # every text a GEPA candidate holds, in GEPA's round-robin order
COMPONENT_FILES={**{role:f'{role}.md' for role in ROLES},'routing':'routing.md','settings':'settings.md','tool':'tool.py','starter':'starter.py'}
CODE_BYTES=65536

ROUTING_OPTIONS={
    'review':('off','advice','rebuild'),  # off: no review; advice: the review is recorded only; rebuild: the Engineer rebuilds once with the review
    'specify_sees_hypothesis':('no','yes'),  # the Mathematician also receives the Director's hypothesis
    'engineer_sees_memo':('no','yes'),  # the Engineer also receives the Researcher's memo
    'researcher_sees_lessons':('no','yes'),  # the Researcher also receives the ledger summary with its lessons
    'director_sees_tool':('no','yes'),  # the tool's output goes to the Director's pick
    'researcher_sees_tool':('no','yes'),  # ... to the Researcher's memo
    'specify_sees_tool':('no','yes'),  # ... to the Mathematician's specification
}
ROUTING_DEFAULT={'review':'advice','specify_sees_hypothesis':'no','engineer_sees_memo':'no','researcher_sees_lessons':'no',
                 'director_sees_tool':'no','researcher_sees_tool':'no','specify_sees_tool':'no'}
TOKEN_CAPS=('model','1024','2048','4096','8192','16384')  # model: the model file's cap, or the engine default without one
TEMPERATURES=('0','0.3','0.7','1')
SETTINGS_OPTIONS={'hypotheses':('1','2','3'),'retries':('0','1','2'),'engineer_runs':('2','3','4','5'),
                  **{f'{role}_max_tokens':TOKEN_CAPS for role in ROLES},**{f'{role}_temperature':TEMPERATURES for role in ROLES}}
SETTINGS_DEFAULT={'hypotheses':'3','retries':'1','engineer_runs':'3',**{f'{role}_max_tokens':'model' for role in ROLES},**{f'{role}_temperature':'0' for role in ROLES}}
OPTION_SLOTS={'routing':('ROUTING',ROUTING_OPTIONS,ROUTING_DEFAULT),'settings':('SETTINGS',SETTINGS_OPTIONS,SETTINGS_DEFAULT)}
# Without a tool file the tool only prints the size of train.csv, so the slot has a valid program for GEPA to grow from.
TOOL_STUB='''"""Analysis tool. It reads train.csv in its folder and prints what it finds. Its output may go to the roles (see the routing)."""
import csv

with open('train.csv',newline='',encoding='utf-8') as handle: rows=list(csv.DictReader(handle))
print('train sessions',len(rows))
'''
CODE_DEFAULTS={'tool':TOOL_STUB,'starter':STARTER_MAIN}


def parse_options(name,text):
    """The values of an option slot (routing or settings): the header line, then one 'key: value' line for every key. Anything else is refused."""
    header,options,_=OPTION_SLOTS[name];code=f'ENGINE_{name.upper()}_INVALID'
    if not isinstance(text,str) or len(text.encode('utf-8'))>PROMPT_BYTES: raise RuntimeRefused(code)
    lines=[line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines or lines[0]!=header: raise RuntimeRefused(code)
    values={}
    for line in lines[1:]:
        key,sep,value=line.partition(':');key=key.strip();value=value.strip()
        if not sep or key not in options or key in values or value not in options[key]: raise RuntimeRefused(code)
        values[key]=value
    if set(values)!=set(options): raise RuntimeRefused(code)
    return values


def options_text(name,values):
    header,options,_=OPTION_SLOTS[name]
    return header+'\n'+''.join(f'{key}: {values[key]}\n' for key in options)


def parse_routing(text): return parse_options('routing',text)
def routing_text(values): return options_text('routing',values)
def parse_settings(text): return parse_options('settings',text)


def check_code(name,text):
    """A tool or starter program: bounded UTF-8 text that parses as Python. It is parsed, never run, outside the sandbox."""
    code=f'ENGINE_{name.upper()}_INVALID'
    if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=CODE_BYTES or not text.strip(): raise RuntimeRefused(code)
    try: ast.parse(text)
    except (SyntaxError,ValueError): raise RuntimeRefused(code) from None
    return text


def check_component(name,text):
    """The shape check of one slot text. Role prompts keep their own rules (load_prompt, gepa_run.check_prompt)."""
    if name in OPTION_SLOTS: parse_options(name,text)
    elif name in CODE_DEFAULTS: check_code(name,text)
    else: raise RuntimeRefused('AI_ROLE_DENIED')
    return text


def default_component(name):
    return options_text(name,OPTION_SLOTS[name][2]) if name in OPTION_SLOTS else CODE_DEFAULTS[name]


def load_component(project_root,name):
    """One committed candidate text: a role prompt, or a slot from config/engine_prompts/ (its default when the file is absent)."""
    if name in ROLES: return load_prompt(project_root,name)
    if name not in COMPONENT_FILES: raise RuntimeRefused('AI_ROLE_DENIED')
    try: path=resolve_project_path(f'config/engine_prompts/{COMPONENT_FILES[name]}',Path(project_root).absolute())
    except ContractError as error: raise RuntimeRefused(error.reason) from None
    if not path.is_file(): return default_component(name)
    try: text=path.read_bytes()[:CODE_BYTES+1].decode('utf-8')
    except (OSError,UnicodeError): raise RuntimeRefused(f'ENGINE_{name.upper()}_INVALID') from None
    return check_component(name,text)


def load_routing_text(project_root): return load_component(project_root,'routing')
