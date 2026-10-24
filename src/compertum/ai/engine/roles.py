"""The four AI roles as Deep Agents over one ledgered loopback model path.

`LedgerChatModel` is the only chat model an agent sees. Every model call, including a tool call, goes through the
E1 `ModelClient`, so the ledger holds one row per call. A harness profile for the `compertum` provider removes the
`execute`, `task` and `delete` tools, disables the general-purpose subagent and the summarization middleware.
File tools work on the in-memory state backend. Nothing an agent writes reaches the file system except through `run_job`.
Role prompts live in `config/engine_prompts/<role>.md`; stage E7 (GEPA) edits those files and nothing else.
"""
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from . import harden_environment
harden_environment()  # before any LangChain import, so the libraries see tracing off and no provider key
from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage,HumanMessage,SystemMessage,ToolMessage
from langchain_core.outputs import ChatGeneration,ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.errors import GraphRecursionError
from pydantic import ConfigDict
from compertum.domain import ContractError,resolve_project_path  # noqa: E402
from compertum.runtime.errors import RuntimeRefused  # noqa: E402

from .prompts import PROMPT_BYTES,ROLES,load_prompt  # noqa: E402,F401  (re-exported; the loader has no engine library dependency)

FILE_TOOLS=['ls','read_file','write_file','edit_file','glob','grep']
EXCLUDED_TOOLS=frozenset({'execute','task','delete'})
TASK_BYTES=65536
RECURSION_LIMIT=40
PROVIDER='compertum'
_registered=False


def text_of(content):
    """Plain text from a LangChain message content. Anything that is not text is refused."""
    if isinstance(content,str): return content
    if isinstance(content,list):
        parts=[]
        for block in content:
            if isinstance(block,str): parts.append(block)
            elif isinstance(block,dict) and block.get('type')=='text' and isinstance(block.get('text'),str): parts.append(block['text'])
            else: raise RuntimeRefused('AI_MESSAGES_DENIED')
        return ''.join(parts)
    raise RuntimeRefused('AI_MESSAGES_DENIED')


def to_chat_messages(messages):
    """LangChain messages to Chat Completions messages. Tool calls keep their ids so the ledger can pair call and result."""
    out=[]
    for message in messages:
        if isinstance(message,SystemMessage): out.append({'role':'system','content':text_of(message.content)})
        elif isinstance(message,HumanMessage): out.append({'role':'user','content':text_of(message.content)})
        elif isinstance(message,AIMessage):
            entry={'role':'assistant','content':text_of(message.content)}
            if message.tool_calls:
                entry['tool_calls']=[{'id':call['id'],'type':'function','function':{'name':call['name'],'arguments':json.dumps(call['args'],sort_keys=True,separators=(',',':'))}}
                                     for call in message.tool_calls]
            out.append(entry)
        elif isinstance(message,ToolMessage): out.append({'role':'tool','content':text_of(message.content),'tool_call_id':message.tool_call_id})
        else: raise RuntimeRefused('AI_MESSAGES_DENIED')
    return out


class LedgerChatModel(BaseChatModel):
    """The one model path. Calls the E1 client, which checks the address, the model, memory, the request limit and records the call."""
    model_config=ConfigDict(arbitrary_types_allowed=True,protected_namespaces=())
    client:Any
    role:str
    purpose:str
    model_name:str
    max_tokens:int=2048
    seconds:int=120
    temperature:float=0.0

    @property
    def _llm_type(self): return 'compertum-loopback'

    def _get_ls_params(self,stop=None,**kwargs): return {'ls_provider':PROVIDER,'ls_model_name':self.model_name,'ls_model_type':'chat'}

    def bind_tools(self,tools,*,tool_choice=None,**kwargs):
        if tool_choice not in (None,'auto'): raise RuntimeRefused('AI_TOOLS_DENIED')
        return self.bind(tools=[convert_to_openai_tool(tool) for tool in tools])

    def _generate(self,messages,stop=None,run_manager=None,**kwargs):
        if stop: raise RuntimeRefused('AI_SETTINGS_DENIED')
        tools=kwargs.get('tools');chat=to_chat_messages(messages)
        settings=dict(purpose=self.purpose,max_tokens=self.max_tokens,temperature=self.temperature,seconds=self.seconds)
        if tools: content,calls,entry=self.client.complete_tools(self.role,chat,tools,**settings)
        else: content,entry=self.client.complete(self.role,chat,**settings);calls=[]
        message=AIMessage(content=content,tool_calls=[{'name':c['name'],'args':c['arguments'],'id':c['id'],'type':'tool_call'} for c in calls],
                          response_metadata={'call_id':entry['call_id'],'model_reported':entry['model_reported'],'request_index':entry['request_index']})
        return ChatResult(generations=[ChatGeneration(message=message)])


