"""Exact bounded reads; callers retain ownership and close inherited handles."""
import ctypes as c
from ._windows import DWORD
from compertum.data.errors import DataError
MIB=1024**2

def read_input(api,handle,size):
    if type(size) is not int or not 0<size<=20*MIB:raise DataError('INPUT_BOUND')
    raw=bytearray()
    while len(raw)<size:
        count=min(MIB,size-len(raw));buffer=c.create_string_buffer(count);read=DWORD()
        api.checked(api.ReadFile(handle.get(),buffer,count,c.byref(read),None),'CampaignRead')
        if not read.value:raise DataError('RUN_ARTIFACT_CORRUPT')
        raw.extend(buffer.raw[:read.value])
    extra=c.create_string_buffer(1);read=DWORD()
    api.checked(api.ReadFile(handle.get(),extra,1,c.byref(read),None),'CampaignReadEnd')
    if read.value:raise DataError('RUN_ARTIFACT_CORRUPT')
    return bytes(raw)


