"""Bounded synthetic prediction-report reproduction in a fresh evidence directory."""
import argparse,hashlib,json,sys
from decimal import Decimal as D
from pathlib import Path
import compertum
from compertum.data.calendar import session_times
from compertum.data.snapshot import canonical
from compertum.simulation.market import WATCHLIST
from compertum.simulation.prediction import score_predictions
from compertum.storage import sample_storage,CAPS
from compertum.runtime.identity import resolve_project


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--installed',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];output=Path(args.output).resolve()
    scratch=root/'.cache/test-runs'
    if output==scratch or not output.is_relative_to(scratch) or output.exists():raise RuntimeError('FRESH_SCRATCH_REQUIRED')
    if args.installed and not Path(compertum.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):raise RuntimeError('NOT_INSTALLED_PACKAGE')
    s=sample_storage(resolve_project(root))
    if any(s['categories'][k]>cap for k,cap in CAPS.items()) or s['categories']['scratch']+32*1024**2>CAPS['scratch']:raise RuntimeError('STORAGE_CAPACITY')
    sys.path.insert(0,str(root/'tests'))
    from helpers.simulation_fixture import fixture,changed
    symbols=WATCHLIST+('SPY',);chunks,start,end,dates=fixture(symbols)
    # Invent a visibly nonconstant future-price path. These are never market observations.
    def edit(value):
        symbol=value['assets'][0]['symbol'];factor=symbols.index(symbol)+1
        for b in value['bars']:
            if b['reference']=='entry' and b['session_date']>=start:
                n=dates.index(b['session_date'])-252;price=D(100)+D(n)*factor/100
                for k in ('open','high','low','close'):b[k]=format(price,'f')
    chunks=changed(chunks,edit);sectors={s:'fixture-'+str(i//2) for i,s in enumerate(symbols)}
    cutoff=session_times(session_times(end).next_date).decision.isoformat();output.mkdir(parents=True,exist_ok=False)
    used=0
    def save(name,raw):
        nonlocal used
        if used+len(raw)>32*1024**2:raise RuntimeError('OUTPUT_BOUND')
        with (output/name).open('xb') as f:f.write(raw)
        used+=len(raw)
    inputs=[]
    for index,chunk in enumerate(chunks):
        name=f'input-{index:02}.json';save(name,chunk.content);inputs.append({'path':name,'sha256':chunk.sha256})
    reports=[]
    for horizon in (1,5,21):
        result=score_predictions(chunks,sectors,start,end,horizon,scoring_as_of=cutoff)
        name=f'h{horizon}.json';save(name,result.content)
        reports.append({'horizon':horizon,'path':name,'sha256':result.sha256})
    receipt={'status':'SYNTHETIC_REPRODUCTION_COMPLETE','inputs':inputs,'reports':reports,
        'fingerprint':hashlib.sha256(canonical(reports)).hexdigest(),'written_bytes':used,
        'python':sys.version.split()[0],'package_path':str(Path(compertum.__file__).resolve()),
        'financial_acceptance':'UNVERIFIED','source_wheel_comparison':'PENDING'}
    save('result.json',canonical(receipt));print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
