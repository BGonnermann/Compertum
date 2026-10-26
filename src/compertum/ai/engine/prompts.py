"""The role prompts: names, size bound and the bounded loader. No engine library; the product environment imports this module."""
from pathlib import Path
from compertum.domain import ContractError,resolve_project_path
from compertum.runtime.errors import RuntimeRefused

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


# Routing (owner direction, 26 October 2026: "USE GEPA to improve the firm"; route the information the firm needs better). What each role receives
# and where the Mathematician's review goes. GEPA rewrites this file like a prompt, but code reads only the keys and values below, so a proposal
# can choose a route and never add code. The defaults are the routes the cycle used before 26 October 2026.
ROUTING_FILE='config/engine_prompts/routing.md'
ROUTING_HEADER='ROUTING'
ROUTING_OPTIONS={
    'review':('off','advice','rebuild'),  # off: no review; advice: the review is recorded only; rebuild: the Engineer rebuilds once with the review
    'specify_sees_hypothesis':('no','yes'),  # the Mathematician also receives the Director's hypothesis
    'engineer_sees_memo':('no','yes'),  # the Engineer also receives the Researcher's memo
    'researcher_sees_lessons':('no','yes'),  # the Researcher also receives the ledger summary with its lessons
}
ROUTING_DEFAULT={'review':'advice','specify_sees_hypothesis':'no','engineer_sees_memo':'no','researcher_sees_lessons':'no'}
COMPONENTS=ROLES+('routing',)  # every text a GEPA candidate holds


def parse_routing(text):
    """The routing settings from their text: the header line, then one 'key: value' line for every key. Anything else is refused."""
    if not isinstance(text,str) or len(text.encode('utf-8'))>PROMPT_BYTES: raise RuntimeRefused('ENGINE_ROUTING_INVALID')
    lines=[line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines or lines[0]!=ROUTING_HEADER: raise RuntimeRefused('ENGINE_ROUTING_INVALID')
    settings={}
    for line in lines[1:]:
        key,sep,value=line.partition(':');key=key.strip();value=value.strip()
        if not sep or key not in ROUTING_OPTIONS or key in settings or value not in ROUTING_OPTIONS[key]: raise RuntimeRefused('ENGINE_ROUTING_INVALID')
        settings[key]=value
    if set(settings)!=set(ROUTING_OPTIONS): raise RuntimeRefused('ENGINE_ROUTING_INVALID')
    return settings


def routing_text(settings):
    return ROUTING_HEADER+'\n'+''.join(f'{key}: {settings[key]}\n' for key in ROUTING_OPTIONS)


def load_routing_text(project_root):
    """The committed routing text, checked. Without the file the cycle uses the default routes."""
    root=Path(project_root).absolute()
    try: path=resolve_project_path(ROUTING_FILE,root)
    except ContractError as error: raise RuntimeRefused(error.reason) from None
    if not path.is_file(): return routing_text(ROUTING_DEFAULT)
    try: text=path.read_bytes()[:PROMPT_BYTES+1].decode('utf-8')
    except (OSError,UnicodeError): raise RuntimeRefused('ENGINE_ROUTING_INVALID') from None
    parse_routing(text);return text


def load_component(project_root,name):
    """One committed candidate text: a role prompt or the routing."""
    return load_routing_text(project_root) if name=='routing' else load_prompt(project_root,name)
