"""Shared pure sizing rules. No broker or runtime side effects."""
from decimal import Decimal,Context,localcontext,ROUND_HALF_EVEN,InvalidOperation,DivisionByZero,Overflow
from functools import wraps
from compertum.data.errors import DataError

D=Decimal
EPS=D('1e-10')
INITIAL=D('10000')


def fixed_decimal(function):
    """Do not inherit an embedding application's rounding, flags or traps."""
    @wraps(function)
    def call(*args,**kwargs):
        context=Context(prec=28,rounding=ROUND_HALF_EVEN,Emin=-999999,Emax=999999,
            capitals=1,clamp=0,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow])
        with localcontext(context):return function(*args,**kwargs)
    return call


def number(value):
    text=format(value,'f')
    return (text.rstrip('0').rstrip('.') if '.' in text else text) if value else '0'


@fixed_decimal
def buy_quantity(budget,reference,cost):
    if any(not isinstance(x,D) or not x.is_finite() for x in (budget,reference,cost)) or budget<0 or reference<=0 or cost not in (D('.001'),D('.002')):
        raise DataError('INVALID_SIZING')
    with localcontext() as ctx:
        ctx.prec=28
        return int(budget/(reference*(1+cost)*D('1.01')))


@fixed_decimal
def qualifies(prediction,cost):
    return prediction-(2*cost+D('.001'))>EPS


@fixed_decimal
def exposure_reason(positions,prices,sectors,nav,cash):
    if nav<=0 or cash<0:return 'INVALID_NAV'
    values={s:q*prices[s] for s,q in positions.items() if q}
    if sum(values.values())/nav>=D('.6')-EPS:return 'GROSS_LIMIT'
    if any(v/nav>=D('.2')-EPS for v in values.values()):return 'NAME_LIMIT'
    for sector in set(sectors.values()):
        if sum(v for s,v in values.items() if sectors[s]==sector)/nav>=D('.4')-EPS:return 'SECTOR_LIMIT'
    return None
