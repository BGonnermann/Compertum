"""Hand-set synthetic prices and exchange timestamps, never provider evidence."""
import copy,json

def batch():
 source={'provider':'synthetic','feed':'iex','vintage':'fixture-v1','availability_basis':'SIMULATED_AVAILABILITY','aggregation':'PROVIDER_DAILY'}
 def row(reference,adjustment,session,label,available):
  return {'asset_id':'fixture-a','session_date':session,'reference':reference,'adjustment':adjustment,'feed':'iex','revision_id':'r1',
   'bar_label_time':label,'provider_timestamp':label,'retrieved_at':'2026-10-09T00:00:00Z','first_seen_at':'2026-10-09T00:00:00Z','feature_available_at':'2026-10-09T00:00:00Z',
   'simulated_available_at':available,'simulated_revision_available_at':available,'open':'100','high':'110','low':'90','close':'105','volume':'1000'}
 return {'schema_version':'1','source':source,'assets':[{'asset_id':'fixture-a','symbol':'AAPL'}],'feature_sessions':['2024-03-08'],'actions':[],
  'bars':[row('daily','raw','2024-03-08','2024-03-08T05:00:00Z','2024-03-11T13:25:00Z'),
   row('daily','split','2024-03-08','2024-03-08T05:00:00Z','2024-03-11T13:25:00Z'),
   row('close','raw','2024-03-08','2024-03-08T20:59:00Z','2024-03-08T21:15:00Z'),
   row('entry','raw','2024-03-11','2024-03-11T13:35:00Z','2024-03-11T13:51:00Z')]}

def encoded(value):return json.dumps(value).encode()

def split_batch():
 b=batch();later=copy.deepcopy(b['bars'])
 for row in later:
  if row['reference']=='entry':
   row.update(session_date='2024-03-12',bar_label_time='2024-03-12T13:35:00Z',provider_timestamp='2024-03-12T13:35:00Z',simulated_available_at='2024-03-12T13:51:00Z',simulated_revision_available_at='2024-03-12T13:51:00Z')
  elif row['reference']=='close':
   row.update(session_date='2024-03-11',bar_label_time='2024-03-11T19:59:00Z',provider_timestamp='2024-03-11T19:59:00Z',simulated_available_at='2024-03-11T20:15:00Z',simulated_revision_available_at='2024-03-11T20:15:00Z')
  else:row.update(session_date='2024-03-11',bar_label_time='2024-03-11T04:00:00Z',provider_timestamp='2024-03-11T04:00:00Z',simulated_available_at='2024-03-12T13:25:00Z',simulated_revision_available_at='2024-03-12T13:25:00Z')
 b['bars']+=later;b['feature_sessions'].append('2024-03-11')
 for key in ('open','high','low','close'):b['bars'][1][key]=str(int(b['bars'][1][key])/2)
 b['bars'][1]['volume']='2000'
 b['actions']=[{'action_id':'split-1','asset_id':'fixture-a','kind':'SPLIT','effective_session':'2024-03-11','ex_date':None,'pay_date':None,'factor':'2','amount':None,'first_known_at':None,'simulated_known_at':'2024-03-07T14:00:00Z','lineage':'synthetic-fixture'}]
 return b
