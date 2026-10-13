"""Bounded synthetic data validation; no provider, broker or evaluation access."""
from .errors import DataError

__all__=['DataError','Snapshot','validate_snapshot','feature_rows']

def __getattr__(name):
    if name in {'Snapshot','validate_snapshot','feature_rows'}:
        from . import snapshot
        return getattr(snapshot,name)
    raise AttributeError(name)
