"""Private fixed-origin asset GET; no account confirmation or authority."""
from compertum.domain import ContractError
from compertum.paper_market_inputs import OperationalMarketRequest,_sha
from .errors import RuntimeRefused
from .owners import _owner_scope,require_live_owner
from ._winhttp_get import _OwnedHTTP,_syntax,_header_values

def _need(value):
    if not value:raise RuntimeRefused('HTTP_ASSET_INPUT_INVALID')

def _wire(request):
    try:
        _need(type(request) is OperationalMarketRequest);request.__post_init__();p=request.to_payload()
        _need(p['operation']=='ASSET' and p['origin']=='https://paper-api.alpaca.markets' and p['method']=='GET')
        return request.plan,request.content,p['target']
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError):raise RuntimeRefused('HTTP_ASSET_INPUT_INVALID') from None

class _OwnedAssetGet(_OwnedHTTP):
    def __init__(self,lease,*,request,headers,timeout=10,_test_port=None,_deadline_at=None,_pre_send=None,_permit=None):
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution');plan,raw,target=_wire(request)
            _need(plan.to_payload()['project_id']==state.project.project_id)
            _need(_test_port is None or type(_test_port) is int and 1<=_test_port<=65535)
            _need(_pre_send is None or callable(_pre_send));self._pre_send=_pre_send
            self._source_request=request
            self._request_bytes=raw;self._request_sha256=_sha(raw);self._plan_sha256=plan.sha256;self._asset_target=target
            self._asset_origin=('paper-api.alpaca.markets',443,True) if _test_port is None else ('127.0.0.1',_test_port,False)
            host,port,secure=self._asset_origin
            super().__init__(lease,host=host,port=port,secure=secure,path=target,headers=headers,timeout=timeout,method='GET',body=b'',_deadline_at=_deadline_at,_permit=_permit)
    def _before_send(self):
        if self._pre_send is not None:self._pre_send()
    def _validate_inputs(self,host,port,secure,path,headers,timeout,method,body):
        _syntax(host,port,secure,path,headers,timeout)
        _need(method=='GET' and type(body) is bytes and body==b'' and (host,port,secure)==self._asset_origin and path==self._asset_target)
        _header_values(headers,{'APCA-API-KEY-ID','APCA-API-SECRET-KEY'} if secure else {'X-Compertum-Test'})
    def _accept_status(self,code):return code==200 or 400<=code<=599
