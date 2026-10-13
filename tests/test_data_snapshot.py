import copy,hashlib,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parent/'helpers'))
from data_fixture import batch,encoded,split_batch
from compertum.data import DataError,validate_snapshot,feature_rows
from compertum.data.calendar import session_times

def test_calendar_dst_and_early_close_are_hand_checked():
 assert session_times('2024-03-08').open.isoformat()=='2024-03-08T14:30:00+00:00'
 assert session_times('2024-03-11').decision.isoformat()=='2024-03-11T13:25:00+00:00'
 assert session_times('2024-11-29').close.isoformat()=='2024-11-29T18:00:00+00:00'
 assert session_times('2024-11-29').close_reference.isoformat()=='2024-11-29T17:59:00+00:00'
 with pytest.raises(DataError):session_times('2024-03-09')

def test_stable_snapshot_and_features_never_include_future_minute_reference():
 b=batch();one=validate_snapshot(encoded(b));b['bars'].reverse();b['bars'][0]['open']='100.000'
 two=validate_snapshot(encoded(b));assert one.content==two.content and one.sha256==two.sha256
 assert hashlib.sha256(one.content).hexdigest()==one.sha256
 rows=feature_rows(one,'2024-03-11');assert len(rows)==2
 assert all(r['reference']=='daily' and r['session_date']=='2024-03-08' for r in rows)
 rows[0]['close']='999';assert feature_rows(one,'2024-03-11')[0]['close']=='105'

@pytest.mark.parametrize('mutation,reason',[
 (lambda b:b['bars'].append(copy.deepcopy(b['bars'][0])),'DUPLICATE_ROW'),
 (lambda b:b['bars'].pop(),'MISSING_ROW'),
 (lambda b:b['bars'][0].update(feed='sip'),'FEED_MISMATCH'),
 (lambda b:b['bars'][0].update(close='NaN'),'INVALID_NUMBER'),
 (lambda b:b['bars'][0].update(low='111'),'INVALID_OHLC'),
 (lambda b:b['bars'][0].update(open=100),'INVALID_NUMBER'),
 (lambda b:b['bars'][0].update(volume='-1'),'INVALID_NUMBER'),
 (lambda b:b['source'].update(provider='alpaca'),'SYNTHETIC_ONLY'),
 (lambda b:b['source'].update(aggregation='REGULAR_HOURS'),'INVALID_SOURCE'),
 (lambda b:b['bars'][0].update(unknown='field'),'INVALID_FIELDS'),
 (lambda b:b['bars'][0].update(simulated_available_at='2024-03-08T05:00:00Z'),'AVAILABILITY_BEFORE_POLICY'),
 (lambda b:b['bars'][0].update(first_seen_at='2026-10-10T00:00:00Z'),'ACTUAL_TIME_ORDER'),
 (lambda b:b['bars'][0].update(bar_label_time='2024-03-08T00:00:00'),'INVALID_TIME'),
 (lambda b:b['bars'][2].update(bar_label_time='2024-03-08T21:00:00Z'),'REFERENCE_TIME'),
 (lambda b:b['bars'][1].update(close='104'),'ADJUSTMENT_MISMATCH'),
])
def test_bad_data_is_rejected(mutation,reason):
 b=batch();mutation(b)
 with pytest.raises(DataError,match=reason):validate_snapshot(encoded(b))

def test_duplicate_keys_and_large_or_unsafe_input_are_rejected():
 for raw,reason in [(b'{"x":1,"x":2}','DUPLICATE_KEY'),(b'x'*(1024*1024+1),'INPUT_BOUND'),(b'{"password":"not-a-real-secret"}','SENSITIVE_INPUT')]:
  with pytest.raises(DataError,match=reason):validate_snapshot(raw)

def test_late_revision_cannot_enter_frozen_feature_bundle():
 b=batch();b['bars'][0]['simulated_revision_available_at']='2024-03-11T13:26:00Z'
 snapshot=validate_snapshot(encoded(b))
 with pytest.raises(DataError,match='FEATURE_UNAVAILABLE'):feature_rows(snapshot,'2024-03-11')
 with pytest.raises(DataError,match='FEATURE_COVERAGE'):feature_rows(snapshot,'2024-03-12')

