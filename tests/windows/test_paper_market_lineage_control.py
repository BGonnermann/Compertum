"""Actual Windows lineage channels, full reserve and ACK-only process restart."""
import json,shutil,time
from uuid import uuid4
import pytest
from compertum.runtime.supervisor import control
from compertum.runtime.errors import RuntimeRefused
from test_paper_market_control import ROOT,capture,launch,stop,call,begin,wait


def wait_lineage(root,cid,predicate):
 end=time.monotonic()+20;request_id=str(uuid4())
 while time.monotonic()<end:
  result=control(root,'paper_market_read',dict(operation='lineage_status',capture_id=cid),request_id=request_id)
  if predicate(result):return result
  time.sleep(.05)
 raise AssertionError('Lineage state not reached: '+json.dumps(result))


def test_actual_lineage_capture_lost_ack_and_both_owner_restarts(tmp_path):
 from compertum.paper_market_inputs import prepare_market_plan
 from compertum.runtime.identity import resolve_project
 plan=prepare_market_plan(project_id=resolve_project(tmp_path).project_id,account_alias='fixture',symbol='MSFT',session_date='2023-11-24',created_at='2023-11-24T14:00:00+00:00').to_payload()
 rows=[dict(t=t,o=100,h=102,l=99,c=100.125,v=20000) for t in plan['daily_labels']]
 (tmp_path/'market-fixture-rows.json').write_text(json.dumps(rows))
 shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');p,initial=launch(tmp_path,'collect')
 try:
  execution=initial['watchdog']['owners']['execution'];reserve=execution['reserve'];first_generation=execution['generation']
  assert reserve['capacity_bytes']==reserve['unused_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
  history=call(tmp_path,'prepare',job_id=str(uuid4()),account_alias='fixture',mode='HISTORY',symbol='MSFT',history_job_id=None)
  with pytest.raises(RuntimeRefused,match='MARKET_GRANT_REQUIRED'):call(tmp_path,'start',job_id=history['job_id'],grant_sha256=history['grant_sha256'])
  begin(tmp_path,history)
  published=wait(tmp_path,history['job_id'],lambda r:r['publication']['state']=='FAILED')
  assert published['state']=='PUBLISHED' and published['publication']['reason']=='FIXTURE_ACK_REPLY_LOST'
  assert published['manifest']==published['publication']['manifest'] and published['evidence']['size_bytes']>32768
  first=stop(tmp_path,p);assert len(first['requests'])==3 and first['lost_ack_receipts']==1
  p,second_initial=launch(tmp_path,'fresh');second_generation=second_initial['watchdog']['owners']['execution']['generation'];assert second_generation>first_generation
  recovered=wait(tmp_path,history['job_id'],lambda r:r['publication']['state']=='PUBLISHED')
  assert recovered['manifest']==published['manifest'] and control(tmp_path,'status')['fixture_requests']==[]
  assert call(tmp_path,'start',job_id=history['job_id'],grant_sha256=history['grant_sha256'])['state']=='PUBLISHED'
  assert control(tmp_path,'status')['fixture_requests']==[]
  fresh=call(tmp_path,'prepare',job_id=str(uuid4()),account_alias='fixture',mode='FRESH',symbol='MSFT',history_job_id=history['job_id'])
  assert fresh['plan']==history['plan'];begin(tmp_path,fresh)
  complete=wait(tmp_path,fresh['job_id'],lambda r:r['state']=='COMPLETE');assert complete['evidence'] is complete['manifest'] is None
  cid=str(uuid4());capture_request=call(tmp_path,'publish_lineage',capture_id=cid,job_id=fresh['job_id'],grant_sha256=fresh['grant_sha256'])
  assert capture_request['state']=='CAPTURING'
  lineage=wait_lineage(tmp_path,cid,lambda r:r['publication']['state']=='FAILED')
  assert lineage['state']=='PUBLISHED' and lineage['publication']['reason']=='FIXTURE_ACK_REPLY_LOST'
  assert lineage['manifest']==lineage['publication']['manifest'] and lineage['evidence']['size_bytes']>32768
  assert lineage['use']=='HISTORICAL_ONLY' and lineage['freshness']=='NOT_RESTORED'
  assert all(lineage[k] is False for k in ('financial_accepted','transport_authorized','research_eligible'))
  request_id=str(uuid4());command=dict(operation='compose',job_id=fresh['job_id'])
  current=control(tmp_path,'paper_market_read',command,request_id=request_id)['composition']
  assert current['observed_sessions']==252 and current['observed_conditions_met'] and current['quote_valid'] and current['asset_valid']
  assert current['history_job_id']==history['job_id'] and current['status']=='BLOCKED' and current['financial_accepted'] is False
  tmp_path.with_name(tmp_path.name+'-advance-market-age.fixture').write_text('fixture-only advance31seconds')
  stale=control(tmp_path,'paper_market_read',command,request_id=request_id)['composition']
  assert not stale['quote_valid'] and not stale['asset_valid'] and not stale['observed_conditions_met'] and stale['age_basis_at']!=current['age_basis_at']
  with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):control(tmp_path,'shutdown')
  # An acknowledged busy reply must leave every healthy owner channel usable.
  still_complete=call(tmp_path,'status',job_id=fresh['job_id'])
  assert still_complete['state']=='COMPLETE' and still_complete['grant_sha256']==fresh['grant_sha256']
  # The existing fixture deadline closes the processes without a checkpoint.
  # A deliberate forbidden command is fatal and belongs after restart checks.
  out,err=capture(tmp_path,p,60)
  assert p.returncode==0 and err==b'',err.decode()
  second=json.loads(out);assert len(second['requests'])==2 and all('/v2/stocks/bars' not in path for path in second['requests'])
  second['closure']='CONTROLLED_FIXTURE_DEADLINE';second['exit_code']=p.returncode
  assert second['lost_ack_receipts']==1
  p,third_initial=launch(tmp_path,'verify');assert third_initial['watchdog']['owners']['execution']['generation']>second_generation
  interrupted=call(tmp_path,'status',job_id=fresh['job_id']);assert interrupted['state']=='INTERRUPTED' and 'fresh' not in interrupted
  assert interrupted['reason']=='OWNER_RESTARTED' and interrupted['grant_sha256']==fresh['grant_sha256']
  with pytest.raises(RuntimeRefused):call(tmp_path,'compose',job_id=fresh['job_id'])
  with pytest.raises(RuntimeRefused):call(tmp_path,'start',job_id=fresh['job_id'],grant_sha256=fresh['grant_sha256'])
  restored=wait(tmp_path,history['job_id'],lambda r:r['publication']['state']=='PUBLISHED');assert restored['manifest']==published['manifest']
  restored_lineage=wait_lineage(tmp_path,cid,lambda r:r['publication']['state']=='PUBLISHED')
  assert restored_lineage['manifest']==lineage['manifest'] and restored_lineage['lineage_sha256']==lineage['lineage_sha256']
  assert restored_lineage['evidence']==lineage['evidence'] and restored_lineage['grant_sha256']==fresh['grant_sha256']
  retried=call(tmp_path,'publish_lineage',capture_id=cid,job_id=fresh['job_id'],grant_sha256=fresh['grant_sha256'])
  assert retried==restored_lineage and all(retried[k] is False for k in ('financial_accepted','transport_authorized','research_eligible'))
  with pytest.raises(RuntimeRefused):call(tmp_path,'publish_lineage',capture_id=str(uuid4()),job_id=fresh['job_id'],grant_sha256=fresh['grant_sha256'])
  assert control(tmp_path,'status')['fixture_requests']==[]
  with pytest.raises(RuntimeRefused):control(tmp_path,'paper_market_transfer',dict(operation='lineage_chunk',capture_id=cid,offset=0,sha256=lineage['evidence']['sha256']))
  out,err=capture(tmp_path,p)
  assert p.returncode!=0 and b'COMMAND_DENIED' in err,err.decode()
  third=json.loads(out);assert third['requests']==[]
  third['closure']='INTENTIONAL_COMMAND_DENIED';third['exit_code']=p.returncode
  receipt=dict(first=first,second=second,third=third,reserve=reserve,history=published,current=current,stale=stale,lineage=lineage,restored_lineage=restored_lineage,financial_accepted=False)
  raw=json.dumps(receipt);assert 'INVENTED_KEY' not in raw and 'INVENTED_SECRET' not in raw and 'body_utf8' not in raw
  (tmp_path/'native-market-receipt.json').write_text(raw)
 finally:
  if p.poll() is None:p.kill()
  capture(tmp_path,p,5)
