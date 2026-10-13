"""Campaign result framing binds phase, identity and dependency without refitting."""
from functools import lru_cache
import json
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.modeling.campaign import build_campaign,compute_campaign_unit
from compertum.simulation.runs import runtime_identity
from compertum.simulation.campaign_record import pack_result,verify_result
from helpers.saved_campaign_fixture import campaign_folds

@lru_cache(maxsize=1)
def result():
    identity=runtime_identity();c=build_campaign(campaign_folds(),identity=identity)
    raw=compute_campaign_unit(c,0,identity=identity).content
    return raw,c.sha256,pack_result(raw,c.sha256,0)


def test_frame_round_trip_and_distinct_header():
    body,pin,raw=result();assert raw!=body and verify_result(raw,pin,0)==body

@pytest.mark.parametrize('field',['phase','candidate_id','year','unit','input_sha256','dependency_sha256','payload_sha256','payload_bytes'])
def test_changed_header_refused(field):
    body,pin,raw=result();header=json.loads(raw.split(b'\n',1)[0]);header[field]='changed'
    with pytest.raises(DataError):verify_result(canonical(header)+b'\n'+body,pin,0)


def test_changed_financial_status_or_wrong_unit_is_refused():
    body,pin,raw=result();value=json.loads(body);value['financial_accepted']=True
    with pytest.raises(DataError):pack_result(canonical(value),pin,0)
    with pytest.raises(DataError):verify_result(raw,pin,1)
    with pytest.raises(DataError):verify_result(raw,pin,0,'0'*64)

@pytest.mark.parametrize('mutation',['strip','pid','plan','schema','extra'])
def test_startup_frame_cannot_downgrade_or_change_launch_binding(mutation):
 body,pin,legacy=result();proof={'schema':'observed-python-startup-v1','pid':123,'plan_sha256':'f'*64}
 frame=pack_result(body,pin,0,startup=proof)
 assert verify_result(frame,pin,0,expected_startup=proof)==body
 assert verify_result(frame,pin,0)==body
 with pytest.raises(DataError):verify_result(legacy,pin,0,expected_startup=proof)
 with pytest.raises(DataError):verify_result(frame,pin,0,expected_startup=None)
 header=json.loads(frame.split(b'\n',1)[0])
 if mutation=='strip':header.pop('startup');header['format']='compertum-campaign-unit-v1'
 elif mutation=='pid':header['startup']['pid']+=1
 elif mutation=='plan':header['startup']['plan_sha256']='0'*64
 elif mutation=='schema':header['format']='compertum-campaign-unit-v1'
 else:header['startup']['approved']=True
 with pytest.raises(DataError):verify_result(canonical(header)+b'\n'+body,pin,0,expected_startup=proof)
