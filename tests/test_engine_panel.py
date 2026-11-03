"""Panel candidates, phase 1 (docs/PANEL_CANDIDATES_DESIGN.md): anonymous files, weights.csv, and scoring by the library's rules."""
from datetime import date,timedelta
import os
from pathlib import Path
import random
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from compertum.ai.engine import library_multi,panel  # noqa: E402
from compertum.runtime.errors import RuntimeRefused  # noqa: E402

SYMBOLS=['Agric','Food','Soda','Beer','Smoke','Toys','Fun']


def synthetic(n=320,train=200,seed=5,drift=0.0003):
    rng=random.Random(seed);day=date(1990,1,2);dates=[]
    while len(dates)<n:
        if day.weekday()<5: dates.append(day.isoformat())
        day+=timedelta(days=1)
    closes={}
    for j,s in enumerate(SYMBOLS):
        level=100.0;series=[]
        for t in range(n):
            level*=1+rng.gauss(drift*(j-3),0.012);series.append(None if s=='Fun' and t<60 else level)
        closes[s]=series
    eligible=[[s for s in sorted(closes) if closes[s][t] is not None] for t in range(n)]
    return {'dates':dates,'train':train,'closes':closes,'eligible':eligible,'rates':['0.0001']*n,'universe':'french49','vault':'french-v1'}


def rows_for(p,aliases,targets,sessions):
    out=[panel.HEADER]
    for t in sessions:
        chosen=[f'{t},{aliases[s]},{w!r}' for s,w in sorted(targets[t].items()) if w>0]
        out+=chosen or [f'{t},{panel.CASH},1']
    return '\n'.join(out)+'\n'


def test_asset_names():
    """Each industry gets a fixed anonymous name A01..An, the same every time."""
    names=panel.asset_names(SYMBOLS)
    assert names==panel.asset_names(list(reversed(SYMBOLS))) and sorted(names.values())==[f'A{i:02d}' for i in range(1,len(SYMBOLS)+1)]
    assert set(names)==set(SYMBOLS)


def test_panel_files():
    """Two files: TRAIN rows and VALIDATION rows, session numbers instead of dates, empty cells without a close, the cash rate last."""
    p=synthetic();aliases=panel.asset_names(SYMBOLS);files=panel.panel_files(p,aliases)
    train=files['panel_train.csv'].strip().splitlines();validation=files['panel_validation.csv'].strip().splitlines()
    assert train[0]==validation[0]=='session,'+','.join(sorted(aliases.values()))+',rate'
    assert len(train)-1==p['train'] and len(validation)-1==len(p['dates'])-p['train']
    assert train[1].startswith('0,') and validation[1].startswith(f"{p['train']},") and not any(d in files['panel_train.csv'] for d in p['dates'][:5])
    fun=sorted(aliases.values()).index(aliases['Fun'])+1
    assert train[1].split(',')[fun]=='' and train[61].split(',')[fun]!='' and train[1].endswith(',0.0001')


def test_weights_parse():
    """A listed session is a rebalance; other sessions share the previous target; CASH lists an all-cash rebalance."""
    p=synthetic();aliases=panel.asset_names(SYMBOLS);a=aliases
    text=f"session,asset,weight\n200,{a['Food']},0.5\n200,{a['Beer']},0.25\n210,CASH,1\n215,{a['Toys']},1.0\n"
    targets=panel.parse_weights(text,p,aliases)
    assert len(targets)==len(p['dates']) and targets[199]=={} and targets[200]=={'Food':0.5,'Beer':0.25}
    assert targets[209] is targets[200] and targets[210]=={} and targets[210] is not targets[200] and targets[319] is targets[215]=={'Toys':1.0}


