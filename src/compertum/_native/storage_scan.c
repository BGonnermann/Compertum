/* Checked, bounded FILE_FULL_DIR_INFORMATION reader. No traversal or allocation.
 * ABI1, Windows x64. Every non-null result.handle is caller-owned, also on error.
 * The caller must retain the handle through path validation and check cs_close.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    union { LONG status; PVOID pointer; } value;
    ULONG_PTR information;
} cs_io;
typedef LONG (NTAPI *cs_query)(HANDLE,HANDLE,PVOID,PVOID,cs_io*,PVOID,ULONG,
                              int,BOOLEAN,PVOID,BOOLEAN);
typedef struct {
    HANDLE handle;
    uint32_t bytes;
    int32_t status;
    uint32_t error;
    uint32_t operation;
} cs_result;
_Static_assert(sizeof(void*)==8 && sizeof(WCHAR)==2 && sizeof(cs_result)==24,
               "Windows x64 ABI required");

__declspec(dllexport) uint32_t cs_abi(void) { return 1; }

static int cs_fail(cs_result *out, uint32_t operation, DWORD error) {
    out->operation=operation; out->error=error; return -1;
}

static int cs_read(HANDLE handle, void *buffer, uint32_t capacity,
                   cs_result *out, BOOLEAN restart) {
    HMODULE module=GetModuleHandleW(L"ntdll.dll");
    cs_query query=module ? (cs_query)(void*)GetProcAddress(module,"NtQueryDirectoryFile") : NULL;
    cs_io io={0};
    if (!query) return cs_fail(out,6,ERROR_PROC_NOT_FOUND);
    out->status=query(handle,NULL,NULL,NULL,&io,buffer,capacity,2,FALSE,NULL,restart);
    if ((uint32_t)out->status==UINT32_C(0x80000006)) return 1;
    if (out->status!=0 || io.information==0 || io.information>capacity)
        return cs_fail(out,7,ERROR_INVALID_DATA);
    out->bytes=(uint32_t)io.information;
    return 0;
}

__declspec(dllexport) int cs_open_read(const WCHAR *path, void *buffer,
                                      uint32_t capacity, cs_result *out) {
    DWORD flags=0; FILE_ATTRIBUTE_TAG_INFO info;
    if (!out) return -1;
    memset(out,0,sizeof(*out));
    if (!path || !buffer || capacity!=65536) return cs_fail(out,1,ERROR_INVALID_PARAMETER);
    HANDLE handle=CreateFileW(path,0x81,3,NULL,OPEN_EXISTING,
                             FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
    if (handle==INVALID_HANDLE_VALUE) return cs_fail(out,2,GetLastError());
    out->handle=handle;
    if (!GetHandleInformation(handle,&flags)) return cs_fail(out,3,GetLastError());
    if (flags&HANDLE_FLAG_INHERIT) return cs_fail(out,4,ERROR_INVALID_HANDLE);
    if (!GetFileInformationByHandleEx(handle,FileAttributeTagInfo,&info,sizeof(info))) return cs_fail(out,5,GetLastError());
    if (!(info.FileAttributes&FILE_ATTRIBUTE_DIRECTORY)) return cs_fail(out,8,ERROR_DIRECTORY);
    if (info.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT) return cs_fail(out,9,ERROR_ACCESS_DENIED);
    return cs_read(handle,buffer,capacity,out,TRUE);
}

__declspec(dllexport) int cs_next(HANDLE handle, void *buffer,
                                 uint32_t capacity, cs_result *out) {
    if (!out) return -1;
    memset(out,0,sizeof(*out)); out->handle=handle;
    if (!handle || handle==INVALID_HANDLE_VALUE || !buffer || capacity!=65536)
        return cs_fail(out,1,ERROR_INVALID_PARAMETER);
    return cs_read(handle,buffer,capacity,out,FALSE);
}

__declspec(dllexport) uint32_t cs_close(HANDLE handle) {
    if (CloseHandle(handle)) return 0;
    DWORD error=GetLastError();
    return error ? error : ERROR_INVALID_HANDLE;
}
