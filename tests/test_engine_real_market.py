import hashlib
import json
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from test_provider_snapshot import build,encode,envelopes  # noqa: F401
from test_engine_bench import fake_run,project  # noqa: F401
from compertum.ai.engine import practice
from compertum.ai.engine.real_market import load_market_manifest,load_snapshot,provider_market
from compertum.runtime.errors import RuntimeRefused

PROJECT=Path(__file__).resolve().parents[1]


def evidence_project(tmp_path,envelopes,snapshot=None,evidence_values=None):
    folder=tmp_path/'evidence';folder.mkdir();snapshot=snapshot or build(envelopes)
    (folder/'snapshot.json').write_bytes(snapshot.content)
    records=[];values=envelopes if evidence_values is None else evidence_values
    for index,value in enumerate(values):
        raw=encode(value);path=folder/f'chunk-{index}.json';path.write_bytes(raw)
        records.append({'path':f'evidence/chunk-{index}.json','sha256':hashlib.sha256(raw).hexdigest()})
    manifest={'schema_version':'1','symbol':'AAPL','snapshot':{'path':'evidence/snapshot.json','sha256':hashlib.sha256(snapshot.content).hexdigest()},'evidence':records}
    (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return tmp_path,'evidence/manifest.json',snapshot


def test_manifest_revalidates_evidence_and_builds_a_development_market(tmp_path,envelopes):
    root,path,snapshot=evidence_project(tmp_path,envelopes)
    loaded, symbol=load_snapshot(root,path)
    assert loaded==snapshot and symbol=='AAPL'
    market,vault=provider_market(loaded,symbol,sessions=50)
    assert len(market['validation_rows'])==15 and len(vault)==10 and market['vault_sessions']==10
    assert all(float(row['return'])==0 for row in market['validation_rows'])
    assert market['validation_rows']==sorted(market['validation_rows'],key=lambda r:r['session'])
    assert market['provenance']['snapshot_sha256']==snapshot.sha256 and market['provenance']['financial_accepted'] is False
    assert 'ACTION_COVERAGE_AND_KNOWLEDGE' in market['provenance']['pending']
    assert 'validation_csv' in market and 'vault_csv' not in market


def test_changed_missing_and_incomplete_inputs_are_refused(tmp_path,envelopes):
    root,path,snapshot=evidence_project(tmp_path,envelopes)
    manifest_path=root/'evidence/manifest.json';manifest=json.loads(manifest_path.read_text())
    manifest['snapshot']['sha256']='0'*64;manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_SNAPSHOT_CHANGED$'): load_snapshot(root,path)
    manifest=json.loads(manifest_path.read_text());manifest['snapshot']['sha256']=snapshot.sha256;manifest['evidence'][0]['sha256']='0'*64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_EVIDENCE_CHANGED$'): load_snapshot(root,path)
    manifest['evidence'][0]['sha256']=hashlib.sha256((root/'evidence/chunk-0.json').read_bytes()).hexdigest();manifest_path.write_text(json.dumps(manifest))
    (root/'evidence/chunk-0.json').unlink()
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_INPUT_UNAVAILABLE$'): load_snapshot(root,path)


def test_incomplete_coverage_is_never_filled(tmp_path,envelopes):
    snapshot=build(envelopes[:-1])
    root,path,_=evidence_project(tmp_path,envelopes,snapshot=snapshot,evidence_values=envelopes[:-1])
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_COVERAGE_INCOMPLETE$'): load_snapshot(root,path)
    with pytest.raises(RuntimeRefused,match='^PROVIDER_SNAPSHOT_CORRUPT$'): provider_market(replace(snapshot,sha256='0'*64),'AAPL',sessions=50)


def test_practice_accepts_a_verified_manifest_and_records_provenance(tmp_path,envelopes,monkeypatch):
    root=tmp_path/'project';root.mkdir();root=project(root);_,path,snapshot=evidence_project(root,envelopes);seen={}
    def fake_run(**kwargs):
        seen.update(kwargs)
        return {'run_id':'run-20261027-0123abcd','reason':'CYCLE_LIMIT','cycles':[],'requests':0,'elapsed_seconds':0,'summary_path':'s.md','models':{}}
    monkeypatch.setitem(sys.modules,'compertum.ai.engine.run',SimpleNamespace(run_bounded=fake_run))
    record=practice.run_practice(root,root/'config.toml',cycles=1,hours=None,requests=40,note='real market fixture',sessions=50,
                                 market_manifests=[path],available_memory=lambda:practice.START_FLOOR+1)
    assert seen['market']['provenance']['snapshot_sha256']==snapshot.sha256 and seen['schedule'] is None
    assert seen['transcript_training_allowed'] is False
    assert record['market_provenance'][0]['financial_accepted'] is False and record['vault_sessions_held_back']==10


def test_gepa_accepts_multiple_manifests_without_training_on_them(tmp_path,envelopes,monkeypatch):
    root=tmp_path/'project';root.mkdir();root=project(root);_,path,_=evidence_project(root,envelopes);seen={}
    def fake_gepa(**kwargs):
        seen.update(kwargs)
        return {'run_id':'run-20261027-0123abcd','reason':'CYCLE_LIMIT','cycles':[],'requests':0,'elapsed_seconds':0,'summary_path':'s.md','models':{}}
    monkeypatch.setitem(sys.modules,'compertum.ai.engine.gepa_run',SimpleNamespace(MAX_MARKETS=8,run_gepa=fake_gepa))
    record=practice.run_practice(root,root/'config.toml',cycles=2,hours=None,requests=40,note='real GEPA fixture',sessions=50,gepa=True,
                                 market_manifests=[path,path],available_memory=lambda:practice.START_FLOOR+1)
    assert len(seen['markets'])==2 and seen['transcript_training_allowed'] is False
    assert record['kind']=='gepa' and record['vault_sessions_held_back']==20


def test_bench_and_holdout_refuse_manifests_before_the_lease(tmp_path,fake_run):
    for purpose in ('bench','holdout'):
        with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_PURPOSE_DENIED$'):
            practice.run_practice(tmp_path,tmp_path/'missing.toml',cycles=None,hours=None,requests=10,note='x',purpose=purpose,
                                  market_manifests=['evidence/manifest.json'],available_memory=lambda:practice.START_FLOOR+1)
    assert not (tmp_path/'state/locks').exists() and fake_run=={}


def test_command_line_forwards_real_market_manifests(tmp_path,monkeypatch):
    seen={}
    def fake(root,config,**kwargs): seen.update(kwargs);return {'kind':'cycles'}
    monkeypatch.setattr(practice,'run_practice',fake)
    assert practice.main(['--project',str(tmp_path),'gepa','--cycles','2','--requests','10','--note','n','--market-manifest','one.json','--market-manifest','two.json'])==0
    assert seen['market_manifests']==['one.json','two.json']
    wrapper=(PROJECT/'tools/practice.ps1').read_text(encoding='utf-8')
    assert "@('--market-manifest',$manifest)" in wrapper and '$evaluationMode -and $MarketManifest.Count -gt 0' in wrapper
