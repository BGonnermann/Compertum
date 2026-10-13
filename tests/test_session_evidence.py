"""Immutable evidence integrity is not proof of actual supervised operation."""
import copy,hashlib,json
from importlib.metadata import version
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.data.calendar import session_times
from compertum.domain import ContractError
from compertum.session_evidence import check_session,check_window

KINDS=('INPUTS','SUPERVISION','ORDERS','LEDGER','INCIDENTS','CLOSING','RECOVERY','AI_OFF')
SHA='a'*64
ASOF='2026-10-11T22:00:00Z'
def ref(raw,identity):return dict(artifact_id=identity,sha256=hashlib.sha256(raw).hexdigest(),size_bytes=len(raw))
def packet(day='2023-11-20',previous=None,provenance='PAPER_WIRE_FIXTURE'):
 sid=str(uuid4());times=session_times(day);artifacts=[];roots={}
 for kind in KINDS:
  aid=str(uuid4());records=[] if kind=='ORDERS' else [{'observation':'invented'}]
  a=dict(version=1,record_type='SessionEvidenceArtifact',artifact_id=aid,session_id=sid,project_id=SHA,account_alias='fixture',kind=kind,page=1,records=records,references=[])
  raw=canonical(a);artifacts.append(raw);roots[kind]=dict(reference=ref(raw,aid),page_count=1,record_count=len(records))
 m=dict(version=1,record_type='SessionEvidenceManifest',scope='OFFLINE_SESSION_EVIDENCE',provenance=provenance,project_id=SHA,account_alias='fixture',private_context_sha256='b'*64,session_id=sid,session_date=day,calendar=dict(name='XNYS',package='exchange_calendars',version=version('exchange-calendars')),started_at=times.open.isoformat(),ended_at=times.close.isoformat(),code_sha256=SHA,lock_sha256=SHA,config_sha256=SHA,previous_session=previous,roots=roots)
 return canonical(m),tuple(artifacts)
def mutate(p,key,value):
 m=json.loads(p[0]);m[key]=value;return canonical(m),p[1]
def check(p):return check_session(*p,as_of=ASOF)
def window(start='2023-11-20'):
 out=[];previous=None;day=start
 for _ in range(10):
  p=packet(day,previous);out.append(p);previous=ref(p[0],json.loads(p[0])['session_id']);day=session_times(day).next_date
 return tuple(out)
def change_artifact(p,index,changes):
 m=json.loads(p[0]);rows=list(p[1]);a=json.loads(rows[index]);a.update(changes);raw=canonical(a);rows[index]=raw
 m['roots'][KINDS[index]]['reference']=ref(raw,a['artifact_id'])
 return canonical(m),tuple(rows)

def test_valid_no_order_packet_retains_zero_actual_sessions_and_opaque_meaning():
 p=packet();before=copy.deepcopy(p);r=check(p)
 assert p==before and r['structural_status']=='VERIFIED_PASS'
 assert r['actual_sessions_verified']==0 and r['qualification_status']=='UNVERIFIED'
 assert r['semantic_status']=='UNVERIFIED' and r['transport_authorized'] is False
 assert r['streams']['ORDERS']['record_count']==0
 assert r['manifest_sha256']==hashlib.sha256(p[0]).hexdigest()
 assert 'NATIVE_SESSION_SEMANTICS_UNVERIFIED' in r['unverified_reasons']

@pytest.mark.parametrize('provenance',['ACTUAL_PAPER_CLAIM','PAPER_PREPARATION','DETERMINISTIC_FAKE','PAPER_WIRE_FIXTURE','ACCELERATED_CLOCK','BACKTEST','HISTORICAL_REPLAY'])
def test_no_caller_provenance_can_certify_actual_sessions(provenance):
 r=check(packet(provenance=provenance));assert r['actual_sessions_verified']==0
 assert r['milestone_accepted'] is False and r['financial_accepted'] is False

@pytest.mark.parametrize('key,value',[
 ('version',True),('version',2),('record_type','Other'),('scope','ACTUAL'),('project_id',[]),('private_context_sha256','bad'),
 ('account_alias','../secret'),('session_id','11111111-1111-4111-8111-11111111111A'),('session_date','2023-11-23'),('session_date','2023-11-19'),
 ('started_at','2023-11-20T14:30:00.000000001Z'),('started_at','2023-11-19T14:30:00Z'),('ended_at','2023-11-20T14:00:00Z'),
 ('code_sha256','A'*64),('lock_sha256',True),('config_sha256',None),('provenance','VERIFIED_ACTUAL'),('previous_session',{}),
 ('calendar',{'name':'XNYS','package':'exchange_calendars','version':'0'})])
def test_manifest_tampering_is_rejected(key,value):
 with pytest.raises(ContractError):check(mutate(packet(),key,value))

