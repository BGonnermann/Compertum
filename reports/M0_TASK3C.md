# M0 Task 3C: private worker bootstrap source

Status: **PORTABLE_SOURCE_VERIFIED; NATIVE_BOOTSTRAP_UNVERIFIED; DURABLE_DISPATCH_DISABLED; M0_INCOMPLETE; PAPER_DISABLED.**

This stage extends the merged ownership and operator pipe-inspection source. It supplies candidate private startup credentials and worker protocol inspection. It does not complete Task 3, establish native acceptance, start actual workers or activate Task 4 stores. The owner authorized reviewed merges into the private repository; the home project remains untouched and local source edits remain paused.

## Source behavior

The supervisor prepares a private, randomly named, preconnected overlapped pipe under its verified live owner lease. Only the client handle becomes temporarily inheritable. The trusted fixture launcher uses an explicit Windows handle list and closes the parent's client copy after launch. No capability or private route is supplied in command arguments, environment, persistent metadata or logs; the child receives only a numeric inherited handle and a public supervisor expectation.

The parent binds the credential from the launcher's retained native child process handle, a separately retained matching process handle, native creation time, token user/logon SIDs and parent-process snapshot. It does not use an inherited bootstrap connection's client PID to claim that the child opened that connection. The child checks the bootstrap server's native process identity and compares the packet's child identity with its own observed process. Delivery requires a bounded acknowledgement. The normal request then opens a fresh endpoint client connection, whose peer observation authenticates that requesting process.

Packets bind supervisor, target and child project/role/instance/generation, an explicit command set and a random 256-bit capability. The private bootstrap packet is limited to 8,192 bytes. Worker request wrappers include the capability within the existing 65,536-byte frame limit. Duplicate keys, extra fields, nonfinite/malformed data, claimed native identities and mismatched roles/generations/instances are rejected. Private packet/offer/credential representations omit the secret and pickle serialization is refused. Constructed leases or credential objects cannot establish native authority.

The source-stage command limits are deliberately narrow:

| Child role | Permitted grants at this inspection stage |
| --- | --- |
| Watchdog | `status`, `pause_research` |
| Coordinator, evaluation, execution, recovery | `status`, `checkpoint` |

Each grant must also be allowed by its target endpoint. Financial commands and operator grants such as resume/shutdown cannot be conferred. The responses remain `PROTOCOL_VALIDATED_ONLY` with `can_dispatch=false`; no handler or mutable store is accepted. `request()` still raises `DURABLE_DISPATCH_UNAVAILABLE`.

Closing either owning endpoint or supervisor revokes enrollment and attempts disposal of every bootstrap/process handle. Native worker identities remain classified after revocation, preventing fallback to operator rights. Classification is process-wide across endpoints. At most 64 worker identities and offers are admitted per process/endpoint, with refusal after the bound rather than unbounded tombstone growth.

## Cloud measurements

Baseline: **133 passed, 20 Windows skips**. The new packet/frame interfaces first failed 15 portable checks, then passed. Seven enrollment/fallback cases and six verifier cases also failed before their implementations. Before review, the candidate had **158 source passes, 29 Windows skips**, and **142 installed-wheel passes, zero skips**.

After the single review repair pass, the final source command was:

```bash
PYTHONPATH=src ../../.venv/bin/python -B -m pytest -q
```

Result: **163 passed, 30 skipped**, zero failures. All thirty skips are native Windows fixtures; none qualify native behavior. A rebuilt noneditable wheel, installed offline without dependencies into the second locked environment, passed **147 contract/configuration/runtime checks, zero skips**. The bootstrap import was verified from that environment's `site-packages`. Wheel SHA-256: `501872e09da1e9a1c98c968165d5f0da9534aa491d4c29458a20d3200f7fbf43`.

The initial build command selected unavailable target Python 3.14.7 and refused. Selecting the existing cloud Python 3.12.14 explicitly allowed the offline owned-package build; no interpreter was downloaded or target changed. Detailed source/wheel logs, JUnit and the wheel remain under `.cache/test-runs/task3c-20261009/`. Source and this summary are published; native receipts must be freshly generated.

