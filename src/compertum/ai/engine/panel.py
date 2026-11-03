"""Portfolio-weight candidates on the 49 French industry portfolios (docs/PANEL_CANDIDATES_DESIGN.md, phase 1; owner approval 2 November 2026).

The firm's program sees two files with anonymous names (D1): panel_train.csv and panel_validation.csv, each with the columns
session, A01 ... A49 and rate. A session is the 0-based row number over TRAIN and VALIDATION together; a value is the industry's
total-return index level at that session's close, empty when the industry has no close; rate is that session's daily cash rate.
The program writes weights.csv with the header session,asset,weight. A listed session is a rebalance: the portfolio trades at that
session's close to the listed weights (long only, adding up to 1 or less, the rest in cash; a session listed only with asset CASH
holds all cash). A session that is not listed holds the previous positions, which drift with returns. Weights chosen at session t
earn the returns of t+1. The score is library_multi.score on the VALIDATION sessions against the equal-weight industries, with the
same honest rules as the library: cash rate, costs by era, drift turnover and the lag check.
"""
import math
import random
from compertum.runtime.errors import RuntimeRefused
from . import library_multi

ALIAS_SEED=20261102
CASH='CASH'
HEADER='session,asset,weight'
WEIGHTS_BYTES=4*1024*1024
WEIGHTS_ROWS=200000
SUM_SLACK=1e-9


def french_manifests(root):
    return [p.relative_to(root).as_posix() for p in sorted((root/'data'/'french').glob('*/manifest.json'))]


def asset_names(members):
    """The fixed anonymous name of each industry: A01 to A49 in an order drawn once from ALIAS_SEED."""
    order=random.Random(ALIAS_SEED).sample(sorted(members),len(members))
    return {symbol:f'A{i+1:02d}' for i,symbol in enumerate(order)}


def _cell(value):
    return '' if value is None else format(value,'.10g')


def panel_files(p,aliases):
    """The two input files of a panel job. They never hold a vault row: p comes from french_panel without with_vault."""
    names=sorted(aliases.values());real={a:s for s,a in aliases.items()};header='session,'+','.join(names)+',rate'
    def rows(start,end):
        return [f"{t},"+','.join(_cell(p['closes'][real[a]][t]) for a in names)+f",{_cell(float(p['rates'][t]))}" for t in range(start,end)]
    n=len(p['dates'])
    return {'panel_train.csv':'\n'.join([header]+rows(0,p['train']))+'\n','panel_validation.csv':'\n'.join([header]+rows(p['train'],n))+'\n'}


def parse_weights(text,p,aliases):
    """Admit a weights.csv. Returns one target dict per session (real industry names); sessions between rebalances share one dict,
    which is how library_multi.run_navs tells a hold from a trade. Any bad row refuses the whole file."""
    if not isinstance(text,str) or len(text.encode('utf-8'))>WEIGHTS_BYTES: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    lines=[line.strip() for line in text.strip().splitlines()]
    if not lines or lines[0].replace(' ','')!=HEADER or len(lines)-1>WEIGHTS_ROWS: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    real={a:s for s,a in aliases.items()};n=len(p['dates']);listed={}
    for line in lines[1:]:
        cells=[c.strip() for c in line.split(',')]
        if len(cells)!=3: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
        try: session=int(cells[0]);weight=float(cells[2])
        except ValueError: raise RuntimeRefused('ENGINE_SIGNALS_INVALID') from None
        asset=cells[1]
        if not 0<=session<n or not math.isfinite(weight) or weight<0: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
        targets=listed.setdefault(session,{})
        if asset==CASH: continue
        symbol=real.get(asset)
        if symbol is None or symbol in targets or symbol not in p['eligible'][session]: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
        if weight>0: targets[symbol]=weight
    if any(sum(t.values())>1+SUM_SLACK for t in listed.values()): raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    out=[];current={}
    for t in range(n):
        if t in listed: current=listed[t]
        out.append(current)
    return out


