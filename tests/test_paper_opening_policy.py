"""In-memory owner-policy tests. Native identity, artifact origin and freshness are injected."""
from contextlib import contextmanager,nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sqlite3
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_opening_records import reference_sha
from compertum.runtime import paper_opening as m
from compertum.runtime import paper_account_binding as b
from test_paper_opening_records import P,ALIAS,PACKET,TASK,AT,parts

ACCOUNT='44444444-4444-4444-8444-444444444444';INSTANCE='55555555-5555-4555-8555-555555555555'

@pytest.fixture
def policy(monkeypatch):
 cipher=b'invented-opening-envelope';credential=hashlib.sha256(cipher).hexdigest()
 db=sqlite3.connect(':memory:');db.execute('CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
 base,manifest,history=parts();identity=reference_sha(dict(purpose='COMPERTUM_PAPER_ALIAS_IDENTITY_V1',project_id=P,account_alias=ALIAS,private_account_id=ACCOUNT))
 account=dict(status='ACTIVE',cash='100000',trading_blocked=False,account_blocked=False,trade_suspended_by_user=False)
 request=dict(operation='ACCOUNT',created_at='2023-11-24T14:30:00+00:00');parsed=dict(operation='ACCOUNT',observation=account,raw_sha256='1'*64,received_at=AT)
 refs=[dict(request_sha256=reference_sha(request),parsed_sha256=reference_sha(parsed),raw_sha256=parsed['raw_sha256'],received_at=AT)]
 proposal=dict(version=1,purpose='PAPER_ACCOUNT_IDENTITY_ATTESTATION',project_id=P,account_alias=ALIAS,packet_id=PACKET,subject_key='9'*64,owner_instance=INSTANCE,generation=1,credential_sha256=credential,identity_sha256=identity,preflight_sha256='3'*64,manifest_sha256=reference_sha(manifest),encrypted_evidence_sha256=manifest['sha256'],created_at=AT,expires_at='2023-11-24T14:30:30+00:00',history_sha256=reference_sha(history),opening_observation_sha256=reference_sha(dict(private_account_id=ACCOUNT,account=account,references=refs)))
 record=dict(proposal=proposal,proposal_sha256=reference_sha(proposal),confirmed_at=AT)
 value=dict(state='PUBLISHED',evidence=dict(size_bytes=manifest['size_bytes'],sha256=manifest['sha256']),owner_generation=1,task_id=TASK,plan=dict(created_at='2023-11-24T14:30:00+00:00',start_expires_at='2023-11-24T14:31:00+00:00'))
 value.update({k:proposal[k] for k in ('project_id','account_alias','packet_id','subject_key','owner_instance','credential_sha256')})
 lease=SimpleNamespace(project_id=P,generation=1,identity=SimpleNamespace(process_instance_id=INSTANCE));store=SimpleNamespace(root=Path('memory-only'),path=Path('memory-only/state/execution.sqlite'),_live=lambda:nullcontext())
 owner=SimpleNamespace(db=db,store=store,lease=lease,_read=lambda _:value,_closed=False)
 snapshot=dict(metadata=dict(credential_sha256=credential,execution_generation=1,contexts=[dict(private_account_id=ACCOUNT)],status=dict(state='PREPARATION_COMPLETE',positions=0,orders=0,orders_coverage='OBSERVED_SHORT_TERMINAL_PAGE')),records=[dict(request=request,parsed=parsed)])
 @contextmanager
 def opened(*args):yield SimpleNamespace(snapshot=lambda:deepcopy(snapshot))
 monkeypatch.setattr(m,'open_read_evidence',opened)
 monkeypatch.setattr(m,'_restore_clear',lambda owner:True)
 monkeypatch.setattr(m,'_owner_scope',lambda _:nullcontext())
 monkeypatch.setattr(m,'require_live_owner',lambda *a:None)
 monkeypatch.setattr(m,'load_paper_slot',lambda *a:SimpleNamespace(ciphertext=cipher))
 @contextmanager
 def credentials(*args):yield SimpleNamespace(headers=lambda:{'key':'INVENTED_OPENING_KEY','secret':'INVENTED_OPENING_SECRET'})
 monkeypatch.setattr(m,'open_paper_credentials',credentials)
 context=SimpleNamespace(_records=((canonical(request),canonical(parsed)),),diagnostic=lambda:None)
 current=SimpleNamespace(_context=context)
 facts=dict(account_alias=ALIAS,transport_provenance='PAPER_TLS')
 monkeypatch.setattr(b,'_live',lambda *a:(current,record,facts,history,[]))
 def save_alias():
  b._put(owner,b._ALIAS+ALIAS,dict(version=1,project_id=P,account_alias=ALIAS,identity_sha256=identity,first_packet_id=PACKET,confirmed_at=AT),new=True)
  b._put(owner,b._PREFIX+PACKET,record,new=True)
 def save():
  with db:
   save_alias();m.record_confirmation_opening(owner,record,manifest,history,[],new_alias=True)
 yield SimpleNamespace(owner=owner,record=record,manifest=manifest,history=history,snapshot=snapshot,context=context,current=current,facts=facts,save=save,save_alias=save_alias)
 db.close()

def test_first_pin_and_repeated_confirmation_keep_exact_bytes(policy):
 f=policy;f.save();before=f.owner.db.execute('SELECT * FROM state ORDER BY key').fetchall()
 with f.owner.db:
  f.owner.db.execute('UPDATE state SET value=value');m.record_confirmation_opening(f.owner,f.record,f.manifest,f.history,[],new_alias=False)
 assert f.owner.db.execute('SELECT * FROM state ORDER BY key').fetchall()==before
 assert m.current_opening(f.owner,PACKET,f.manifest)['opening_status']=='CURRENT_CLEAN_OPENING'
 historical=m.opening_history(f.owner,ALIAS);assert historical['opening_status']=='HISTORICAL_ONLY' and not historical['transport_authorized'] and historical['actual_flat'] is None
 assert all(x not in json.dumps(historical) for x in (ACCOUNT,'100000','INVENTED_OPENING_KEY','INVENTED_OPENING_SECRET'))

@pytest.mark.parametrize('point',['alias','confirmation','pin','artifact'])
def test_interruption_rolls_back_alias_confirmation_and_pin_together(policy,monkeypatch,point):
 f=policy;original=b._put
 def interrupted(owner,key,value,**kw):
  original(owner,key,value,**kw)
  if (point=='alias' and key.startswith(b._ALIAS)) or (point=='confirmation' and key.startswith(b._PREFIX)) or (point=='pin' and key.startswith(m._PREFIX)):raise RuntimeRefused('INJECTED_INTERRUPTION')
 monkeypatch.setattr(b,'_put',interrupted)
 if point=='artifact':monkeypatch.setattr(m,'open_read_evidence',lambda *a:(_ for _ in ()).throw(RuntimeRefused('INJECTED_ARTIFACT_FAILURE')))
 with pytest.raises(RuntimeRefused):f.save()
 assert f.owner.db.execute('SELECT * FROM state').fetchall()==[]

@pytest.mark.parametrize('change',['digest','identity','manifest','proposal','alias','cipher','cash'])
def test_surviving_original_must_match_all_links(policy,change):
 f=policy;f.save()
 if change in {'digest','identity','manifest'}:
  a=b._state(f.owner,m._PREFIX+ALIAS)
  if change=='digest':a['sha256']='f'*64
  elif change=='identity':a['reference']['identity_sha256']='f'*64;a['sha256']=reference_sha(a['reference'])
  else:a['reference']['manifest']['sha256']='f'*64;a['sha256']=reference_sha(a['reference'])
  with f.owner.db:b._put(f.owner,m._PREFIX+ALIAS,a)
 elif change=='proposal':
  with f.owner.db:f.owner.db.execute('DELETE FROM state WHERE key=?',(b._PREFIX+PACKET,))
 elif change=='alias':
  with f.owner.db:f.owner.db.execute('DELETE FROM state WHERE key=?',(b._ALIAS+ALIAS,))
 elif change=='cipher':f.snapshot['metadata']['credential_sha256']='f'*64
 else:f.snapshot['records'][0]['parsed']['observation']['cash']='200000'
 with pytest.raises(RuntimeRefused):m.opening_history(f.owner,ALIAS)


def test_missing_legacy_pin_never_initializes_on_later_confirmation(policy):
 f=policy
 with f.owner.db:f.save_alias()
 with f.owner.db:
  f.owner.db.execute('UPDATE state SET value=value');m.record_confirmation_opening(f.owner,f.record,f.manifest,f.history,[],new_alias=False)
 assert b._state(f.owner,m._PREFIX+ALIAS) is None
 with pytest.raises(RuntimeRefused,match='UNRECORDED'):m.current_opening(f.owner,PACKET,f.manifest)


def test_blocked_first_reference_cannot_become_clean_later(policy,monkeypatch):
 f=policy;monkeypatch.setattr(m,'_restore_clear',lambda owner:False);f.save()
 before=b._state(f.owner,m._PREFIX+ALIAS)
 monkeypatch.setattr(m,'_restore_clear',lambda owner:True)
 with f.owner.db:
  f.owner.db.execute('UPDATE state SET value=value');m.record_confirmation_opening(f.owner,f.record,f.manifest,f.history,[],new_alias=False)
 assert b._state(f.owner,m._PREFIX+ALIAS)==before
 result=m.current_opening(f.owner,PACKET,f.manifest)
 assert result['opening_status']=='BLOCKED' and 'RESTORE_HISTORY_PRESENT' in result['deficiencies']

@pytest.mark.parametrize(('cash','status'),[('100000.01','CURRENT_CLEAN_OPENING'),('100000.02','BLOCKED')])
def test_current_cash_uses_original_baseline(policy,cash,status):
 f=policy;f.save();request,parsed=f.context._records[0];value=json.loads(parsed);value['observation']['cash']=cash;f.context._records=((request,canonical(value)),)
 assert m.current_opening(f.owner,PACKET,f.manifest)['opening_status']==status


def test_current_zero_history_may_gain_empty_schema_without_rebaselining(policy):
 f=policy;f.save();f.history['status']='VERIFIED_HISTORY'
 assert m.current_opening(f.owner,PACKET,f.manifest)['opening_status']=='CURRENT_CLEAN_OPENING'

@pytest.mark.parametrize('change',['unconfirmed','origin','identity','credentials','history','stale_after_artifact','stale_at_return'])
def test_current_qualification_rechecks_context_after_original_verification(policy,monkeypatch,change):
 f=policy;f.save();calls=[0];original=b._live
 def live(*args):
  calls[0]+=1
  if calls[0]==2:
   if change=='unconfirmed':f.record['confirmed_at']=None
   elif change=='origin':f.facts['transport_provenance']='LOOPBACK_FIXTURE'
   elif change=='identity':f.record['proposal']['identity_sha256']='f'*64
   elif change=='credentials':f.record['proposal']['credential_sha256']='f'*64
   elif change=='history':f.history.update(status='UNVERIFIED',sequence=None,sha256=None,empty=False)
   elif change=='stale_after_artifact':raise RuntimeRefused('PAPER_PREFLIGHT_STALE')
  return original(*args)
 monkeypatch.setattr(b,'_live',live)
 if change=='stale_at_return':f.context.diagnostic=lambda:(_ for _ in ()).throw(RuntimeRefused('PAPER_PREFLIGHT_STALE'))
 if change=='history':assert m.current_opening(f.owner,PACKET,f.manifest)['opening_status']=='BLOCKED'
 else:
  with pytest.raises(RuntimeRefused):m.current_opening(f.owner,PACKET,f.manifest)
 assert calls[0]==2

@pytest.mark.parametrize('when',['before_save','stored_read'])
def test_reference_secret_reflection_refuses_and_first_confirmation_rolls_back(policy,monkeypatch,when):
 f=policy
 if when=='stored_read':f.save()
 @contextmanager
 def reflected(*args):yield SimpleNamespace(headers=lambda:{'key':'PAPER_CLEAN_OPENING_REFERENCE','secret':'INVENTED_OPENING_SECRET'})
 monkeypatch.setattr(m,'open_paper_credentials',reflected)
 with pytest.raises(RuntimeRefused,match='SECRET_REFLECTION'):
  if when=='before_save':f.save()
  else:m.opening_history(f.owner,ALIAS)
 if when=='before_save':assert f.owner.db.execute('SELECT * FROM state').fetchall()==[]
