"""Economic-NAV metrics; undefined Sharpe is never infinity."""
from decimal import Decimal as D,localcontext
from compertum.data.errors import DataError
from .policy import number,fixed_decimal


@fixed_decimal
def metrics(navs,benchmark):
    if len(navs)!=len(benchmark) or len(navs)<2 or any(not isinstance(x,D) or not x.is_finite() or x<=0 for x in [*navs,*benchmark]):
        raise DataError('INVALID_NAV')
    with localcontext() as ctx:
        ctx.prec=28
        r=[b/a-1 for a,b in zip(navs,navs[1:])]
        b=[y/x-1 for x,y in zip(benchmark,benchmark[1:])]
        n=len(r);mean=sum(r)/n
        variance=sum((x-mean)**2 for x in r)/(n-1) if n>1 else None
        std=variance.sqrt() if variance is not None else None
        high=navs[0];drawdown=D(0)
        for nav in navs[1:]:
            high=max(high,nav);drawdown=max(drawdown,1-nav/high)
        return {'returns':list(map(number,r)),'benchmark_returns':list(map(number,b)),
            'annual_mean_excess':number(252*sum(x-y for x,y in zip(r,b))/n),
            'annual_volatility':number(D(252).sqrt()*std) if std is not None else None,
            'sharpe':number(D(252).sqrt()*mean/std) if std else None,
            'sharpe_status':'DEFINED' if std else 'UNDEFINED',
            'cagr':number((navs[-1]/navs[0])**(D(252)/n)-1),
            'max_drawdown':number(drawdown)}