def register_profile():
    """Register the harness profile once. Deep Agents looks it up through the model's provider name."""
    global _registered
    if _registered: return
    from deepagents import GeneralPurposeSubagentProfile,HarnessProfile,register_harness_profile
    register_harness_profile(PROVIDER,HarnessProfile(excluded_tools=EXCLUDED_TOOLS,excluded_middleware=frozenset({'SummarizationMiddleware'}),
                                                     general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
    _registered=True


def agent_path(path):
    """Agent file paths are absolute in the in-memory store, for example /main.py."""
    if not isinstance(path,str) or not 2<=len(path)<=256 or not path.startswith('/') or '..' in path.split('/') or '\\' in path or '\0' in path:
        raise RuntimeRefused('ENGINE_FILES_DENIED')
    return path


@dataclass
class RoleAgent:
    role:str
    graph:Any
    backend:Any
    recursion_limit:int

    def run(self,text,files=None):
        """One fresh conversation: a task text and optional starting files. Returns the final text, the files and counts."""
        from deepagents.backends.utils import create_file_data,file_data_to_string
        if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=TASK_BYTES: raise RuntimeRefused('AI_TASK_DENIED')
        state={'messages':[HumanMessage(content=text)]}
        if files:
            if not isinstance(files,dict) or len(files)>32 or any(not isinstance(c,str) for c in files.values()): raise RuntimeRefused('ENGINE_FILES_DENIED')
            state['files']={agent_path(p):create_file_data(c) for p,c in files.items()}
        try: result=self.graph.invoke(state)
        except GraphRecursionError: raise RuntimeRefused('ENGINE_STEP_LIMIT') from None
        messages=result.get('messages') or [];final=messages[-1] if messages else None
        out_files={p:file_data_to_string(fd) for p,fd in (result.get('files') or {}).items() if isinstance(fd,dict) and fd.get('encoding','utf-8')=='utf-8'}
        return {'text':text_of(final.content) if isinstance(final,AIMessage) else '','files':out_files,'messages':len(messages),
                'tool_calls':sum(len(m.tool_calls) for m in messages if isinstance(m,AIMessage))}


def build_role_agent(role,client,*,system_prompt,tools=(),recursion_limit=RECURSION_LIMIT):
    """One Deep Agent for one role over the ledgered model. tools: extra LangChain tools, for the Engineer only."""
    if role not in ROLES or role not in client.roles: raise RuntimeRefused('AI_ROLE_DENIED')
    if type(recursion_limit) is not int or not 2<=recursion_limit<=200: raise RuntimeRefused('ENGINE_STEP_LIMIT')
    if not isinstance(system_prompt,str) or not system_prompt.startswith(f'ROLE: {role}\n'): raise RuntimeRefused('ENGINE_PROMPT_INVALID')
    harden_environment();register_profile()
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware
    backend=StateBackend()
    model=LedgerChatModel(client=client,role=role,purpose=f'engine:{role}',model_name=client.roles[role].model)
    graph=create_deep_agent(model=model,tools=list(tools),system_prompt=system_prompt,backend=backend,
                            middleware=[FilesystemMiddleware(backend=backend,tools=list(FILE_TOOLS))],name=f'compertum-{role}')
    return RoleAgent(role,graph.with_config({'recursion_limit':recursion_limit}),backend,recursion_limit)
