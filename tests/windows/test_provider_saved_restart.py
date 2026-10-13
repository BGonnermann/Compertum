"""Native provider evidence survives real owner exits with no duplicate accepted units."""
from pathlib import Path
from uuid import uuid4
import hashlib,json
import pytest
from test_provider_replay import snapshot,envelopes,scenario
from test_saved_run_restart import child
from compertum.simulation.provider_replay import replay_provider
ROOT=Path(__file__).parents[2]

def prepare(root,snapshot,s):
 (root/'config.toml').write_bytes((ROOT/'config/default.toml').read_bytes())
 (root/'provider-fixture-inputs.json').write_text(json.dumps({'start':snapshot.start,'end':snapshot.end,'evidence_utf8':[c.content.decode('utf-8') for c in snapshot.evidence],'scenario_utf8':s.content.decode('utf-8')}),encoding='utf-8')

@pytest.mark.parametrize('crash,code',[('crash_before_compute',74),('crash_after_publish',73),('crash_after_write',75)])
def test_provider_real_owner_exit_pause_resume_and_exact_completion(tmp_path,snapshot,crash,code):
 s=scenario(snapshot);prepare(tmp_path,snapshot,s);run=str(uuid4())
 first=child(tmp_path,run,'create_provider');child(tmp_path,run,'resume');child(tmp_path,run,crash,code)
 state=child(tmp_path,run,'status');assert state['generation']>first['generation']
 assert state['result']['state']=='INTERRUPTED' and state['result']['completed_units']==0
 assert state['result']['input_kind']=='provider-diagnostic'
 orphan={p:p.read_bytes() for p in (tmp_path/f'artifacts/runs/{run}/baseline').glob('unit-*.json')}
 child(tmp_path,run,'resume');child(tmp_path,run,'step');child(tmp_path,run,'pause')
 assert child(tmp_path,run,'status')['result']['state']=='PAUSED'
 done=child(tmp_path,run,'finish')['result'];assert done['state']=='COMPLETED' and len(done['attempts'])==7
 for row in done['results']:
  expected=replay_provider(snapshot,s,row['horizon'],cost_bps=row['cost_bps'])
  assert (tmp_path/row['artifact']['path']).read_bytes()==expected.content
 assert all(p.read_bytes()==raw for p,raw in orphan.items())


def test_provider_stop_survives_new_owner_without_replay(tmp_path,snapshot):
 prepare(tmp_path,snapshot,scenario(snapshot));run=str(uuid4());child(tmp_path,run,'create_provider');child(tmp_path,run,'resume');child(tmp_path,run,'step')
 stopped=child(tmp_path,run,'stop')['result'];restored=child(tmp_path,run,'status')['result']
 assert restored==stopped and restored['state']=='STOPPED' and restored['completed_units']==1