"""Private native order transport. No operator route, grant or retry mechanism.

The eventual execution factory must consume a durable intent and enforce all
account, plan and health checks before invoking this backend. Loopback is a
private native-test boundary and accepts only invented test headers.
"""
from urllib.parse import urlencode
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier, client_id, order_body, require
from .errors import RuntimeRefused
from ._winhttp_get import _OwnedHTTP


def _wire(operation,parameters,body):
    try:
        require(type(operation) is str and (parameters is None or type(parameters) is dict))
        parameters={} if parameters is None else parameters.copy()
        if operation=='SUBMIT_ORDER':
            require(not parameters)
            return 'POST','/v2/orders',canonical(order_body(body))
        require(body is None)
        if operation in ('CANCEL_ORDER','ORDER_BY_ID'):
            require(set(parameters)=={'order_id'})
            return ('DELETE' if operation=='CANCEL_ORDER' else 'GET'),'/v2/orders/'+identifier(parameters['order_id']),b''
        require(operation=='ORDER_BY_CLIENT_ID' and set(parameters)=={'client_order_id'})
        client_id(parameters['client_order_id'])
        return 'GET','/v2/orders:by_client_order_id?'+urlencode(parameters),b''
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError):
        raise RuntimeRefused('HTTP_ORDER_INPUT_INVALID') from None


class _OwnedOrderHTTP(_OwnedHTTP):
    def __init__(self,lease,*,operation,parameters=None,body=None,headers,timeout=10,_test_port=None,_permit=None,_deadline_at=None):
        method,path,wire=_wire(operation,parameters,body)
        if _test_port is not None and (type(_test_port) is not int or not 1<=_test_port<=65535):
            raise RuntimeRefused('HTTP_ORDER_INPUT_INVALID')
        super().__init__(lease,host='paper-api.alpaca.markets' if _test_port is None else '127.0.0.1',
                         port=443 if _test_port is None else _test_port,secure=_test_port is None,path=path,
                         headers=headers,timeout=timeout,method=method,body=wire,_permit=_permit,_deadline_at=_deadline_at)

    def _accept_status(self,code):
        # Error bodies are bounded private observations, never financial effects.
        return code==(204 if self._method=='DELETE' else 200) or 400<=code<=599
