"""Canonical JSON bytes without importing numerical or calendar libraries."""
import json

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
