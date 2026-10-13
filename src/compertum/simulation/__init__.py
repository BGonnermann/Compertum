"""Bounded synthetic engineering replay; no market access or trading authority."""

__all__=['replay']

def replay(*args,**kwargs):
    from .engine import replay as compute
    return compute(*args,**kwargs)
