"""Private cooperative native GET backend; no public paper/account capability.

The eventual paper factory must bind its own scoped grant, fixed origin and
route. The only alternate native test endpoint is loopback with test headers.
"""
from collections import deque
from dataclasses import dataclass
from datetime import datetime,timezone
import ctypes as c
import hashlib
import math
import os
import re
import threading
import time

from .errors import RuntimeRefused
from .http_retry import _RetryAfter,normalize_retry_after
from .owners import _MUTEX, _owner_scope, require_live_owner

H=c.c_void_p;D=c.c_uint32;B=c.c_int32;P=c.c_size_t;W=c.c_wchar_p
PD=c.POINTER(D)
SEND=0x00400000;HEADERS=0x00020000;READ=0x00080000;ERROR=0x00200000;CLOSING=0x800
_PENDING={}

def _utc_now():return datetime.now(timezone.utc)


class ASYNC_RESULT(c.Structure):
    _fields_=[('dwResult',P),('dwError',D)]


class FAILED_CONNECTION_RETRIES(c.Structure):
    _fields_=[('maximum',D),('conditions',D)]


class _API:
    def __init__(self):
        if os.name!='nt':raise RuntimeRefused('NATIVE_WINDOWS_UNAVAILABLE')
        self.dll=c.WinDLL('winhttp',use_last_error=True)
        self.callback_type=c.WINFUNCTYPE(None,H,P,D,H,D)
        def bind(name,result,*args):
            fn=getattr(self.dll,'WinHttp'+name);fn.restype=result;fn.argtypes=list(args);setattr(self,name,fn)
        bind('Open',H,W,D,W,W,D)
        bind('Connect',H,H,W,c.c_uint16,D)
        bind('OpenRequest',H,H,W,W,W,W,c.POINTER(W),D)
        bind('SetStatusCallback',H,H,self.callback_type,D,P)
        bind('SetOption',B,H,D,H,D)
        bind('SetTimeouts',B,H,c.c_int,c.c_int,c.c_int,c.c_int)
        bind('SendRequest',B,H,W,D,H,D,D,P)
        bind('ReceiveResponse',B,H,H)
        bind('QueryHeaders',B,H,D,W,H,PD,PD)
        bind('ReadData',B,H,H,D,PD)
        bind('CloseHandle',B,H)


def _checked(result):
    if not result:raise RuntimeRefused('HTTP_NATIVE_FAILED')
    return result


def _syntax(host,port,secure,path,headers,timeout,*,target_limit=2048):
    if (type(host) is not str or type(port) is not int or not 1<=port<=65535 or type(secure) is not bool
            or type(path) is not str or not 1<=len(path)<=target_limit or not path.startswith('/') or path.startswith('//')
            or re.fullmatch(r'[\x21-\x7e]+',path) is None or '#' in path or '\\' in path
            or type(headers) is not dict or type(timeout) not in (int,float)
            or not 0<timeout<=10 or not math.isfinite(timeout)):raise RuntimeRefused('HTTP_INPUT_INVALID')


def _inputs(host,port,secure,path,headers,timeout):
    _syntax(host,port,secure,path,headers,timeout)
    if host=='paper-api.alpaca.markets' and secure and port==443:
        expected={'APCA-API-KEY-ID','APCA-API-SECRET-KEY'}
    elif host=='127.0.0.1' and not secure:
        expected={'X-Compertum-Test'}
    else:raise RuntimeRefused('HTTP_INPUT_INVALID')
    _header_values(headers,expected)


def _header_values(headers,expected):
    if set(headers)!=expected or any(type(v) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,256}',v) is None for v in headers.values()):
        raise RuntimeRefused('HTTP_INPUT_INVALID')


@dataclass(frozen=True,repr=False)
class _HTTPResult:
    status_code:int
    body:bytes
    retry_after:_RetryAfter|None=None
    def __repr__(self):return '<NativeHTTPResult redacted>'


