"""Fixed-origin activity GET. Only the registered producer can dispatch it."""
from compertum.paper_activity_records import PreparedActivityRequest,sha
from .errors import RuntimeRefused
from ._winhttp_get import _OwnedHTTP,_syntax,_header_values


class _OwnedActivityGet(_OwnedHTTP):
    def __init__(self,producer,request,headers,permit,timeout):
        if type(request) is not PreparedActivityRequest or permit is None:raise RuntimeRefused('ACTIVITY_REQUEST_INVALID')
        request.__post_init__();p=request.to_payload()
        if p['project_id']!=producer._lease.project_id:raise RuntimeRefused('ACTIVITY_REQUEST_INVALID')
        self._producer=producer;self._source_request=request;self._request_bytes=request.content
        self._request_sha256=sha(request.content);self._target=p['target']
        self._activity_origin=('paper-api.alpaca.markets',443,True) if producer._port is None else ('127.0.0.1',producer._port,False)
        host,port,secure=self._activity_origin
        super().__init__(producer._lease,host=host,port=port,secure=secure,path=self._target,headers=headers,
            timeout=timeout,method='GET',body=b'',_deadline_at=producer._deadline_ns/10**9,_permit=permit)
    def _native_initialized(self):self._producer._attach(self)
    def _before_send(self):self._producer._before_send(self)
    def _send_committed(self):self._producer._committed(self)
    def _validate_inputs(self,host,port,secure,path,headers,timeout,method,body):
        _syntax(host,port,secure,path,headers,timeout)
        if (host,port,secure)!=self._activity_origin or path!=self._target or method!='GET' or body!=b'':
            raise RuntimeRefused('ACTIVITY_REQUEST_INVALID')
        _header_values(headers,{'APCA-API-KEY-ID','APCA-API-SECRET-KEY'} if secure else {'X-Compertum-Test'})
