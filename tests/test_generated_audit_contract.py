"""Forged consumed-result binding must fail before any fixed-market generation."""
import hashlib,json
from copy import deepcopy
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.modeling.generated_tables import pack_final
from test_generated_final import plan
from compertum import audit_generated_final as audit


def packet():
 p=plan(('momentum-h01',));book={k:[] for k in ('trades','observations','days','signals','omissions')}
 folds=[dict(year=year,model_sha256=None,predictions=dict(rows=[],omissions=[],daily_rank_correlation=[]),replays={cost:dict(portfolios={name:deepcopy(book) for name in ('strategy','spy60','spy100','equal60','zero')}) for cost in ('10','20')},checks={cost:dict(policy=dict(holding_intervals=[])) for cost in ('10','20')}) for year in (2024,2025)]
 value=dict(schema='generated-final-batch-v1',status='SYNTHETIC_ENGINEERING',authority='NO_OWNER_ADMISSION_FROM_PURE_COMPUTATION',plan_sha256=hashlib.sha256(canonical(p)).hexdigest(),evaluation_id=p['evaluation_id'],checkpoint_id=p['checkpoint_id'],inputs=p['inputs'],market={},fits=[],candidates=[dict(candidate_id='momentum-h01',folds=folds,qualification=dict(inputs=dict(predictions=[],intervals=[])))],financial_accepted=False,full_M3=False)
 return p,value


def invoke(p,v):
 a=canonical(p);b=pack_final(v)
 return audit.audit_generated_final(a,b,plan_sha256=hashlib.sha256(a).hexdigest(),payload_sha256=hashlib.sha256(b).hexdigest())


@pytest.mark.parametrize('change',['plan_hash','evaluation','checkpoint','inputs','candidate','extra_candidate','year_order','extra_field','financial','full','author','fit'])
def test_rehashed_wrong_consumed_binding_rejected_before_prices(change,monkeypatch):
 p,v=packet();seen=[]
 def forbidden(*a,**k):seen.append(True);raise AssertionError('generated before binding checked')
 monkeypatch.setattr(audit,'generate_market',forbidden)
 if change=='plan_hash':v['plan_sha256']='0'*64
 elif change=='evaluation':v['evaluation_id']='11111111-1111-4111-8111-111111111111'
 elif change=='checkpoint':v['checkpoint_id']='11111111-1111-4111-8111-111111111111'
 elif change=='inputs':v['inputs']=dict(v['inputs'],protocol_sha256='0'*64)
 elif change=='candidate':v['candidates'][0]['candidate_id']='momentum-h05'
 elif change=='extra_candidate':v['candidates'].append(deepcopy(v['candidates'][0]))
 elif change=='year_order':v['candidates'][0]['folds'].reverse()
 elif change=='extra_field':v['broker_origin']='https://example.invalid'
 elif change=='financial':v['financial_accepted']=True
 elif change=='full':v['full_M3']=True
 elif change=='author':v['authority']='TRUST_ME'
 else:v['fits']=[dict(candidate_id='momentum-h01',year=2024,rows=[],omissions=[],provenance=[],manifest=dict(included=[],excluded=[]))]
 with pytest.raises(DataError):invoke(p,v)
 assert seen==[]


@pytest.mark.parametrize('kind',['plan_bytes','payload_bytes','plan_digest','payload_digest'])
def test_invalid_outer_bytes_refuse_before_generation(kind,monkeypatch):
 p,v=packet();a=canonical(p);b=pack_final(v);ah=hashlib.sha256(a).hexdigest();bh=hashlib.sha256(b).hexdigest()
 monkeypatch.setattr(audit,'generate_market',lambda *a,**k:pytest.fail('generated before validation'))
 if kind=='plan_bytes':a=b'{}'
 elif kind=='payload_bytes':b=b'{}'
 elif kind=='plan_digest':ah='0'*64
 else:bh='0'*64
 with pytest.raises(DataError):audit.audit_generated_final(a,b,plan_sha256=ah,payload_sha256=bh)
