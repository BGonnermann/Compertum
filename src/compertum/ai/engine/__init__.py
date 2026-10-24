"""Stage E3: the section 19 autoresearch engine roles, cycle, sandbox tool and Archivist tables.

This package needs the separate engine environment (`.cache/engine-env`) for Deep Agents. The product
environment imports only `harden_environment`, `market` and `ledger`, which have no engine dependency.
"""
import os

# LangSmith checks LANGSMITH_TRACING_V2, LANGSMITH_TRACING, LANGCHAIN_TRACING_V2 and LANGCHAIN_TRACING. All four are set off.
TRACING_OFF={'LANGSMITH_TRACING':'false','LANGSMITH_TRACING_V2':'false','LANGCHAIN_TRACING_V2':'false','LANGCHAIN_TRACING':'false',
             'LANGCHAIN_CALLBACKS_BACKGROUND':'false','ANONYMIZED_TELEMETRY':'false'}
# Provider and tracing keys that the engine libraries would read. The engine removes the names. No key value is displayed or recorded.
PROVIDER_KEYS=('LANGSMITH_API_KEY','LANGCHAIN_API_KEY','LANGSMITH_ENDPOINT','LANGCHAIN_ENDPOINT','ANTHROPIC_API_KEY','OPENAI_API_KEY',
               'OPENAI_BASE_URL','GOOGLE_API_KEY','GEMINI_API_KEY','AZURE_OPENAI_API_KEY','OPENROUTER_API_KEY','NVIDIA_API_KEY',
               'FIREWORKS_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN')


def harden_environment():
    """Turn tracing off and remove provider keys from this process environment. Returns the names touched, never a value.

    roles.py calls this before it imports LangChain, so the libraries read the hardened environment. LangSmith caches
    environment reads, so a process that imported it earlier must still be treated as unhardened.
    """
    for key,value in TRACING_OFF.items(): os.environ[key]=value
    removed=sorted(key for key in PROVIDER_KEYS if os.environ.pop(key,None) is not None)
    return {'tracing_off':sorted(TRACING_OFF),'removed_keys':removed}
