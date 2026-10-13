"""Small identity header followed by canonical replay bytes from the trusted worker."""
import hashlib,json
from compertum.data.errors import DataError
from compertum.data.encoding import canonical


def pack_result(raw,input_sha256):
    result=json.loads(raw)
    identity=({'format':'compertum-prediction-v1','method':result['method'],'scoring_as_of':result['scoring_as_of']}
        if 'method' in result else {'format':'compertum-provider-replay-v1' if result['policy']=='momentum-provider-engineering-v1' else 'compertum-replay-v1','cost_bps':result['cost_bps'],'policy':result['policy']})
    header={**identity,'input_sha256':input_sha256,
        'horizon':result['horizon'],'financial_status':result['financial_status'],
        'payload_sha256':hashlib.sha256(raw).hexdigest(),'payload_bytes':len(raw)}
    return canonical(header)+b'\n'+raw


def verify_result(raw,input_sha256,horizon,cost_bps,*,scoring_as_of=None,input_kind='synthetic'):
    """Coordinator checks the trusted worker's binding without decoding bulk JSON."""
    try:
        if input_kind not in ('synthetic','provider-diagnostic') or (input_kind=='provider-diagnostic' and (cost_bps is None or scoring_as_of is not None)):raise ValueError()
        provider=input_kind=='provider-diagnostic'
        end=raw.index(b'\n',0,4096);header=json.loads(raw[:end]);body=raw[end+1:]
        identity=({'format':'compertum-prediction-v1','method':'daily-momentum-price-label-v1','scoring_as_of':scoring_as_of}
            if cost_bps is None else {'format':'compertum-provider-replay-v1' if provider else 'compertum-replay-v1','cost_bps':cost_bps,'policy':'momentum-provider-engineering-v1' if provider else 'momentum-synthetic-v1'})
        expected={**identity,'input_sha256':input_sha256,'horizon':horizon,'financial_status':'REAL_ENGINEERING_DIAGNOSTIC' if provider else 'SYNTHETIC_UNVERIFIED',
            'payload_sha256':hashlib.sha256(body).hexdigest(),'payload_bytes':len(body)}
        if header!=expected or not body.startswith(b'{') or not body.endswith(b'}'):raise ValueError()
        return body
    except (ValueError,TypeError,KeyError):raise DataError('RUN_ARTIFACT_CORRUPT') from None