Portable checks cover private packet/credential boundaries, native-observation comparison, role allowlists, malformed/bounded frames and worker authorization/revocation policy. Injected native observations prove Python policy only. Ten additional real Windows fixtures cover inherited-handle selection, successful child inspection, wrong role/generation/instance/secret, operator impersonation at both the enrolled and a second endpoint, supervisor/target release and rejected self-binding. They are not executed in this Linux environment.

The native verifier accepts `--suite bootstrap`; `--suite all` requires at least 30 native fixtures without skips/errors/failures. Even a native fixture pass leaves full Task 3, native Task 1 and M0 unverified/incomplete. The all-suite command measured exit 3 on Linux with `NATIVE_WINDOWS_UNAVAILABLE`, `fixture_run=false` and no native fixture/evidence writes.

## Review and limitations

One fresh read-only whole-stage review found no Critical issue, two Important issues and two Minor findings. The Important issues were worker-to-operator fallback at a second endpoint and a launch finalization interruption leaving the bootstrap offer live. Five added regressions failed before the repair and then passed: same/cross-project fallback, inheritance reset/client-close interruption and the fixed identity bound. The repair keeps bounded process-wide native worker tombstones and irrevocably closes the whole offer on every finalization failure. A native second-endpoint fixture was also added, unrun. Fresh-token assertions were changed to constant refusal messages so a failed native test cannot print the capability. The final full source and rebuilt-wheel checks passed after this single repair pass; no second whole-stage review was performed.

Enrollment is local to the process holding the supervisor and target endpoint owners. Registration between separate owner processes is not implemented; no production launcher or native Job isolation is supplied. Only trusted bounded fixture helpers are launched. Task 5's limits and cancellation requirements remain pending.

Native owner replacement with old bootstrap credentials still needs a real lifecycle fixture; releasing an owner while its process remains alive cannot prove replacement. Task 3B's native DACL create-instance probe, published-endpoint takeover, acknowledgement faults and pending read/write cancellation gaps remain. The verifier's output limit still bounds retained evidence after capture, not memory allocated during capture.

The review also identified missing native coverage for a wrong retained child-handle binding, missing/bad bootstrap acknowledgement and interruption during real inherited-channel I/O. These remain explicit qualification gaps, alongside the unrun fixtures.

No durable replay receipt is synthesized. Task 4's receiver transaction/dedup store remains the required integration, after applicable native ownership prerequisites pass. Specification v1.1, plan, lock and financial/resource thresholds are unchanged. The preparation brief remains absent. No provider requests, broker credentials/transport, market data, protected evaluation, OS/interpreter/Strata changes or spending occurred.

## Design rulings

1. Use a private inherited **overlapped named pipe**, rather than `CreatePipe`, because anonymous pipes do not support overlapped operations. The unpublished name is not a public role endpoint. Cost if wrong: repair native fixture compatibility before acceptance; the transport deadline is not waived.
2. Keep worker inspection separate from effects and distributed owner registration. Cost if wrong: later integration must extend native enrollment without treating these source checks as qualification.
3. Retain bounded native worker classification after revocation, including across endpoints. Cost if wrong: admission may need safe process replacement after the fixed identity bound; revoked workers never regain operator authority.

## Native verification

After verifying native Task 1, use a clean checkout of the published `main` head and its existing qualified environment:

```powershell
.\.venv\Scripts\python.exe -B tools\verify_native_ownership.py --suite all --run-fixtures
```

Return the measured JSON/pytest/JUnit evidence directory. Keep local source edits paused. A fixture pass is a capability observation, not M0 acceptance.

## Primary API references

- [Anonymous pipe operations and absence of overlapped support](https://learn.microsoft.com/en-us/windows/win32/ipc/anonymous-pipe-operations)
- [Explicit Python Windows handle-list inheritance](https://docs.python.org/3.14/library/subprocess.html#subprocess.STARTUPINFO)
- [SetHandleInformation](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-sethandleinformation)
- [PROCESSENTRY32W parent-process field](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w)
- [Native named-pipe server PID](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeserverprocessid)
