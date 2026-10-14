"""Pure invented opening records; no filesystem owners, credentials or requests."""
from copy import deepcopy
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_opening_records import build_reference,validate_reference,cash_matches,reference_sha

P='a'*64;ALIAS='fixture';PACKET='11111111-1111-4111-8111-111111111111';TASK='22222222-2222-4222-8222-222222222222';ART='33333333-3333-4333-8333-333333333333';AT='2023-11-24T14:30:01+00:00'

def parts():
 proposal=dict(project_id=P,account_alias=ALIAS,packet_id=PACKET,identity_sha256='b'*64,credential_sha256='c'*64,opening_observation_sha256='d'*64,history_sha256=reference_sha(dict(status='VERIFIED_ZERO_PRE_SCHEMA',sequence=0,sha256='0'*64,empty=True)))
 manifest=dict(artifact_id=ART,path=f'artifacts/runs/{TASK}/paper-read-{PACKET}.bin',size_bytes=1024,sha256='e'*64,task_id=TASK)
 proposal['manifest_sha256']=reference_sha(manifest);proposal['encrypted_evidence_sha256']=manifest['sha256']
 record=dict(proposal=proposal,proposal_sha256=reference_sha(proposal),confirmed_at=AT)
 history=dict(status='VERIFIED_ZERO_PRE_SCHEMA',sequence=0,sha256='0'*64,empty=True)
 return record,manifest,history

def reference(**kw):
 record,manifest,history=parts();return build_reference(record,manifest,history,[],restore_clear=True,**kw)

def test_clean_reference_is_exact_deterministic_and_contains_no_cash():
 a=reference();assert a==reference();assert validate_reference(a,P,ALIAS)==a
 assert a['reference']['disposition']=='CLEAN_ZERO_HISTORY'
 assert not any(k in str(a) for k in ('100000','private_account_id','cash'))

@pytest.mark.parametrize('reason',['UNEXPLAINED_POSITIONS','UNEXPLAINED_ORDER_HISTORY','LOCAL_HISTORY_UNVERIFIED','NEGATIVE_ACCOUNT_CASH'])
def test_blocked_initial_observation_is_retained(reason):
 record,m,h=parts();a=build_reference(record,m,h,[reason],restore_clear=True)
 assert a['reference']['disposition']=='BLOCKED' and a['reference']['deficiencies']==[reason]
 assert validate_reference(a,P,ALIAS)==a

def test_restore_cannot_create_clean_reference():
 record,m,h=parts();a=build_reference(record,m,h,[],restore_clear=False)
 assert a['reference']['disposition']=='BLOCKED' and 'RESTORE_HISTORY_PRESENT' in a['reference']['deficiencies']

def test_nonzero_history_is_not_clean_even_if_caller_omits_reason():
 record,m,h=parts();h.update(sequence=1,sha256='f'*64,empty=False);record['proposal']['history_sha256']=reference_sha(h);record['proposal_sha256']=reference_sha(record['proposal'])
 with pytest.raises(RuntimeRefused):build_reference(record,m,h,[],restore_clear=True)

@pytest.mark.parametrize('change',['digest','extra','project','alias','version','packet','manifest_path','manifest_task','manifest_size_bool','disposition','clean_reason','clean_history','confirmation','history_hash'])
def test_tampered_reference_refuses_even_if_structural_hash_recomputed(change):
 a=reference();p=a['reference']
 if change=='digest':a['sha256']='f'*64
 elif change=='extra':p['cash']='100000'
 elif change=='project':p['project_id']='f'*64
 elif change=='alias':p['account_alias']='other'
 elif change=='version':p['version']=True
 elif change=='packet':p['first_packet_id']='bad'
 elif change=='manifest_path':p['manifest']['path']='state/execution.sqlite'
 elif change=='manifest_task':p['manifest']['task_id']=PACKET
 elif change=='manifest_size_bool':p['manifest']['size_bytes']=True
 elif change=='disposition':p['disposition']='TRADING_APPROVED'
 elif change=='clean_reason':p['deficiencies']=['UNEXPLAINED_POSITIONS']
 elif change=='clean_history':p['history']['sequence']=1
 elif change=='confirmation':p['confirmed_at']='tomorrow'
 else:p['history_sha256']='f'*64
 if change!='digest':a['sha256']=reference_sha(p)
 with pytest.raises(RuntimeRefused):validate_reference(a,P,ALIAS)

@pytest.mark.parametrize(('opening','current','expected'),[('100000','100000',True),('100000','100000.01',True),('100000','99999.99',True),('100000','100000.01001',False),('100000','99999.98999',False),('1'+'0'*55,'1'+'0'*55+'.02',False)])
def test_cash_uses_original_exact_decimal_cent_bound(opening,current,expected):
 assert cash_matches(opening,current) is expected

def test_cumulative_cash_drift_never_moves_baseline():
 assert cash_matches('100','100.01')
 assert cash_matches('100.01','100.02')
 assert not cash_matches('100','100.02')

@pytest.mark.parametrize('value',['-0.01','NaN','Infinity','1e5',True,None,'1'*65])
def test_invalid_or_negative_cash_refuses(value):
 with pytest.raises(RuntimeRefused):cash_matches('100',value)

@pytest.mark.parametrize('field',['manifest','history','proposal'])
def test_build_refuses_unbound_source(field):
 r,m,h=parts()
 if field=='manifest':m['sha256']='f'*64
 elif field=='history':h['status']='VERIFIED_HISTORY'
 else:r['proposal']['identity_sha256']='f'*64
 with pytest.raises(RuntimeRefused):build_reference(r,m,h,[],restore_clear=True)

def test_opening_preserves_existing_64_character_case_sensitive_alias_contract():
 r,m,h=parts();alias='A'+'1'*63;r['proposal']['account_alias']=alias;r['proposal_sha256']=reference_sha(r['proposal'])
 a=build_reference(r,m,h,[],restore_clear=True);assert validate_reference(a,P,alias)==a

@pytest.mark.parametrize('hostile',['overflow','subnormal','rounding','precision'])
def test_cash_comparison_is_independent_of_ambient_decimal_context(hostile):
 from decimal import localcontext,Overflow,Subnormal,ROUND_UP
 with localcontext() as context:
  if hostile=='overflow':context.Emax=0;context.traps[Overflow]=True
  elif hostile=='subnormal':context.Emin=0;context.traps[Subnormal]=True
  elif hostile=='rounding':context.rounding=ROUND_UP;context.prec=1
  else:context.prec=1
  assert cash_matches('0','100') is False
  assert cash_matches('100','100.01') is True
  assert cash_matches('100','100.01000001') is False