def panel_score(p,targets):
    """The VALIDATION score of the targets against the equal-weight industries, by the library's honest rules."""
    members=sorted(p['closes']);u=library_multi.prepare(p,members)
    if len(targets)!=u['n']: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    return library_multi.score(u,targets,p['train'],u['n'])


STARTER_PANEL='''"""Starter program for a portfolio specification. Edit decide(); keep the file names as they are.
Reads panel_train.csv and panel_validation.csv (session, A01..A49, rate) and writes weights.csv (session,asset,weight).
A listed session is a rebalance at that session's close; other sessions hold. Long only; weights add up to 1 or less; the rest is cash."""
import csv

REBALANCE=21


def load(name):
    with open(name,newline='',encoding='utf-8') as f:
        rows=list(csv.reader(f))
    return rows[0],rows[1:]


def decide(closes,t,assets):
    """Target weights at the close of session t. closes[a][s] is asset a's level at session s, or None; use only sessions up to t."""
    live=[a for a in assets if closes[a][t] is not None]
    return {a:1.0/len(live) for a in live} if live else {}


def main():
    header,train=load('panel_train.csv');_,validation=load('panel_validation.csv')
    assets=header[1:-1];rows=train+validation
    closes={a:[float(r[i+1]) if r[i+1] else None for r in rows] for i,a in enumerate(assets)}
    first=int(validation[0][0]);out=['session,asset,weight']
    for row in validation:
        t=int(row[0])
        if (t-first)%REBALANCE: continue
        weights=decide(closes,t,assets)
        out+=[f'{t},{a},{w!r}' for a,w in sorted(weights.items()) if w>0] or [f'{t},CASH,1']
    with open('weights.csv','w',encoding='utf-8') as f: f.write('\\n'.join(out)+'\\n')


main()
'''


PERTURB=(1,4,8)


def weight_rows(text):
    """The admitted rows of a weights.csv as sorted (session, asset, weight) tuples, for comparing two outputs."""
    lines=[line.strip() for line in (text or '').strip().splitlines()][1:]
    return sorted((int(c[0]),c[1].strip(),float(c[2])) for c in (line.split(',') for line in lines))


def perturbed_panel(p,k):
    """The panel with the closes of the last k sessions changed, each asset by its own factor (as library_multi.causal)."""
    n=len(p['dates'])
    def factor(j,t): return (0.85+0.3*((j*7)%11)/10)*(1-0.01*(t-n+k))
    closes={s:[c if c is None or t<n-k else c*factor(j,t) for t,c in enumerate(series)] for j,(s,series) in enumerate(sorted(p['closes'].items()))}
    return {**p,'closes':closes}


class PanelMarket:
    """The panel market kind: what the sandbox gets, what the program writes, how it is scored, and how the Auditor perturbs it."""
    kind='panel'
    output='weights.csv'

    def __init__(self,p):
        if p.get('universe')!='french49' or not p.get('train') or 'eligible' not in p: raise RuntimeRefused('ENGINE_MARKET_DENIED')
        self.p=p;self.aliases=asset_names(p['closes']);self.files=panel_files(p,self.aliases);self.n=len(p['dates'])

    def score(self,text):
        return panel_score(self.p,parse_weights(text,self.p,self.aliases))

    def perturbed_files(self,k):
        if not 1<=k<self.n-self.p['train']-1: raise RuntimeRefused('ENGINE_AUDIT_DENIED')
        return panel_files(perturbed_panel(self.p,k),self.aliases)

    def prefix_equal(self,original,changed,k):
        """True when every rebalance row before the changed tail is the same in both outputs, and the changed output is admitted."""
        q=perturbed_panel(self.p,k);parse_weights(changed,q,self.aliases);parse_weights(original,self.p,self.aliases)
        cut=self.n-k
        return [r for r in weight_rows(original) if r[0]<cut]==[r for r in weight_rows(changed) if r[0]<cut]

    def brief(self):
        from .tasks import panel_brief
        return panel_brief(self.p['train'],self.p['dates'][self.p['train']:],len(self.aliases))
