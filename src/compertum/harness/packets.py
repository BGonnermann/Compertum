"""Conversation size and secret checks owned by the harness."""
from __future__ import annotations

import json
import re

from compertum.ai.manual import SECRET
from compertum.runtime.errors import RuntimeRefused

# Owner decision, 28 October 2026: a conversation may hold 512 KiB, about 130,000 tokens.
# The harness previously reused the 64 KiB event-store record limit, which three file reads could fill.
MAX_CONVERSATION = 512 * 1024
WARN_CONVERSATION = MAX_CONVERSATION * 4 // 5
SECRET_LINE = "[line hidden: it looks like a secret]"
# Common token shapes and secret assignments that the shared rule misses, such as DEEPSEEK_API_KEY  REG_SZ  value.
# This list is a safeguard for shell and search output. It is not a complete secret filter.
TOKEN = re.compile(
    r"(?i)(?:\b(?:sk|ghp|gho|ghu|ghs|ghr|xox[abprs])[-_][a-z0-9_-]{10,}|\bgithub_pat_\w{20,}|\bAKIA[0-9A-Z]{16}\b"
    r"|://[^/\s:@]+:[^/\s@]+@|\bbearer\s+[a-z0-9._~+/=-]{16,}|_authtoken"
    r"|(?:api_?key|key_id|secret|token|passw(?:or)?d|credential|auth)\w{0,40}[\"']?\s{0,8}(?:=|:|REG_(?:EXPAND_)?SZ)"
    r"\s{0,8}[\"']?[a-z0-9_./+=-]{16})")
# The rule starts at the keyword and bounds every repeat, so long text cannot make it backtrack for minutes.
# Only local text can carry a secret to a remote model. Model replies and tool-call arguments came from the model.
LOCAL_ROLES = ("system", "user", "tool")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def looks_secret(text):
    return bool(SECRET.search(text) or TOKEN.search(text))


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def checked(value, limit, code, scan=True):
    """Encode a value and refuse it above the limit. With scan, refuse local text that looks like a secret."""
    try:
        raw = encode(value)
    except (TypeError, ValueError, RecursionError):
        raise RuntimeRefused("HARNESS_PACKET_INVALID") from None
    if len(raw) > limit:
        raise RuntimeRefused(code)
    if scan:
        # Scan the decoded strings. In JSON text a line break becomes \n, which hides a secret at a line start.
        local = [item for item in value if not isinstance(item, dict) or item.get("role") in LOCAL_ROLES]
        if any(looks_secret(text) for text in _strings(local)):
            raise RuntimeRefused("AI_SENSITIVE_INPUT_DENIED")
    return raw


def kib(size):
    return f"{size / 1024:.0f} KiB"


def hide_secrets(text):
    """Hide each line that looks like a secret, so one key cannot reach a remote model."""
    return "\n".join(SECRET_LINE if looks_secret(line) else line for line in text.split("\n"))