@pytest.mark.parametrize('bad',['', 'session,weight\n200,0.5\n', 'session,asset,weight\nx,A01,0.5\n', 'session,asset,weight\n999,A01,0.5\n',
                                'session,asset,weight\n200,A99,0.5\n', 'session,asset,weight\n200,A01,-0.1\n', 'session,asset,weight\n200,A01,nan\n',
                                'session,asset,weight\n200,A01,0.7\n200,A02,0.4\n', 'session,asset,weight\n200,A01,0.5\n200,A01,0.2\n',
                                'session,asset,weight\n200,A01\n','session,asset,weight\n200,A01,0\n200,A01,0.5\n',
                                'session,asset,weight\n200,CASH,0.5\n','session,asset,weight\n200,A01,0.5\n200,CASH,1\n',
                                'session,asset,weight\n200,CASH,1\n200,A01,0.5\n'])
def test_weights_refused(bad):
    """Every malformed or illegal file is refused whole."""
    p=synthetic();aliases=panel.asset_names(SYMBOLS)
    with pytest.raises(RuntimeRefused,match='^ENGINE_SIGNALS_INVALID$'): panel.parse_weights(bad,p,aliases)


def test_weights_eligible():
    """No weight on an industry without a close at that session; size limits hold."""
    p=synthetic(train=40);aliases=panel.asset_names(SYMBOLS)
    with pytest.raises(RuntimeRefused,match='^ENGINE_SIGNALS_INVALID$'): panel.parse_weights(f"session,asset,weight\n45,{aliases['Fun']},0.5\n",p,aliases)
    assert panel.parse_weights(f"session,asset,weight\n61,{aliases['Fun']},0.5\n",p,aliases)[61]=={'Fun':0.5}
    with pytest.raises(RuntimeRefused,match='^ENGINE_SIGNALS_INVALID$'): panel.parse_weights('session,asset,weight\n'+'x'*(panel.WEIGHTS_BYTES),p,aliases)


@pytest.mark.parametrize('family,knobs',[('xs_momentum',{'lookback':20,'skip':0,'share':0.3,'hold':5}),('xs_low_vol',{'window':20,'share':0.3,'hold':21}),
                                         ('ew_trend',{'window':50,'hold':1})])
def test_library_equivalence(family,knobs):
    """A firm program that writes a library family's weights as weights.csv gets exactly the library's score for that family.
    The lag check shifts the weights by one session, so the program also lists its last rebalance before VALIDATION."""
    p=synthetic();aliases=panel.asset_names(SYMBOLS);members=sorted(p['closes']);u=library_multi.prepare(p,members)
    direct=library_multi.weights(u,family,knobs);start=p['train'];hold=knobs['hold']
    sessions=[max(t for t in range(start) if t%hold==0)]+[t for t in range(start,u['n']) if t%hold==0]
    targets=panel.parse_weights(rows_for(p,aliases,direct,sessions),p,aliases)
    assert panel.panel_score(p,targets)==library_multi.score(library_multi.prepare(p,members),direct,start,u['n'])


def test_starter_program(tmp_path):
    """The starter reads the two files and writes a weights.csv that the reader admits and the scorer scores."""
    p=synthetic();aliases=panel.asset_names(SYMBOLS)
    for name,text in panel.panel_files(p,aliases).items(): (tmp_path/name).write_text(text,encoding='utf-8')
    (tmp_path/'main.py').write_text(panel.STARTER_PANEL,encoding='utf-8')
    here=os.getcwd()
    try:
        os.chdir(tmp_path);exec(compile(panel.STARTER_PANEL,'main.py','exec'),{'__name__':'__main__'})
    finally: os.chdir(here)
    targets=panel.parse_weights((tmp_path/'weights.csv').read_text(encoding='utf-8'),p,aliases)
    assert targets[p['train']]=={s:1.0/len(SYMBOLS) for s in SYMBOLS} and targets[p['train']+1] is targets[p['train']]
    score=panel.panel_score(p,targets)
    assert score['sessions']==len(p['dates'])-p['train'] and score['sharpe_status']=='DEFINED' and score['turnover_per_year']!='0.0000'


