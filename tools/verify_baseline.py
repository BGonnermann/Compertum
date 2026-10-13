"""Foreground synthetic source/wheel reproduction. No provider or runtime calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import compertum
from compertum.data.snapshot import canonical
from compertum.simulation import replay
from compertum.simulation.market import WATCHLIST
from compertum.storage import CAPS,sample_storage
from compertum.runtime.identity import resolve_project


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--installed',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=Path(args.output).resolve();scratch=root/'.cache/test-runs'
    if not output.is_relative_to(scratch) or output==scratch or output.exists():raise RuntimeError('FRESH_SCRATCH_REQUIRED')
    package=Path(compertum.__file__).resolve()
    if args.installed and not package.is_relative_to(Path(sys.prefix).resolve()):raise RuntimeError('NOT_INSTALLED_PACKAGE')
    storage=sample_storage(resolve_project(root))
    if any(storage['categories'][k]>cap for k,cap in CAPS.items()) or storage['categories']['scratch']+64*1024*1024>CAPS['scratch']:
        raise RuntimeError('STORAGE_CAPACITY')
    sys.path.insert(0,str(root/'tests'))
    from helpers.simulation_fixture import fixture
    symbols=WATCHLIST+('SPY',);sectors={s:'fixture-'+str(i//2) for i,s in enumerate(symbols)}
    chunks,start,end,_=fixture(symbols)
    output.mkdir(parents=True,exist_ok=False)
    written=0
    def save(name,content):
        nonlocal written
        if written+len(content)>64*1024*1024:raise RuntimeError('OUTPUT_BOUND')
        with (output/name).open('xb') as stream:stream.write(content)
        written+=len(content)
    inputs=[]
    for i,chunk in enumerate(chunks):
        name=f'input-{i:02}.json';save(name,chunk.content)
        inputs.append({'path':name,'sha256':chunk.sha256})
    runs=[]
    for cost in (10,20):
        for horizon in (1,5,21):
            result=replay(chunks,sectors,start,end,horizon,cost_bps=cost)
            value=json.loads(result.content)
            assert value['financial_status']=='SYNTHETIC_UNVERIFIED'
            assert all(not p['days'][-1]['positions'] for p in value['portfolios'].values())
            name=f'h{horizon}-cost{cost}.json';save(name,result.content)
            runs.append({'horizon':horizon,'cost_bps':cost,'path':name,'sha256':result.sha256})
    receipt={'status':'SYNTHETIC_REPRODUCTION_COMPLETE','python':sys.version.split()[0],
        'package_path':str(package),'installed':args.installed,'inputs':inputs,'runs':runs,
        'fingerprint':hashlib.sha256(canonical(runs)).hexdigest(),'written_bytes':written,
        'start':start,'end':end,'sessions':44,'sectors':sectors,
        'financial_acceptance':'UNVERIFIED','source_and_wheel_comparison':'PENDING'}
    save('result.json',canonical(receipt));print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
