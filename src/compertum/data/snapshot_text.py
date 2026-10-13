"""Bounded synthetic snapshot text screening without calendar imports."""
import re
from .errors import DataError

MAX_INPUT=1024*1024
SECRET=re.compile(r'(?i)(?:\b(?:api[_-]?key|access[_-]?token|authorization|password|broker_credentials)\b|\bsk-[a-z0-9_-]{8,}|-----BEGIN .*PRIVATE KEY|PROTECTED_SENTINEL|PROTECTED_OUTCOME)')


def safe_text(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_INPUT:raise DataError('INPUT_BOUND')
    try:text=raw.decode('utf-8')
    except UnicodeError:raise DataError('INVALID_ENCODING') from None
    unescaped=re.sub(r'\\u([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),text)
    if SECRET.search(text) or SECRET.search(unescaped):raise DataError('SENSITIVE_INPUT')
    return text

