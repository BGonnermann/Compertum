"""Private GET-only data adapter; no grant, collection loop or public route."""
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_market_inputs import OperationalMarketRequest, _sha
from compertum.paper_action_inputs import CurrentActionQuery, _request_payload
from .errors import RuntimeRefused
from .owners import _owner_scope, require_live_owner
from ._winhttp_get import _OwnedHTTP, _syntax, _header_values


def _need(value):
    if not value:
        raise RuntimeRefused('HTTP_DATA_INPUT_INVALID')


def _wire(request, request_id, requested_at, page_token):
    try:
        if type(request) is OperationalMarketRequest:
            _need(request_id is None and requested_at is None and page_token is None)
            request.__post_init__()
            value = request.to_payload()
            _need(value['operation'] in ('QUOTE', 'HISTORY'))
            plan = request.plan
        else:
            _need(type(request) is CurrentActionQuery)
            value = _request_payload(request, request_id, requested_at, page_token)
            plan = request.plan
        _need(value['origin'] == 'https://data.alpaca.markets' and value['method'] == 'GET')
        return plan, canonical(value), value['target']
    except (ContractError, ValueError, TypeError, KeyError, UnicodeError):
        raise RuntimeRefused('HTTP_DATA_INPUT_INVALID') from None


class _OwnedDataGet(_OwnedHTTP):
    def __init__(self, lease, *, request, headers, timeout=10, _test_port=None,
                 action_request_id=None, action_requested_at=None, action_page_token=None, _deadline_at=None, _pre_send=None,_permit=None):
        with _owner_scope(lease) as state:
            require_live_owner(lease, 'execution')
            plan, raw, target = _wire(request, action_request_id, action_requested_at, action_page_token)
            _need(plan.to_payload()['project_id'] == state.project.project_id)
            _need(_pre_send is None or callable(_pre_send));self._pre_send=_pre_send
            _need(_test_port is None or type(_test_port) is int and 1 <= _test_port <= 65535)
            self._source_request=request
            self._request_bytes, self._request_sha256 = raw, _sha(raw)
            self._plan_sha256, self._data_target = plan.sha256, target
            self._data_origin = ('data.alpaca.markets', 443, True) if _test_port is None else ('127.0.0.1', _test_port, False)
            host, port, secure = self._data_origin
            super().__init__(lease, host=host, port=port, secure=secure, path=target,
                             headers=headers, timeout=timeout, method='GET', body=b'', _deadline_at=_deadline_at,_permit=_permit)

    def _before_send(self):
        if self._pre_send is not None:self._pre_send()

    def _validate_inputs(self, host, port, secure, path, headers, timeout, method, body):
        _syntax(host, port, secure, path, headers, timeout, target_limit=4096)
        _need(method == 'GET' and type(body) is bytes and body == b'')
        _need((host, port, secure) == self._data_origin and path == self._data_target)
        expected = {'APCA-API-KEY-ID', 'APCA-API-SECRET-KEY'} if secure else {'X-Compertum-Test'}
        _header_values(headers, expected)

    def _accept_status(self, code):
        return code == 200 or 400 <= code <= 599