def test_split_adjustment_uses_declared_factor_and_unknown_knowledge_is_diagnostic():
 b=split_batch();s=validate_snapshot(encoded(b));assert 'ACTION_KNOWLEDGE_UNVERIFIED' in s.diagnostics
 rows=feature_rows(s,'2024-03-11');assert next(r for r in rows if r['adjustment']=='split')['close']=='52.5'
 b['bars'][1]['volume']='1000'
 with pytest.raises(DataError,match='ADJUSTMENT_MISMATCH'):validate_snapshot(encoded(b))

def test_action_dates_and_conflicts_reject():
 b=split_batch();b['actions'].append(copy.deepcopy(b['actions'][0]))
 with pytest.raises(DataError,match='DUPLICATE_ACTION'):validate_snapshot(encoded(b))
 b=split_batch();b['actions'][0]['factor']='0'
 with pytest.raises(DataError):validate_snapshot(encoded(b))
 b=batch();b['actions']=[{'action_id':'div-1','asset_id':'fixture-a','kind':'DIVIDEND','effective_session':'2024-03-08','ex_date':'2024-03-08','pay_date':'2024-03-07','factor':None,'amount':'1','first_known_at':None,'simulated_known_at':'2024-03-07T14:00:00Z','lineage':'synthetic-fixture'}]
 with pytest.raises(DataError,match='ACTION_DATES'):validate_snapshot(encoded(b))

def test_corrected_snapshot_preserves_original_identity():
 b=batch();a=validate_snapshot(encoded(b));b['bars'][0]['close']=b['bars'][1]['close']='106';c=validate_snapshot(encoded(b))
 assert a.sha256!=c.sha256 and json.loads(a.content)['bars'][0]['close']=='105'

@pytest.mark.parametrize('value',[[],{},True,20240308,None])
def test_malformed_session_types_are_stable_rejections(value):
 b=batch();b['bars'][0]['session_date']=value
 with pytest.raises(DataError,match='INVALID_DATE'):validate_snapshot(encoded(b))


def test_escaped_sensitive_key_is_rejected_before_schema_validation():
 raw=b'{"\\u0070assword":"never-retain-this-value"}'
 with pytest.raises(DataError,match='SENSITIVE_INPUT'):validate_snapshot(raw)


def test_future_unknown_split_cannot_change_a_past_feature():
 b=split_batch();b['feature_sessions'][0]='2024-03-07'
 for row in b['bars'][:4]:
  if row['reference']=='entry':
   row.update(session_date='2024-03-08',bar_label_time='2024-03-08T14:35:00Z',provider_timestamp='2024-03-08T14:35:00Z',simulated_available_at='2024-03-08T14:51:00Z',simulated_revision_available_at='2024-03-08T14:51:00Z')
  elif row['reference']=='close':
   row.update(session_date='2024-03-07',bar_label_time='2024-03-07T20:59:00Z',provider_timestamp='2024-03-07T20:59:00Z',simulated_available_at='2024-03-07T21:15:00Z',simulated_revision_available_at='2024-03-07T21:15:00Z')
  else:row.update(session_date='2024-03-07',bar_label_time='2024-03-07T05:00:00Z',provider_timestamp='2024-03-07T05:00:00Z',simulated_available_at='2024-03-08T14:25:00Z',simulated_revision_available_at='2024-03-08T14:25:00Z')
 b['actions'][0]['simulated_known_at']='2024-03-11T13:00:00Z'
 with pytest.raises(DataError,match='ACTION_UNAVAILABLE'):feature_rows(validate_snapshot(encoded(b)),'2024-03-08')

@pytest.mark.parametrize('location',['sessions','actions'])
def test_malformed_nested_session_types_are_stable_rejections(location):
 b=split_batch()
 if location=='sessions':b['feature_sessions'][0]={}
 else:b['actions'][0]['effective_session']=[]
 with pytest.raises(DataError,match='INVALID_DATE'):validate_snapshot(encoded(b))
