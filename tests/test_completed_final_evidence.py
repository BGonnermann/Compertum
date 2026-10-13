"""Small saved-publication tests; native identities here are simulated."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone
import json,sqlite3
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_final_task import request as seed_request
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.final_task import build_task
from compertum.final_request import build_request
from compertum.review_evidence import sha
from compertum.review_frame import result_binding,pack_review
from compertum.runtime.startup_record import expected_proof
from compertum.runtime.campaign_environment import observed_from_native
from compertum import completed_final_evidence as module


@pytest.fixture
def saved(tmp_path,monkeypatch):
 raw,_=seed_request();v=json.loads(raw);p=v['plan'];sid=p['seal_id'];eid=p['evaluation_id'];source=v['source_artifact'];run=source['task_id']
 source_raw=canonical(dict(clean_pair=dict(record=dict(project_id=p['project_id'],source=dict(seal_id=sid),holdout_manifest_sha256=p['inputs']['input_sha256']))))
 assert len(source_raw)==source['size_bytes'] and sha(source_raw)==source['sha256']
 guard=dict(status='VERIFIED',sequence=1,sha256='5'*64,consumed={sid:dict(evaluation_id=eid,inputs=p['inputs'])})
 raw=build_request(p,plan_sha256=sha(canonical(p)),consumption_sha256=sha(canonical(guard['consumed'][sid])),number=1,source_artifact=source);v=json.loads(raw)
 db=sqlite3.connect(':memory:')
 db.execute('CREATE TABLE reservations(id TEXT PRIMARY KEY,task TEXT,category TEXT,maximum INTEGER,written INTEGER,status TEXT,path TEXT,manifest TEXT)')
 db.execute('CREATE TABLE baseline_runs(run_id TEXT,body TEXT)')
 db.execute('CREATE TABLE final_dispatches(seal_id TEXT,attempt_id TEXT PRIMARY KEY,body TEXT,sha256 TEXT)')
 for table in ('final_exits','final_closures'):db.execute('CREATE TABLE '+table+'(attempt_id TEXT PRIMARY KEY,body TEXT,sha256 TEXT)')
 def publish(task,path,data,*,artifact=None,reservation=None,maximum=None):
  a=artifact or dict(artifact_id=str(uuid4()),task_id=task,path=path,size_bytes=len(data),sha256=sha(data))
  target=tmp_path/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
  db.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?,?,?)',(reservation or str(uuid4()),task,'records',maximum or len(data),len(data),'PUBLISHED',path,canonical(a).decode()));return a
 publish(run,source['path'],source_raw,artifact=source)
 db.execute('INSERT INTO baseline_runs VALUES(?,?)',(run,canonical(dict(run_id=run,input_kind='synthetic-campaign',state='COMPLETED',input_artifact=source,request_sha256=source['sha256'])).decode()))
 req=publish(eid,f'artifacts/runs/{eid}/input/final/attempt-01.json',raw)
 payload=build_task(tmp_path,raw,req,charged_ms=0,now=datetime(2026,10,11,tzinfo=timezone.utc)).to_payload();task=publish(eid,f'artifacts/runs/{eid}/input/final/task-attempt-01.json',canonical(payload))
 native=dict(schema='native-template-execution-v3',process=dict(pid=123,creation_filetime=456,operator_sid='S-1-5-21-1'),task_id=eid,role='experiment_runner',entrypoint='compertum.runtime.campaign_worker',code_sha256=p['runtime']['package_sha256'],lock_sha256=p['runtime']['lock_sha256'],task_sha256=task['sha256'],startup=dict(image_sha256='0'*64,volume_serial=1,file_id='1'*32,plan_sha256='2'*64),clean_environment=dict(schema='expected-clean-campaign-v1',pair_sha256='e'*64,manifest_sha256='c'*64,lane='source',run_id=run))
 a=dict(number=1,attempt_id=v['attempt_id'],evaluation_id=eid,checkpoint_id=p['checkpoint_id'],plan_sha256=v['plan_sha256'],consumption_sha256=v['consumption_sha256'],task_sha256=task['sha256'],reservation_id=str(uuid4()),output_path=f'artifacts/runs/{eid}/final/attempt-01.final',native_execution=native,charged_before_ms=0,started_at=payload['created_at'],deadline_at=payload['deadline_at'])
 binding=result_binding('final',eid,run,sha(raw),p['runtime'],123,startup=expected_proof(native),environment=observed_from_native(native));body=b'{"fixture":true}';frame_raw=pack_review(body,binding)
 frame=publish(eid,a['output_path'],frame_raw,reservation=a['reservation_id'],maximum=16*1024**2)
 publication=dict(artifact=frame,payload_sha256=sha(body),payload_bytes=len(body))
 receipt=dict(pid=123,exit_code=0,timed_out=False,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=32000000,observed_child_pids=[],observed_children_exited=True,execution_identity=native)
 common=dict(seal_id=sid,created_at='2026-10-11T00:00:01+00:00',owner_instance=str(uuid4()),owner_generation=1)
 start=dict(common,operation='START_FINAL_BATCH',attempt=a)
 closed=dict(common,operation='TERMINATE_FINAL_BATCH',created_at='2026-10-11T00:00:02+00:00',attempt_id=a['attempt_id'],outcome='COMPLETED',charged_ms=2000,job_receipt=receipt,publication=publication)
 row=dict(status='SEALED',creation=dict(protocol=dict(development_sha256=source['sha256'])),final=dict(plan=p,plan_sha256=v['plan_sha256']),freeze=dict(ticket=dict(pair_sha256='e'*64,pair=dict(source=dict(run_id=run,manifest_sha256='c'*64)))),final_attempts=[dict(start=start,close=closed)],final_complete=dict(closed,result_sha256='7'*64))
 evidence=dict(status='VERIFIED',sequence=8,sha256='8'*64,seals={sid:row})
 dispatch=dict(schema='synthetic-final-dispatch-v1',seal_id=sid,attempt=deepcopy(a),request_artifact=req,task_artifact=task)
 db.execute('INSERT INTO final_dispatches VALUES(?,?,?,?)',(sid,a['attempt_id'],canonical(dispatch).decode(),sha(canonical(dispatch))))
 exit_record=dict(schema='synthetic-final-exit-v1',attempt_id=a['attempt_id'],observed_at='2026-10-11T00:00:02+00:00',job_receipt=deepcopy(receipt))
 closure=dict(schema='synthetic-final-closure-v1',seal_id=sid,attempt_id=a['attempt_id'],exit_sha256=sha(canonical(exit_record)),mode='COMPLETED',publication=publication)
 for table,value in (('final_exits',exit_record),('final_closures',closure)):db.execute('INSERT INTO '+table+' VALUES(?,?,?)',(a['attempt_id'],canonical(value).decode(),sha(canonical(value))))
 project=SimpleNamespace(root_path=tmp_path,project_id=p['project_id'])
 @contextmanager
 def live():yield SimpleNamespace(project=project)
 storage=SimpleNamespace(root=tmp_path,store=SimpleNamespace(conn=db,_live=live))
 status=dict(status='COMPLETED');monkeypatch.setattr(module,'context',lambda *args,**kwargs:(deepcopy(evidence),deepcopy(guard),deepcopy(status)));monkeypatch.setattr(module,'mirrors',lambda *args:None)
 yield SimpleNamespace(storage=storage,db=db,sid=sid,evidence=evidence,guard=guard,row=row,dispatch=dispatch,exit=exit_record,closure=closure,frame=frame,raw=frame_raw,status=status)
 db.close()


def update(db,table,key,value):
 raw=canonical(value);db.execute('UPDATE '+table+' SET body=?,sha256=? WHERE attempt_id=?',(raw.decode(),sha(raw),key))


def test_completed_original_survives_new_runtime_without_writing(saved,monkeypatch):
 from compertum import recovery
 monkeypatch.setattr(recovery,'_package_hash',lambda:'9'*64)
 before=(list(saved.db.iterdump()),canonical(saved.evidence),canonical(saved.guard),saved.storage.root.joinpath(saved.frame['path']).read_bytes())
 result=module.completed_final(saved.storage,saved.sid)
 assert result['frame']==saved.frame and result['author']==saved.row['final_attempts'][0]['start']['attempt']['native_execution']
 assert result['plan']['runtime']['package_sha256']!='9'*64
 assert before==(list(saved.db.iterdump()),canonical(saved.evidence),canonical(saved.guard),saved.storage.root.joinpath(saved.frame['path']).read_bytes())


@pytest.mark.parametrize('fault',['running','invalidated','empty','no_close','no_dispatch','dispatch_hash','request','task','charge','consumption','author','exit_failure','exit_timeout','exit_mismatch','publication','reserved_only','reserve_size','frame_byte','frame_author','closure','closure_exit','deadline','continuity'])
def test_changed_completed_evidence_is_rejected(saved,monkeypatch,fault):
 s=saved;a=s.row['final_attempts'][0]['start']['attempt'];aid=a['attempt_id']
 if fault in ('running','invalidated'):s.status['status']='BATCH_RUNNING' if fault=='running' else 'INVALIDATED'
 elif fault=='empty':s.row['final']['plan']['selected']=[]
 elif fault=='no_close':s.row['final_attempts'][0]['close']=None
 elif fault=='no_dispatch':s.db.execute('DELETE FROM final_dispatches')
 elif fault=='dispatch_hash':s.db.execute("UPDATE final_dispatches SET sha256=?",('9'*64,))
 elif fault in ('request','task'):
  key='request_artifact' if fault=='request' else 'task_artifact';s.dispatch[key]['sha256']='9'*64;update(s.db,'final_dispatches',aid,s.dispatch)
 elif fault=='charge':a['charged_before_ms']=1
 elif fault=='consumption':s.guard['consumed'][s.sid]['evaluation_id']=str(uuid4())
 elif fault=='author':a['native_execution']['process']['creation_filetime']+=1
 elif fault in ('exit_failure','exit_timeout','exit_mismatch'):
  if fault=='exit_failure':s.exit['job_receipt']['exit_code']=125
  elif fault=='exit_timeout':s.exit['job_receipt']['timed_out']=True
  else:s.exit['job_receipt']['execution_identity']['process']['creation_filetime']+=1
  update(s.db,'final_exits',aid,s.exit)
 elif fault=='publication':s.row['final_attempts'][0]['close']['publication']['payload_sha256']='9'*64
 elif fault=='reserved_only':s.db.execute("UPDATE reservations SET status='OPEN' WHERE id=?",(a['reservation_id'],))
 elif fault=='reserve_size':s.db.execute('UPDATE reservations SET maximum=maximum+1 WHERE id=?',(a['reservation_id'],))
 elif fault=='frame_byte':s.storage.root.joinpath(s.frame['path']).write_bytes(s.raw[:-1]+b'x')
 elif fault=='frame_author':
  header,body=s.raw.split(b'\n',1);header=json.loads(header);header['worker_pid']+=1;changed=canonical(header)+b'\n'+body
  s.frame.update(size_bytes=len(changed),sha256=sha(changed));s.storage.root.joinpath(s.frame['path']).write_bytes(changed)
  s.db.execute('UPDATE reservations SET written=?,manifest=? WHERE id=?',(len(changed),canonical(s.frame).decode(),a['reservation_id']))
 elif fault in ('closure','closure_exit'):
  s.closure['mode' if fault=='closure' else 'exit_sha256']='INTERRUPTED' if fault=='closure' else '9'*64;update(s.db,'final_closures',aid,s.closure)
 elif fault=='deadline':
  values=iter([0,5]);monkeypatch.setattr(module.time,'monotonic',lambda:next(values))
 else:
  count=[]
  def changed(*args,**kwargs):
   e=deepcopy(s.evidence);count.append(1)
   if len(count)>1:e['sha256']='9'*64
   return e,deepcopy(s.guard),deepcopy(s.status)
  monkeypatch.setattr(module,'context',changed)
 with pytest.raises(DataError):module.completed_final(s.storage,s.sid)


def test_rehashed_exit_observation_after_recorded_closure_is_rejected(saved):
 s=saved;aid=s.dispatch['attempt']['attempt_id']
 s.exit['observed_at']='2026-10-11T00:00:03+00:00';update(s.db,'final_exits',aid,s.exit)
 s.closure['exit_sha256']=sha(canonical(s.exit));update(s.db,'final_closures',aid,s.closure)
 with pytest.raises(DataError):module.completed_final(s.storage,s.sid)
