/* Compile-time Win32 fault injection against the exact production C source.
 * This fixture never replaces the production DLL and opens no real handles.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static int scenario;
static int closed;
static HANDLE WINAPI test_open(LPCWSTR p,DWORD a,DWORD s,LPSECURITY_ATTRIBUTES sa,
                              DWORD d,DWORD f,HANDLE t) {
    if (!p || a!=0x81 || s!=3 || sa || d!=OPEN_EXISTING ||
        f!=(FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT) || t) abort();
    if (scenario==1) { SetLastError(5);return INVALID_HANDLE_VALUE; }
    return (HANDLE)(uintptr_t)123;
}
static BOOL WINAPI test_flags(HANDLE h,LPDWORD flags) {
    if (h!=(HANDLE)(uintptr_t)123) abort();
    if (scenario==2) { SetLastError(5);return FALSE; }
    *flags=scenario==3 ? HANDLE_FLAG_INHERIT : 0;return TRUE;
}
static BOOL WINAPI test_info(HANDLE h,FILE_INFO_BY_HANDLE_CLASS kind,LPVOID output,DWORD size) {
    if (h!=(HANDLE)(uintptr_t)123 || kind!=FileAttributeTagInfo || size!=sizeof(FILE_ATTRIBUTE_TAG_INFO)) abort();
    FILE_ATTRIBUTE_TAG_INFO *info=output;
    if (scenario==4) { SetLastError(5);return FALSE; }
    info->FileAttributes=scenario==5 ? 0 : FILE_ATTRIBUTE_DIRECTORY;
    if (scenario==6) info->FileAttributes|=FILE_ATTRIBUTE_REPARSE_POINT;
    return TRUE;
}
static BOOL WINAPI test_close(HANDLE h) {
    if (h!=(HANDLE)(uintptr_t)123) abort();
    ++closed;
    if (scenario==13) { SetLastError(5);return FALSE; }
    if (scenario==14) { SetLastError(0);return FALSE; }
    return TRUE;
}
static FARPROC WINAPI test_proc(HMODULE module,LPCSTR name);
#define CreateFileW test_open
#define GetHandleInformation test_flags
#define GetFileInformationByHandleEx test_info
#define CloseHandle test_close
#define GetProcAddress test_proc
#include "../../src/compertum/_native/storage_scan.c"

static LONG NTAPI test_query(HANDLE h,HANDLE event,PVOID apc,PVOID context,
                            cs_io *io,PVOID buffer,ULONG capacity,int kind,
                            BOOLEAN single,PVOID name,BOOLEAN restart) {
    if (h!=(HANDLE)(uintptr_t)123 || event || apc || context || !buffer ||
        capacity!=65536 || kind!=2 || single || name || (restart!=TRUE && restart!=FALSE)) abort();
    if (scenario==8) return (LONG)0xc0000001;
    if (scenario==9) { io->information=0;return 0; }
    if (scenario==10) { io->information=65537;return 0; }
    if (scenario==11) return (LONG)0x80000006;
    io->information=70;return 0;
}
static FARPROC WINAPI test_proc(HMODULE module,LPCSTR name) {
    if (!module || strcmp(name,"NtQueryDirectoryFile")) abort();
    if (scenario==7) return NULL;
    return (FARPROC)(void*)test_query;
}

int main(void) {
    char buffer[65536];cs_result result;int count=0;
    const unsigned operations[]={0,2,3,4,5,8,9,6,7,7,7,0,0,0,0};
    for (scenario=0;scenario<=14;++scenario) {
        closed=0;int code=cs_open_read(L"checked",buffer,sizeof(buffer),&result);
        int expected=scenario>=1 && scenario<=10 ? -1 : scenario==11 ? 1 : 0;
        if (code!=expected || result.operation!=operations[scenario]) return 1;
        if (scenario==1) { if (result.handle) return 2; }
        else {
            if (result.handle!=(HANDLE)(uintptr_t)123) return 3;
            unsigned close_error=cs_close(result.handle);
            if (close_error!=(scenario==13 ? 5u : scenario==14 ? ERROR_INVALID_HANDLE : 0u) || closed!=1) return 4;
        }
        ++count;
    }
    scenario=0;
    if (cs_open_read(L"checked",buffer,65535,&result)!=-1 || result.handle || result.operation!=1) return 5;
    ++count;
    if (cs_next(NULL,buffer,65536,&result)!=-1 || result.operation!=1) return 6;
    ++count;
    if (cs_abi()!=1 || sizeof(cs_result)!=24) return 7;
    ++count;
    printf("{\"native_contract_cases\":%d,\"failed\":0}\n",count);
    return 0;
}