def test_panel_brief():
    """The panel brief states files, sizes, the output format, long-only limits, costs by era, the benchmark and the gate, and no strategy."""
    from compertum.ai.engine.tasks import panel_brief
    p=synthetic();brief=panel_brief(p['train'],p['dates'][p['train']:],len(SYMBOLS))
    for fact in ('panel_train.csv (200 sessions)','panel_validation.csv (120 sessions)','A01 to A07','session,asset,weight','Long only','add up to 1 or less',
                 'equal weights, rebalanced daily','one session later','120 seconds per run','320 sessions and 7 assets'):
        assert fact in brief,fact
    assert brief.startswith('MARKET\n') and 'momentum' not in brief.lower() and 'reversal' not in brief.lower()


def peeking_rows(q,aliases,members,start,n,every,ahead):
    out=[panel.HEADER];c=q['closes']
    for t in range(start,n):
        if (t-start)%every: continue
        scores={s:c[s][min(t+ahead,n-1)]/c[s][t] for s in members if c[s][t] is not None}
        out.append(f"{t},{aliases[max(sorted(scores),key=lambda s:scores[s])]},1.0")
    return '\n'.join(out)+'\n'


def test_panel_audit():
    """The panel Auditor cuts at the candidate's own last rebalances: an honest rule keeps every row up to each cut; a rule that peeks
    one or two sessions ahead fails, also when it rebalances only every 21 sessions (review, 2 November 2026)."""
    p=synthetic();market=panel.PanelMarket(p);members=sorted(p['closes']);n=len(p['dates']);start=p['train'];aliases=market.aliases
    u=library_multi.prepare(p,members)
    def honest(q):
        w=library_multi.weights(library_multi.prepare(q,members),'xs_momentum',{'lookback':20,'skip':0,'share':0.3,'hold':21})
        return rows_for(q,aliases,w,[t for t in range(start,n) if t%21==0])
    cuts=market.audit_cuts(honest(p));assert len(cuts)==3 and all(1<=k<=n-start-1 for k in cuts)
    assert [n-k-1 for k in cuts]==sorted({int(r.split(',')[0]) for r in honest(p).splitlines()[1:]},reverse=True)[:3]
    assert all(market.prefix_equal(honest(p),honest(panel.perturbed_panel(p,k)),k) for k in cuts)
    for every,ahead in ((1,1),(21,2),(21,3),(5,1)):
        original=peeking_rows(p,aliases,members,start,n,every,ahead);cuts=market.audit_cuts(original)
        caught=[not market.prefix_equal(original,peeking_rows(panel.perturbed_panel(p,k),aliases,members,start,n,every,ahead),k) for k in cuts]
        assert any(caught),(every,ahead,caught)
    for k in (1,4,30):
        q=panel.perturbed_panel(p,k)
        assert all(q['closes'][s][:n-k]==p['closes'][s][:n-k] for s in members)
        assert all(q['closes'][s][n-k]!=p['closes'][s][n-k] for s in members if p['closes'][s][n-k] is not None)
    assert market.same_output('session,asset,weight\n200,A01,0.5\n200,A02,0.5\n','session,asset,weight\n200,A02,0.5\n200,A01,0.5\n')
    assert market.audit_cuts('session,asset,weight\n')==[1] and market.score(honest(p))['sessions']==u['n']-start
    with pytest.raises(RuntimeRefused,match='^ENGINE_AUDIT_DENIED$'): market.perturbed_files(0)
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): panel.PanelMarket({**p,'universe':'other'})


def test_panel_prompts():
    """Panel runs get panel variants of the Engineer and Mathematician prompts; the single-asset prompts stay as they are."""
    from compertum.ai.engine.prompts import load_prompt
    root=Path(__file__).resolve().parents[1]
    for role in panel.PANEL_ROLES:
        text=load_prompt(root,role,'panel');assert text.startswith(f'ROLE: {role}\n') and 'signals.csv' not in text and 'position in {0, 1}' not in text
        assert load_prompt(root,role)!=text
    assert 'weights.csv' in load_prompt(root,'engineer','panel') and 'signals.csv' in load_prompt(root,'engineer')
    with pytest.raises(RuntimeRefused,match='^ENGINE_PROMPT_INVALID$'): load_prompt(root,'engineer','other')
