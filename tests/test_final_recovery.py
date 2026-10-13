"""Owner recovery with simulated process observations; no native acceptance."""
from datetime import datetime,timezone
from copy import deepcopy
import pytest
from test_final_dispatch import dispatch,owned,pair_inputs,environment,native
from test_final_completion import start
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.final_completion import record_exit
from compertum.evaluation_seals import verify_seal_journal


def observation(n):
 return dict(schema='final-root-exit-v1',process=deepcopy(n['process']),status='VERIFIED_ABSENT',observed_at=datetime.now(timezone.utc).isoformat(),observed_creation_filetime=None,wait_result=None)


def test_owner_loss_exhausts_once_without_exit_receipt(dispatch,monkeypatch):
 import compertum.final_completion as module
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch)
 monkeypatch.setattr(module,'observe_exited',observation)
 command=dict(operation='abandon_final',seal_id=d['seal_id'],attempt_id=d['attempt']['attempt_id'])
 done=seals.handle(command);saved=verify_seal_journal(seals.project)
 assert done['status']=='EXHAUSTED' and done['charged_ms']==120000 and done['result']['publication'] is None
 closed=saved['seals'][d['seal_id']]['final_attempts'][-1]['close']
 assert closed['operation']=='ABANDON_FINAL_BATCH' and 'job_receipt' not in closed
 def unavailable(n):raise RuntimeRefused('FINAL_PROCESS_EXIT_UNVERIFIED')
 monkeypatch.setattr(module,'observe_exited',unavailable)
 assert seals.handle(command)==done and verify_seal_journal(seals.project)['sequence']==saved['sequence']


@pytest.mark.parametrize('fault',['live','unknown','wrong_process','saved_exit','no_start','caller_proof'])
def test_unsafe_abandonment_refused_without_journal_write(dispatch,monkeypatch,fault):
 import compertum.final_completion as module
 runs,seals,p,d,task,out=dispatch
 if fault!='no_start':n,r=start(dispatch,monkeypatch)
 else:n=native(seals,d['seal_id'],d)
 def observe(n):
  if fault in ('live','unknown'):raise RuntimeRefused('FINAL_PROCESS_STILL_LIVE' if fault=='live' else 'FINAL_PROCESS_EXIT_UNVERIFIED')
  proof=observation(n)
  if fault=='wrong_process':proof['process']['pid']+=1
  return proof
 monkeypatch.setattr(module,'observe_exited',observe)
 if fault=='saved_exit':r['exit_code']=4;record_exit(runs,d,r)
 command=dict(operation='abandon_final',seal_id=d['seal_id'],attempt_id=d['attempt']['attempt_id'])
 if fault=='caller_proof':command['process_exit']=observation(n)
 before=canonical(verify_seal_journal(seals.project))
 with pytest.raises(RuntimeRefused):seals.handle(command)
 assert canonical(verify_seal_journal(seals.project))==before


@pytest.mark.parametrize('native_saved',[False,True])
def test_preparation_recovery_is_explicit_and_never_reprepares(dispatch,monkeypatch,native_saved):
 import compertum.final_completion as module
 from compertum.review_evidence import sha
 from compertum.data.errors import DataError
 runs,seals,p,d,task,out=dispatch;n=native(seals,d['seal_id'],d)
 if native_saved:
  committed=deepcopy(d);committed['attempt']['native_execution']=n;raw=canonical(committed)
  with runs.store.conn:runs.store.conn.execute('UPDATE final_dispatches SET body=?,sha256=? WHERE attempt_id=?',(raw.decode(),sha(raw),d['attempt']['attempt_id']))
 monkeypatch.setattr(module,'observe_exited',observation)
 command=dict(operation='abandon_final_preparation',seal_id=d['seal_id'],attempt_id=d['attempt']['attempt_id'])
 done=seals.handle(command);saved=verify_seal_journal(seals.project)
 assert done['status']=='INVALIDATED' and done['price_reads']==0 and done['result'] is None
 assert saved['seals'][d['seal_id']]['invalidation']['operation']=='ABANDON_FINAL_PREPARATION'
 assert not saved['seals'][d['seal_id']].get('final_attempts')
 assert seals.handle(command)==done and verify_seal_journal(seals.project)['sequence']==saved['sequence']
 with pytest.raises((DataError,RuntimeRefused)):runs.prepare(d['seal_id'],now=datetime.now(timezone.utc))



def test_recovery_requires_terminal_closure_and_lost_preparation_dispatch(dispatch,monkeypatch):
 from compertum.final_completion import propose_close,close_through_owner
 from compertum.recovery_lineage import validate_dispatch_links
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);r['exit_code']=4;record_exit(runs,d,r)
 pin=propose_close(runs,d,'REJECTED');close_through_owner(runs,d,pin,evaluation=seals)
 row=verify_seal_journal(seals.project)['seals'][d['seal_id']];validate_dispatch_links(runs.store.conn,d['seal_id'],row)
 with runs.store.conn:runs.store.conn.execute('DELETE FROM final_closures')
 with pytest.raises((RuntimeRefused,__import__('compertum.data.errors',fromlist=['DataError']).DataError)):validate_dispatch_links(runs.store.conn,d['seal_id'],row)


def test_pre_start_rows_cannot_be_erased_by_older_snapshot(dispatch):
 import sqlite3
 from compertum.recovery import _preserved_final_evidence
 from compertum.recovery_lineage import final_evidence,final_evidence_prefix
 runs,seals,p,d,task,out=dispatch;older=sqlite3.connect(':memory:')
 assert _preserved_final_evidence(seals.project,older) is False
 before=final_evidence(runs.store.conn);later=deepcopy(before);aid=d['attempt']['attempt_id'];later['final_dispatches'][aid]['attempt']['native_execution']=native(seals,d['seal_id'],d)
 assert final_evidence_prefix(before,later) is True and final_evidence_prefix(later,before) is False
 command=dict(operation='abandon_final_preparation',seal_id=d['seal_id'],attempt_id=aid);seals.handle(command)
 from compertum.recovery_lineage import validate_dispatch_links
 row=verify_seal_journal(seals.project)['seals'][d['seal_id']];validate_dispatch_links(runs.store.conn,d['seal_id'],row)
 with runs.store.conn:runs.store.conn.execute('DELETE FROM final_dispatches')
 with pytest.raises(RuntimeRefused):validate_dispatch_links(runs.store.conn,d['seal_id'],row)