def test_future_or_uncompleted_session_rejected():
 p=packet()
 for asof in ('2023-11-20T15:00:00Z','2023-11-19T22:00:00Z'):
  with pytest.raises(ContractError):check_session(*p,as_of=asof)

def test_interval_ending_early_is_structural_only_and_day_must_be_complete():
 p=mutate(packet(),'ended_at','2023-11-20T15:00:00Z');assert check(p)['actual_sessions_verified']==0
 with pytest.raises(ContractError):check_session(*p,as_of='2023-11-20T16:00:00Z')

@pytest.mark.parametrize('mode',['missing','extra','duplicate','corrupt','noncanonical','nonbytes','oversize','duplicate_key','nan'])
def test_bad_artifact_sets_rejected(mode):
 p=packet();rows=list(p[1])
 if mode=='missing':rows.pop()
 elif mode=='extra':rows.append(packet()[1][0])
 elif mode=='duplicate':rows.append(rows[0])
 elif mode=='corrupt':rows[0]=rows[0].replace(b'invented',b'changed')
 elif mode=='noncanonical':rows[0]=b' '+rows[0]
 elif mode=='nonbytes':rows[0]=bytearray(rows[0])
 elif mode=='oversize':rows[0]=b' '*65537
 elif mode=='duplicate_key':rows[0]=b'{"a":1,"a":2}'
 elif mode=='nan':rows[0]=b'{"a":NaN}'
 with pytest.raises(ContractError):check((p[0],tuple(rows)))

@pytest.mark.parametrize('changes',[{'session_id':str(uuid4())},{'project_id':'c'*64},{'account_alias':'different'},{'kind':'ORDERS'},{'page':True},{'page':2},{'records':[True]},{'records':[{}]*513},{'references':[{}]},{'version':True}])
def test_bound_artifacts_still_require_identity_and_page_integrity(changes):
 with pytest.raises(ContractError):check(change_artifact(packet(),0,changes))

@pytest.mark.parametrize('mode',['missing_root','extra_root','count','page_count','size','hash','self_previous','root_reuse'])
def test_manifest_reference_and_count_binding(mode):
 p=packet();m=json.loads(p[0]);root=m['roots']['INPUTS']
 if mode=='missing_root':del m['roots']['CLOSING']
 elif mode=='extra_root':m['roots']['EXTRA']=root
 elif mode=='count':root['record_count']+=1
 elif mode=='page_count':root['page_count']+=1
 elif mode=='size':root['reference']['size_bytes']+=1
 elif mode=='hash':root['reference']['sha256']='0'*64
 elif mode=='self_previous':m['previous_session']=ref(p[0],m['session_id'])
 elif mode=='root_reuse':m['roots']['SUPERVISION']=root
 with pytest.raises(ContractError):check((canonical(m),p[1]))

def test_optional_exercises_absent_remain_unverified():
 p=packet();m=json.loads(p[0]);m['roots']['RECOVERY']=m['roots']['AI_OFF']=None
 r=check((canonical(m),p[1][:-2]));assert {'RECOVERY_EVIDENCE_ABSENT','AI_OFF_EVIDENCE_ABSENT'}<=set(r['unverified_reasons'])

def test_transitive_pages_bound_and_counted_without_claiming_coverage():
 p=packet();m=json.loads(p[0]);rows=list(p[1]);a=json.loads(rows[0]);child=dict(a,artifact_id=str(uuid4()),page=2,records=[{'second':True}]);raw=canonical(child)
 a['references']=[ref(raw,child['artifact_id'])];rows[0]=canonical(a);rows.append(raw)
 m['roots']['INPUTS']=dict(reference=ref(rows[0],a['artifact_id']),page_count=2,record_count=2)
 r=check((canonical(m),tuple(rows)));assert r['streams']['INPUTS']==dict(page_count=2,record_count=2)
 for altered in (rows[:-1],rows+[raw]):
  with pytest.raises(ContractError):check((canonical(m),tuple(altered)))

def test_calendar_window_uses_exchange_successors_holiday_and_early_close():
 w=window();r=check_window(w,as_of=ASOF)
 assert r['structurally_valid_sessions']==10 and r['actual_sessions_verified']==0
 assert '2023-11-23' not in r['session_dates'] and '2023-11-24' in r['session_dates']
 p=next(p for p in w if json.loads(p[0])['session_date']=='2023-11-24');assert check(p)['exchange_close']=='2023-11-24T18:00:00+00:00'

def test_calendar_window_crosses_dst_without_weekday_shortcut():
 r=check_window(window('2023-10-30'),as_of=ASOF);assert r['structurally_valid_sessions']==10
 assert check(packet('2023-11-03'))['exchange_open']=='2023-11-03T13:30:00+00:00'
 assert check(packet('2023-11-06'))['exchange_open']=='2023-11-06T14:30:00+00:00'