class _OwnedHTTP:
    def __init__(self,lease,*,host,port,secure,path,headers,timeout,method,body,_deadline_at=None,_permit=None):
        self._lease=lease;self._state=None;self._api_lock=threading.RLock();self._event_lock=threading.Lock()
        self._events=deque();self._closing=threading.Event();self._callback_error=False
        self._session=None;self._connection=None;self._request=None;self._request_id=None
        self._registered=False;self._closed=False;self.native_closed=False;self._cleanup_failed=False
        self._headers=c.create_unicode_buffer(1);self._read=(c.c_ubyte*8192)();self._body=bytearray()
        self._result=None;self._phase='NEW';self._reading=0;self._declared_length=None;self._callback=None
        self._admission=None;self._deadline=0;self.status_code=None;self.retry_after=None;self._method=method;self._upload=c.create_string_buffer(1)
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution')
            self._validate_inputs(host,port,secure,path,headers,timeout,method,body)
            self._origin=(host,port,secure);self._wire_path=path
            if type(method) is not str or method not in ('GET','POST','DELETE') or type(body) is not bytes or len(body)>65536 or (method!='POST' and body):raise RuntimeRefused('HTTP_INPUT_INVALID')
            if _deadline_at is not None and (type(_deadline_at) not in (int,float) or not 0<_deadline_at<=10**12):raise RuntimeRefused('HTTP_INPUT_INVALID')
            self._deadline=time.monotonic()+float(timeout)
            if _deadline_at is not None:self._deadline=min(self._deadline,_deadline_at)
            self._check_deadline()
            if len(_PENDING)>=4 or any(v._lease is lease for v in _PENDING.values()):raise RuntimeRefused('HTTP_BUSY')
            self._wire_body_sha256=hashlib.sha256(body).hexdigest()
            from .service_budget import native_permit,cancel_native
            self._admission=native_permit(self,_permit)
            try:self._api=_API()
            except BaseException:cancel_native(self._admission);raise
            self._state=state;state.resources.append(self);_PENDING[id(self)]=self
            try:
                self._callback=self._api.callback_type(self._on_event)
                self._session=_checked(self._api.Open('Compertum/0.0.1',1,None,None,0x30000000 if secure else 0x10000000))
                _checked(self._api.SetTimeouts(self._session,2000,2000,2000,2000))
                retries=FAILED_CONNECTION_RETRIES(0,0)
                _checked(self._api.SetOption(self._session,162,c.byref(retries),c.sizeof(retries)))
                attempts=D(1)
                _checked(self._api.SetOption(self._session,4,c.byref(attempts),c.sizeof(attempts)))
                self._connection=_checked(self._api.Connect(self._session,host,port,0))
                self._request=_checked(self._api.OpenRequest(self._connection,method,path,None,None,None,0x00800000 if secure else 0))
                self._request_id=self._request
                self._option(63,7)  # Disable cookies, redirects and automatic authentication.
                self._option(88,0)  # Never follow redirects.
                self._option(91,16384)  # Header limit, independently of the body cap.
                context=P(id(self));_checked(self._api.SetOption(self._request,45,c.byref(context),c.sizeof(context)))
                previous=self._api.SetStatusCallback(self._request,self._callback,0x006A0C00,0)
                if previous==H(-1).value:raise RuntimeRefused('HTTP_NATIVE_FAILED')
                self._registered=True
                header=''.join(k+': '+v+'\r\n' for k,v in headers.items())+'Accept-Encoding: identity\r\n'
                if method=='POST':header+='Content-Type: application/json\r\n'
                self._headers=c.create_unicode_buffer(header)
                self._upload=c.create_string_buffer(body,max(1,len(body)))
                self._phase='SEND'
                self._before_send()
                self._check_deadline()
                from .service_budget import commit_native
                commit_native(self._admission)
                self._check_deadline()
                _checked(self._api.SendRequest(self._request,self._headers,len(header),self._upload if body else None,len(body),len(body),id(self)))
            except BaseException:
                self.close()
                raise

    def _before_send(self):pass

    def _validate_inputs(self,host,port,secure,path,headers,timeout,method,body):
        _inputs(host,port,secure,path,headers,timeout)

    def __repr__(self):return '<OwnedNativeHTTP redacted>'

    def _accept_status(self,code):return code==200

    def _option(self,option,value):
        number=D(value);_checked(self._api.SetOption(self._request,option,c.byref(number),c.sizeof(number)))

    def _on_event(self,handle,context,status,info,length):
        # Native callbacks never acquire owner/API locks or initiate another call.
        try:
            if context!=id(self) or handle!=self._request_id:
                self._callback_error=True;return
            if status==CLOSING:
                self._closing.set();return
            with self._event_lock:
                if len(self._events)>=8:self._callback_error=True;return
                if status==READ and (length>8192 or (length and info!=c.addressof(self._read))):
                    self._callback_error=True;return
                if status==ERROR and (not info or length!=c.sizeof(ASYNC_RESULT)):
                    self._callback_error=True;return
                self._events.append((status,length))
        except BaseException:
            self._callback_error=True

    def _query_text(self,kind):
        size=D();index=D()
        if self._api.QueryHeaders(self._request,kind,None,None,c.byref(size),c.byref(index)):
            raise RuntimeRefused('HTTP_HEADERS_INVALID')
        error=c.get_last_error()
        if error==12150:return None  # Header not present.
        if error!=122 or not 2<=size.value<=16384 or size.value%2:
            raise RuntimeRefused('HTTP_HEADERS_INVALID')
        buffer=c.create_unicode_buffer(size.value//2);index=D()
        _checked(self._api.QueryHeaders(self._request,kind,None,buffer,c.byref(size),c.byref(index)))
        second_size=D()
        if self._api.QueryHeaders(self._request,kind,None,None,c.byref(second_size),c.byref(index)) or c.get_last_error()!=12150:
            raise RuntimeRefused('HTTP_HEADERS_INVALID')
        return buffer.value

    def _check_deadline(self):
        if time.monotonic()>=self._deadline:raise RuntimeRefused('HTTP_DEADLINE_EXCEEDED')

    def _read_next(self):
        self._check_deadline()
        self._phase='READ';self._reading=min(8192,65537-len(self._body))
        _checked(self._api.ReadData(self._request,self._read,self._reading,None))

    def poll(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            with self._api_lock:
                if self._result is not None:return self._result
                if self._closed:raise RuntimeRefused('HTTP_CLOSED')
                try:
                    self._check_deadline()
                    if self._callback_error:raise RuntimeRefused('HTTP_CALLBACK_INVALID')
                    with self._event_lock:
                        event=self._events.popleft() if self._events else None
                    if event is None:return None
                    status,length=event
                    if status==ERROR:raise RuntimeRefused('HTTP_NATIVE_FAILED')
                    if status==SEND and self._phase=='SEND':
                        c.memset(self._headers,0,c.sizeof(self._headers));self._phase='HEADERS'
                        self._check_deadline()
                        _checked(self._api.ReceiveResponse(self._request,None))
                    elif status==HEADERS and self._phase=='HEADERS':
                        code=D();size=D(c.sizeof(code))
                        _checked(self._api.QueryHeaders(self._request,19|0x20000000,None,c.byref(code),c.byref(size),None))
                        self.status_code=code.value
                        retry_text=self._query_text(36)  # WINHTTP_QUERY_RETRY_AFTER, SDK.
                        observed_at=_utc_now();observed_mono=time.monotonic_ns()
                        self.retry_after=normalize_retry_after(retry_text,observed_at=observed_at,monotonic_ns=observed_mono)
                        if not self._accept_status(code.value):raise RuntimeRefused('HTTP_STATUS_UNACCEPTABLE')
                        encoding=self._query_text(29)
                        if encoding is not None and encoding.strip().lower()!='identity':raise RuntimeRefused('HTTP_ENCODING_UNACCEPTABLE')
                        declared=self._query_text(5)
                        if declared is not None:
                            if re.fullmatch(r'[0-9]{1,10}',declared) is None:raise RuntimeRefused('HTTP_HEADERS_INVALID')
                            self._declared_length=int(declared)
                            if self._declared_length>65536:raise RuntimeRefused('HTTP_BODY_LIMIT')
                        self._read_next()
                    elif status==READ and self._phase=='READ':
                        if not 0<=length<=self._reading:raise RuntimeRefused('HTTP_CALLBACK_INVALID')
                        if length:
                            self._body.extend(memoryview(self._read).cast('B')[:length])
                            if len(self._body)>65536:raise RuntimeRefused('HTTP_BODY_LIMIT')
                            self._read_next()
                        else:
                            if self._declared_length is not None and self._declared_length!=len(self._body):raise RuntimeRefused('HTTP_BODY_TRUNCATED')
                            body=bytes(self._body);self.close()
                            self._check_deadline()
                            self._result=_HTTPResult(self.status_code,body,self.retry_after)
                            return self._result
                    else:raise RuntimeRefused('HTTP_CALLBACK_INVALID')
                    return None
                except BaseException:
                    self.close()
                    raise

    def close(self):
        # Request cancellation is independent of current lease validity.
        with _MUTEX,self._api_lock:
            from .service_budget import cancel_native
            cancellation_error=None
            try:cancel_native(self._admission)
            except RuntimeRefused as error:cancellation_error=error
            self._closed=True
            if self.native_closed:
                if cancellation_error is not None:raise cancellation_error
                return
            if self._request is not None:
                request=self._request;self._request=None
                if not self._api.CloseHandle(request):self._cleanup_failed=True
            if self._registered and not self._closing.wait(.75):
                # Keep all callback/read/header references alive. Retire capacity
                # and report uncertainty instead of freeing an in-flight buffer.
                raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')
            for attribute in ('_connection','_session'):
                handle=getattr(self,attribute)
                if handle is not None:
                    setattr(self,attribute,None)
                    if not self._api.CloseHandle(handle):self._cleanup_failed=True
            if self._cleanup_failed:raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')
            c.memset(self._headers,0,c.sizeof(self._headers));c.memset(self._read,0,c.sizeof(self._read))
            c.memset(self._upload,0,c.sizeof(self._upload))
            if self._body:c.memset((c.c_ubyte*len(self._body)).from_buffer(self._body),0,len(self._body))
            self.native_closed=True;_PENDING.pop(id(self),None)
            if self._state is not None and not self._state.closed and self in self._state.resources:self._state.resources.remove(self)
            if cancellation_error is not None:raise cancellation_error




class _OwnedGet(_OwnedHTTP):
    def __init__(self,lease,*,host,port,secure,path,headers,timeout,_permit=None,_read_request=None):
        self._source_request=_read_request
        if _read_request is not None:
            _read_request.__post_init__();self._request_bytes=_read_request.content
        super().__init__(lease,host=host,port=port,secure=secure,path=path,headers=headers,timeout=timeout,method='GET',body=b'',_permit=_permit)
