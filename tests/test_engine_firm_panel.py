"""The firm-panel vault route (panel design, phase 4): frozen code by hash, a VALIDATION reproduction before any vault read, vault rows only
inside a counted look, only vault sessions scored, and no vault file left in the job folder. Fixture prices are generated inside the test."""
import hashlib
from pathlib import Path
import pytest
from test_ai_manual import bridge  # noqa: F401  (fixture)
from test_engine_roles import FLOOR,root,verification  # noqa: F401  (fixtures)
from test_engine_panel import synthetic
from compertum.events import canonical
from compertum.ai.engine import firm_panel,library_multi
from compertum.ai.engine.execution import DATA_TIERS,EngineerSandbox
from compertum.ai.engine.ledger import EngineLedger
from compertum.ai.engine.panel import PanelMarket
from compertum.ai.engine.promotion import promote,promoted_folder
from compertum.ai.engine.vault import CandidateQueue
from compertum.runtime.errors import RuntimeRefused

PROGRAM='''import csv
def load(name):
    with open(name,newline='',encoding='utf-8') as f: rows=list(csv.reader(f))
    return rows[0],rows[1:]
header,train=load('panel_train.csv');_,validation=load('panel_validation.csv');assets=header[1:-1];first=int(validation[0][0]);out=['session,asset,weight']
for row in validation:
    t=int(row[0])
    if (t-first)%21: continue
    live=[a for i,a in enumerate(assets) if row[i+1]]
    out+=[f'{t},{a},{1/len(live)!r}' for a in live]
with open('weights.csv','w',encoding='utf-8') as f: f.write('\\n'.join(out)+'\\n')
'''


def cut(full,n):
    return {**full,'dates':full['dates'][:n],'closes':{s:c[:n] for s,c in full['closes'].items()},'eligible':full['eligible'][:n],'rates':full['rates'][:n]}


@pytest.fixture
def setup(bridge,root,verification,monkeypatch):
    b,project=bridge;ledger=EngineLedger(b.store);full=synthetic(n=380,train=200);seen=cut(full,320)
    flags={'blocked':False}
    def panel(root_,manifests,with_vault=False):
        if with_vault and flags['blocked']: raise AssertionError('vault rows read')
        return full if with_vault else seen
    monkeypatch.setattr(library_multi,'french_panel',panel)
    market=PanelMarket(seen)
    sandbox=EngineerSandbox(root,ledger=ledger,lease=b.storage.lease,verification=verification,cycle_id='cycle-firm-panel',train_csv=market.files['panel_train.csv'],
                            validation_csv=market.files['panel_validation.csv'],memory_floor_bytes=FLOOR,layout='panel')
    return project,ledger,market,sandbox,flags


def queued(project,ledger,market,sandbox,cid):
    files={'main.py':PROGRAM};run=sandbox.run({'/main.py':PROGRAM},'main.py');assert run['signals_present'],run
    score=market.score(sandbox.runs[-1]['signals'])
    promote(project,cid,files,audit={'label':'VERIFIED_PASS'},score=score,deflation={},source_job_folder='fixture')

    ledger.record_queue_event(cid,'ELIGIBLE',{'score_sha256':hashlib.sha256(canonical(score)).hexdigest(),'route':firm_panel.route_record(market,files,'main.py'),
                                              'vault':'french-v1','quarter':'2026-Q4','deflation':{}})
    ledger.record_queue_event(cid,'QUEUED',{'quarter':'2026-Q4','vault':'french-v1'})
    return CandidateQueue(ledger).open_batch([cid],'Owner OK: fixture batch',vault='french-v1')


def test_vault_route(setup):
    """The frozen program reproduces its VALIDATION score, then runs once with the vault sessions; only those 60 sessions are scored."""
    project,ledger,market,sandbox,_=setup
    look=queued(project,ledger,market,sandbox,'cycle-0001-aaaaaaaa:h1')
    event=firm_panel.vault_score(CandidateQueue(ledger),look['look_id'],'cycle-0001-aaaaaaaa:h1',project_root=project,manifests=[],sandbox=sandbox)
    assert event['event']=='VAULT_EVALUATED' and event['status']=='SCORED' and event['result']['sessions']==60
    vault_run=sandbox.runs[-1];assert vault_run['purpose']=='vault' and not any((Path(vault_run['job_folder'])/name).exists() for name in DATA_TIERS)
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_REPEAT$'):
        firm_panel.vault_score(CandidateQueue(ledger),look['look_id'],'cycle-0001-aaaaaaaa:h1',project_root=project,manifests=[],sandbox=sandbox)


def test_vault_refusals(setup):
    """A changed frozen file, or other input files, refuse before any vault row is read; the candidate stays counted and unevaluated."""
    project,ledger,market,sandbox,flags=setup;cid='cycle-0002-aaaaaaaa:h1'
    look=queued(project,ledger,market,sandbox,cid);flags['blocked']=True
    (promoted_folder(project,cid)/'main.py').write_text(PROGRAM+'\n',encoding='utf-8')
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'):
        firm_panel.vault_score(CandidateQueue(ledger),look['look_id'],cid,project_root=project,manifests=[],sandbox=sandbox)
    assert CandidateQueue(ledger).state(cid)[0]=='LOOK_COUNTED'
    (promoted_folder(project,cid)/'main.py').write_text(PROGRAM,encoding='utf-8',newline='\n')
    sandbox.validation_csv=sandbox.validation_csv+'\n'
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'):
        firm_panel.vault_score(CandidateQueue(ledger),look['look_id'],cid,project_root=project,manifests=[],sandbox=sandbox)
    assert CandidateQueue(ledger).state(cid)[0]=='LOOK_COUNTED'


def test_vault_command(tmp_path,capsys):
    """The owner command refuses below the memory floor before it takes the lease or reads any file."""
    assert firm_panel.main(['--project',str(tmp_path),'vault','--look','look-x','--candidate','c1'],available_memory=lambda:1)==2
    assert '"refused": "AVAILABLE_RAM_FLOOR"' in capsys.readouterr().out
