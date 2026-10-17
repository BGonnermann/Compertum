"""Real Windows lifecycle with the one admitted reserve and invented local USD fees."""
import json,os,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
import pytest

from compertum.runtime.errors import RuntimeRefused
from test_paper_activity_control import ROOT,control,output,stop,account,activity

RECORDS=ROOT/'artifacts/m5/posted-fees-20261017-01'
RECOVERY=ROOT/'artifacts/m5/native-fee-recovery-20261016-01'
EVIDENCE=RECORDS/'native-posted-fees'


def admitted_root():
    chosen=os.environ.get('COMPERTUM_RECONCILIATION_FIXTURE')
    assert chosen,'NATIVE_POSTED_FEE_CAPACITY_NOT_ADMITTED'
    root=Path(chosen)
    assert root==ROOT/'.cache/test-runs/native-fee-fresh-20261016-01/native-shared'
    admission=json.loads((RECORDS/'capacity-admission.json').read_text())['admission']
    assert admission['status']=='POSTED_FEE_INCREMENT_CAPACITY_ADMITTED' and admission['new_native_folders']==0
    saved=json.loads((RECOVERY/'fresh-native-fixture-result.json').read_text())
    assert saved['status']=='FRESH_NATIVE_FEE_FIXTURE_READY' and saved['fixture']==str(root)
    preserved=json.loads((RECORDS/'posted-native-preservation-before01.json').read_text())
    assert preserved['status']=='STOPPED_NATIVE_ORIGINALS_VERIFIED' and preserved['fixture']==str(root)
    closed=json.loads((RECORDS/'posted-native-preserve-before01.closure.json').read_text())
    assert closed['status']=='PASSED' and closed['exit_observed'] and closed['remaining_children']==0
    from compertum.runtime._windows import WindowsAPI
    from compertum.runtime.identity import resolve_project
    assert resolve_project(root).project_id==saved['project_id']==preserved['project_id']
    api=WindowsAPI()
    with api.open_file(root/'state/execution-reserve.bin',0x80,1) as handle:
        assert list(api.file_identity(handle))==saved['reserve_identity']==preserved['reserve_identity']
    assert not (root/'state/watchdog/halt.json').exists()
    assert (root/'config.toml').read_bytes()==(ROOT/'config/default.toml').read_bytes()
    lane='source' if str(Path(__import__('compertum').__file__)).startswith(str(ROOT/'src')) else 'installed'
    return root,lane


def launch(root):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    assert EVIDENCE.is_dir()
    token=str(uuid4());stdout=EVIDENCE/f'supervisor-{token}.stdout';stderr=EVIDENCE/f'supervisor-{token}.stderr'
    with stdout.open('xb') as out,stderr.open('xb') as err:
        p=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/paper_posted_fee_supervisor.py'),str(root),'restart'],
            executable=sys._base_executable,env=env,stdout=out,stderr=err,creationflags=0x08000000)
    p._fixture_stdout=stdout;p._fixture_stderr=stderr
    until=time.monotonic()+20
    while time.monotonic()<until:
        if p.poll() is not None:pytest.fail(output(p)[1].decode())
        try:
            value=control(root,'status',timeout=2);w=value.get('watchdog',{});e=w.get('owners',{}).get('execution',{})
            if w.get('mutual',{}).get('verified') and e.get('mutual',{}).get('verified'):return p,value
        except (RuntimeRefused,OSError):pass
        time.sleep(.05)
    p.kill();p.wait(timeout=5);pytest.fail('NATIVE_POSTED_FEE_START_TIMEOUT '+output(p)[1].decode())


def test_native_original_posted_fee_and_single_use():
    root,lane=admitted_root();receipt=EVIDENCE/f'{lane}-originals.json';assert not receipt.exists()
    p,initial=launch(root)
    try:
        reserve=initial['watchdog']['owners']['execution']['reserve']
        assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
        packet=account(root);identity=str(uuid4());prepared=activity(root,'prepare',activity_id=identity,packet_id=packet)
        for operation in ('authorize','start'):
            activity(root,operation,activity_id=identity,plan_sha256=prepared['plan_sha256'])
        until=time.monotonic()+30
        while time.monotonic()<until:
            observed=activity(root,'status',activity_id=identity)
            if observed['publication']['state']=='PUBLISHED' and observed.get('fixture_fee_phase')=='DONE':break
            time.sleep(.025)
        assert observed['publication']['state']=='PUBLISHED'
        result=observed['fixture_posted_fee']
        assert result['record_type']=='PaperPostedFeeContextDiagnostic' and result['status']=='BLOCKED'
        assert result['posted_fee_count']==result['posted_debit_count']==1 and result['posted_credit_count']==0
        assert result['cash_comparison']=='MATCHING_OBSERVED_CASH' and result['actual_billed_fee'] is None
        assert {'FEE_POSTING_INTERVAL_UNVERIFIED','FEE_LIABILITIES_UNVERIFIED'}<=set(result['unverified_requirements'])
        assert result['financial_accepted'] is result['transport_authorized'] is False
        assert observed['fixture_calculator_calls']>0 and observed['fixture_single_use_refused'] is True
        final=stop(root,p);assert len(final['requests'])==7 and final['real_account_calls']==0
        with receipt.open('x') as f:json.dump(dict(activity_id=identity,packet_id=packet,observed=observed,reserve=reserve,closure=final),f,indent=2)
    finally:
        if p.poll() is None:p.kill();p.wait(timeout=5)


def test_native_restart_does_not_restore_posted_fee_freshness():
    root,lane=admitted_root();previous=json.loads((EVIDENCE/f'{lane}-originals.json').read_text())
    p,_=launch(root)
    try:
        observed=activity(root,'status',activity_id=previous['activity_id'])
        assert observed['state']=='PUBLISHED'
        assert 'fixture_posted_fee_error' in observed and 'fixture_posted_fee' not in observed
        final=stop(root,p);assert final['requests']==[] and final['real_account_calls']==0
        with (EVIDENCE/f'{lane}-restart.json').open('x') as f:json.dump(dict(observed=observed,closure=final),f,indent=2)
    finally:
        if p.poll() is None:p.kill();p.wait(timeout=5)