@pytest.mark.parametrize('mode',['short','long','duplicate','reordered','missing_predecessor','wrong_project','wrong_account','wrong_context','changed_previous_hash','skip_day'])
def test_window_rejects_broken_continuity(mode):
 w=list(window())
 if mode=='short':w.pop()
 elif mode=='long':w.append(w[-1])
 elif mode=='duplicate':w[3]=w[2]
 elif mode=='reordered':w[1],w[2]=w[2],w[1]
 elif mode=='missing_predecessor':w[4]=mutate(w[4],'previous_session',None)
 elif mode=='wrong_project':w[4]=mutate(w[4],'project_id','d'*64)
 elif mode=='wrong_account':w[4]=mutate(w[4],'account_alias','other')
 elif mode=='wrong_context':w[4]=mutate(w[4],'private_context_sha256','d'*64)
 elif mode=='changed_previous_hash':
  m=json.loads(w[4][0]);m['previous_session']['sha256']='0'*64;w[4]=(canonical(m),w[4][1])
 elif mode=='skip_day':w[5]=packet(session_times(json.loads(w[5][0])['session_date']).next_date,json.loads(w[5][0])['previous_session'])
 with pytest.raises(ContractError):check_window(tuple(w),as_of=ASOF)


@pytest.mark.parametrize('raw',[b'',b'{}',b' '+packet()[0],bytearray(b'{}'),b'{"version":1,"version":1}',b'{"x":Infinity}',b' '*65537],ids=['empty','object','noncanonical','mutable','duplicate-key','infinity','oversize'])
def test_manifest_parser_bounds_and_canonical_bytes(raw):
 with pytest.raises(ContractError):check_session(raw,packet()[1],as_of=ASOF)

@pytest.mark.parametrize('value',[None,[],{},0,True,''])
def test_wrong_manifest_container_types_are_stable_rejections(value):
 for key in ('calendar','roots','session_date','started_at','ended_at'):
  with pytest.raises(ContractError):check(mutate(packet(),key,value))

@pytest.mark.parametrize('value',[(),[],None,tuple([b'{}']*129)])
def test_artifact_collection_bound_before_parsing(value):
 with pytest.raises(ContractError):check_session(packet()[0],value,as_of=ASOF)

def test_graph_depth_bound_is_enforced_with_exact_valid_hashes():
 p=packet();m=json.loads(p[0]);prototype=json.loads(p[1][0]);rows=list(p[1][1:]);link=None
 for page in range(17,0,-1):
  a=dict(prototype,artifact_id=str(uuid4()),page=page,references=[] if link is None else [link]);raw=canonical(a);rows.append(raw);link=ref(raw,a['artifact_id'])
 m['roots']['INPUTS']=dict(reference=link,page_count=17,record_count=17)
 with pytest.raises(ContractError,match='SESSION_GRAPH_DEPTH'):check((canonical(m),tuple(rows)))

def test_reordering_artifact_collection_keeps_exact_diagnostic():
 p=packet();r=check(p);assert check((p[0],tuple(reversed(p[1]))))==r
 r['unverified_reasons'].clear();r['streams']['ORDERS']['record_count']=999
 assert check(p)['streams']['ORDERS']['record_count']==0 and check(p)['unverified_reasons']

def test_calendar_only_inputs_do_not_require_daily_trades_or_flatness():
 p=change_artifact(packet(),3,{'records':[{'holdings':'not interpreted','healthy':True,'complete':True}]})
 r=check(p);assert r['semantic_status']=='UNVERIFIED' and r['actual_sessions_verified']==0


@pytest.mark.parametrize('field,value',[('started_at','0001-01-01T00:00:00Z'),('ended_at','9999-12-31T23:59:59Z')])
def test_extreme_dates_are_stable_contract_rejections(field,value):
 with pytest.raises(ContractError):check(mutate(packet(),field,value))


@pytest.mark.parametrize('mode',['artifact_artifact','artifact_manifest','first_predecessor_in_window'])
def test_window_reference_identity_is_unique_across_all_packets(mode):
 w=list(window())
 if mode=='artifact_artifact':
  duplicate=json.loads(w[0][1][0])['artifact_id'];w[1]=change_artifact(w[1],0,{'artifact_id':duplicate})
 elif mode=='artifact_manifest':
  duplicate=json.loads(w[0][0])['session_id'];w[1]=change_artifact(w[1],0,{'artifact_id':duplicate})
 else:
  w[0]=mutate(w[0],'previous_session',ref(w[-1][0],json.loads(w[-1][0])['session_id']))
 for index in range(1,10):w[index]=mutate(w[index],'previous_session',ref(w[index-1][0],json.loads(w[index-1][0])['session_id']))
 with pytest.raises(ContractError):check_window(tuple(w),as_of=ASOF)
