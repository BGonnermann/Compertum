"""Pure v2 encrypted-frame validation; encryption/native ownership tested separately."""
import json
from uuid import UUID
import pytest
from compertum.data.encoding import canonical
from compertum.paper_market_inputs import _sha
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_market_evidence import _validate
import test_paper_market_attempts as f

PROJECT='a'*64;ALIAS='paper-primary';TASK=str(UUID(int=500));CID=str(UUID(int=600))

def frames(chain=None,mode='HISTORY',state='PAGINATION_COMPLETE',reason=None):
 if chain is None:chain=[f.entry(mode=mode,status=429,outcome='RETRY'),f.entry(2,ordinal=2,mode=mode,at=2.2)]
 projection=f.check(chain,mode)
 v=dict(version=2,record_type='PrivateOperationalCollection',purpose='OPERATIONAL_ONLY',collection_id=CID,mode=mode,plan=f.plan().to_payload(),
        started_at=f.stamp(0),validated_at=projection['validated_at'],state=state,reason=reason,attempts=len(chain),attempt_chain=chain,
        selected_requests=[r['request']['request_id'] for r in projection['records']],started_monotonic_ns=f.START,deadline_monotonic_ns=f.START+80*f.NS,
        aggregate=None if projection['aggregate'] is None else json.loads(projection['aggregate']),aggregate_error=None,
        complete_by_cutoff=state=='PAGINATION_COMPLETE',native_provenance=projection['native_provenance'],clock_basis='SYNTHETIC_FIXTURE',
        research_eligible=False,financial_accepted=False,transport_authorized=False)
 meta=dict(version=1,record_type='PrivateMarketEvidence',purpose='OPERATIONAL_ONLY',project_id=PROJECT,account_alias=ALIAS,task_id=TASK,collection_id=CID,
           execution_generation=1,credential_sha256='b'*64,snapshot_sha256=_sha(canonical(v)))
 return [canonical(meta),canonical(v)]

def validate(fs):return _validate(fs,PROJECT,ALIAS,TASK,CID)

def replace(fs,v):
 meta=json.loads(fs[0]);meta['snapshot_sha256']=_sha(canonical(v));return [canonical(meta),canonical(v)]

@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
def test_v2_exact_full_attempt_evidence_and_successful_projection(mode):
 fs=frames(mode=mode);v=validate(fs)
 assert canonical(v['collection'])==fs[1]
 assert len(v['selected_records'])==1 and len(v['collection']['attempt_chain'])==2
 assert v['selected_records'][0]['diagnostic']==v['collection']['attempt_chain'][1]['reply']['diagnostic']
 assert v['use']=='HISTORICAL_ONLY' and v['freshness']=='NOT_RESTORED'
 assert not any(v[k] for k in ('transport_authorized','financial_accepted','research_eligible'))

@pytest.mark.parametrize('committed',[False,True])
def test_no_response_terminal_roundtrip(committed):
 a=f.entry(outcome='TERMINAL',reason='DISPATCH_FAILED');a.update(reply=None,observed_status=None)
 if not committed:a.update(pre_send_at=None,pre_send_monotonic_ns=None,dispatch_committed_ns=None)
 fs=frames([a],state='INCOMPLETE',reason='DISPATCH_FAILED');v=validate(fs)
 assert v['selected_records']==[] and v['collection']['attempt_chain'][0]['reply'] is None

@pytest.mark.parametrize('reason',['CANCELLED','TOTAL_DEADLINE','RETENTION_LIMIT'])
def test_stopped_during_retry_wait_retains_failed_body(reason):
 fs=frames([f.entry(status=503,outcome='RETRY')],state='INCOMPLETE',reason=reason);v=validate(fs)
 assert v['selected_records']==[] and 'temporary failure' in v['collection']['attempt_chain'][0]['reply']['body_utf8']

def test_exhausted_page_attempts_roundtrip():
 chain=[f.entry(status=503,outcome='RETRY'),f.entry(2,ordinal=2,status=503,at=2.2,outcome='RETRY'),f.entry(3,ordinal=3,status=503,at=6.4,outcome='TERMINAL',reason='PAGE_ATTEMPT_LIMIT')]
 assert validate(frames(chain,state='INCOMPLETE',reason='HTTP_REFUSED'))['selected_records']==[]

@pytest.mark.parametrize('mutation',['version','extra','attempts','selected','aggregate','error','validated','provenance','clock','purpose','research','financial','transport','complete_flag','complete_reason','deadline','start','state','terminal_reason','body_hash'])
def test_tampering_refused(mutation):
 fs=frames();v=json.loads(fs[1])
 if mutation=='version':v['version']=3
 elif mutation=='extra':v['extra']=1
 elif mutation=='attempts':v['attempts']=1
 elif mutation=='selected':v['selected_requests']=[]
 elif mutation=='aggregate':v['aggregate']['financial_accepted']=True
 elif mutation=='error':v['aggregate_error']='AGGREGATE_UNVERIFIED'
 elif mutation=='validated':v['validated_at']=f.stamp(0)
 elif mutation=='provenance':v['native_provenance']='DATA_TLS'
 elif mutation=='clock':v['clock_basis']='LOCAL_CLOCK'
 elif mutation=='purpose':v['purpose']='RESEARCH'
 elif mutation=='research':v['research_eligible']=True
 elif mutation=='financial':v['financial_accepted']=True
 elif mutation=='transport':v['transport_authorized']=True
 elif mutation=='complete_flag':v['complete_by_cutoff']=False
 elif mutation=='complete_reason':v['reason']='CANCELLED'
 elif mutation=='deadline':v['deadline_monotonic_ns']+=1
 elif mutation=='start':v['started_monotonic_ns']-=1
 elif mutation=='state':v['state']='READY'
 elif mutation=='terminal_reason':v.update(state='INCOMPLETE',complete_by_cutoff=False,reason='HTTP_REFUSED')
 else:v['attempt_chain'][0]['reply']['diagnostic']['raw_sha256']='0'*64
 with pytest.raises(RuntimeRefused):validate(replace(fs,v))


def test_v1_bytes_and_result_shape_unchanged():
 fs=frames([f.entry()]);v=json.loads(fs[1]);rows=f.check(v['attempt_chain'])['records']
 for k in ('attempt_chain','selected_requests','started_monotonic_ns','deadline_monotonic_ns'):del v[k]
 v.update(version=1,records=rows);fs=replace(fs,v);before=tuple(fs);result=validate(fs)
 assert tuple(fs)==before and canonical(result['collection'])==fs[1]
 assert set(result)=={'metadata','collection','use','purpose','freshness','provenance','transport_authorized','financial_accepted','research_eligible'}
 assert result['collection']['records'][0]['diagnostic']==rows[0]['diagnostic']
def test_queue_wait_reaching_cutoff_before_first_attempt_is_retained():
 result=validate(frames([],state='INCOMPLETE',reason='INFORMATION_CUTOFF'))
 assert result['collection']['attempts']==0 and result['selected_records']==[]
 assert result['collection']['attempt_chain']==[] and result['collection']['native_provenance']=='UNVERIFIED'