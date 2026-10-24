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
