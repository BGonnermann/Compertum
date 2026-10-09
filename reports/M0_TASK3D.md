# M0 Task 3D: separate owners and lifecycle source

Status: **PORTABLE_SOURCE_VERIFIED; REVIEWED; NATIVE_UNVERIFIED; DURABLE_DISPATCH_DISABLED; M0_INCOMPLETE.**

This stage extends Task 3C with private registration between separate native owner processes and the remaining named-pipe/bootstrap lifecycle fixtures. It does not complete Task 3 or activate Task 4 stores. Cloud development remains the sole source writer; the home project is unchanged.

## Source behavior

A live supervisor prepares an unpublished preconnected overlapped pipe. Only its client handle is selected for inheritance. The child acquires its own role lease and public endpoint, then sends its actual registration through the inherited channel. The supervisor checks the retained launch handle, separately retained matching process handle, native creation time, user/logon SIDs, parentage, project, role and command scope. A bounded two-way acknowledgement establishes a private `RemoteRoleEndpoint`. A public routing descriptor or constructed object grants no authority.

Worker bootstrap accepts either the existing co-located endpoint or this verified remote authority. The supervisor retains remote-target worker registrations, scoped capabilities and native process handles. The remote owner accepts worker envelopes only: unknown peers and all operator claims are denied. A remote owner forwards its native observation and the complete bounded request over its private channel. The supervisor rechecks the retained worker process, exact capability, target generation, command scope and current owner lease, returning only a correlated protocol-inspection receipt.

Each exchange binds a random session, strictly increasing sequence and request fingerprint. A successful supervisor exchange holds its live owner scope until it consumes confirmation that the public worker acknowledged the receipt. The child retains its public peer process handle through its inspection exchange. There is no cached lease-valid flag, asynchronous enrollment snapshot or background control reader. Native pipe operations remain explicitly sequenced, with only one operation admitted per process. Channel failure, timeout, interruption, mismatched sequence or failed approval permanently retires that remote session and its endpoint. Owner resources close the channels when their leases are released, even if their processes remain alive.

Timeout has an explicit receipt boundary: the parent can close the control channel and release its owner scope after an effect-free receipt has already reached the child or worker. A failed private ACK write prevents the child's inspection from returning successfully, but a successful write alone does not prove the parent consumed it. Neither observation authorizes effects. Later durable dispatch needs its own transactional completion protocol; this inspection receipt cannot substitute for that gate.

Private hello/approval frames are at most 8,192 bytes. Forwarded requests, including routing and native-observation overhead, must fit the 65,536-byte pipe frame. This means a worker envelope at the public size limit can be refused when its private wrapper exceeds that limit. Worker grants keep Task 3C's role allowlists; arbitrary operator or financial commands cannot be granted. No private capability is returned in an approval or written to public metadata/output. Every successful reply remains `PROTOCOL_VALIDATED_ONLY`, with `can_dispatch=false`; `request()` still refuses durable dispatch.

## Measurements and review

The initial owner-channel codec contract failed 18 checks, then passed all 18. The expanded verifier failed seven cloud-refusal checks before its implementation. Additional portable checks cover forged authority, wrapper budgets, fresh scoped approval, public-before-private acknowledgement ordering, permanent retirement, inheritance-finalization interruption and closed-session reuse. Native observations and lease scopes injected into portable tests prove Python policy only.

Before independent review, the source suite passed **196 checks**, with **52 native Windows fixtures skipped**, and the installed wheel passed **179 checks with zero skips**. Following the single repair pass, the source suite passes **201 checks**, with **53 native Windows fixtures skipped**. The rebuilt noneditable owned wheel passes **183 contract/configuration/runtime checks with zero skips** in the second locked environment. Windows skips remain **UNVERIFIED**. The cloud Python is 3.12.14; target Python 3.14.7, the dependency lock and third-party packages are unchanged. An initial install named the wheel version incorrectly and refused; the actual built 0.0.1 wheel was then installed and its `site-packages` import verified.

One fresh independent whole-stage review found no Critical issue, two Important issues and two Minor findings. The Important findings were failed owner registration leaving a known launched child eligible for co-located operator fallback, and populated fixture gates becoming visible before their JSON was complete. Four regressions failed before the repair, alongside 33 passes; all 37 passed afterward. Classification now follows native child/SID/parentage validation and precedes any hello read, so timeout, malformed input, wrong role and bad ACK cannot restore operator rights. Command gates publish a complete sibling temporary file through atomic replacement. An additional native failed-registration/operator-fallback fixture remains unrun. The Minor findings were the timeout wording, clarified above, and an incorrectly named ACK fixture, renamed to match its bad-ACK behavior. No review finding is deferred; no second whole-stage review was performed.

Final rebuilt-wheel SHA-256: `6352037492e3b410a1a0094d5adf104ae5ae0af5b8ea5cf65fdb871a4683547f`. Source/JUnit/build/wheel logs remain under `.cache/test-runs/task3d-20261009/`. The Linux native verifier returns exit 3, `fixture_run=false` and `NATIVE_WINDOWS_UNAVAILABLE`, without native fixture/evidence writes.

## Native fixture coverage

All of the following are **source fixtures only, unrun on Windows**:

| Suite | Fixture count | Added cases |
| --- | ---: | --- |
| Ownership | 10 | Replacement after proved exit with a published endpoint, changed generation and only one replacement owner |
| IPC | 18 | DACL denial of the create-instance right, wrong/missing public ACK, actual pending body-read/write cancellation, injected interruption after real pending submission, fresh connection reuse |
| Bootstrap | 14 | Wrong live sibling process handle, wrong/missing private ACK, interruption during an actual pending inherited read and enrollment revocation |
| Registration | 11 | Separate supervisor/owner/worker inspection; unknown operator and cross-owner impersonation denial; supervisor lease release while its process lives; target release; stale session/sequence; wrong owner role; bad public ACK; replacement invalidating old worker credentials; failed registration cannot restore operator fallback |

The pending-I/O fixtures observe real `ERROR_IO_PENDING`, invoke real cancellation/completion calls and check that no uncertain/in-flight operation remains before reuse. The write fixture caps attempts at 1 MiB and a half-second deadline; failing to observe pending I/O is a failed fixture, never a pass inferred from buffer size. Interruption is injected in Python after real native submission; it does not qualify console Ctrl+C delivery. Helpers have independent exit bounds, selected inherited handles and sanitized constant status output. They are not production workers or Task 5 Job isolation.

The native verifier now supports `--suite registration` and requires at least 53 all-suite checks with no skip, error or failure. Even a passing native fixture suite leaves native Task 1, full Task 3 and M0 unverified/incomplete until their separate gates pass.

## Design rulings and remaining gates

1. Remote endpoints are worker-only. Native same-user PID/time/SID observations cannot distinguish an unregistered worker from a new CLI. Positive operator admission belongs to the later supervisor/terminal integration. Cost: remote direct operator inspection is unavailable until that admission exists. Existing co-located inspection still has process-local worker classification; no universal same-user isolation is claimed.
2. Require fresh supervisor approval per request; a successful supervisor exchange holds its owner scope through public acknowledgement. A retained process handle alone cannot prove a lease remains live. Cost: every remote inspection depends on current supervisor availability; timeout may follow an already delivered effect-free receipt, while channel uncertainty permanently closes admission. The receipt cannot grant dispatch.
3. Keep retained worker capabilities at the supervisor and use an explicitly pumped private channel. This avoids asynchronous enrollment snapshots and respects the one-in-flight native adapter. Cost: this API is a bounded inspection mechanism, not a concurrent production service loop.
4. Do not infer native success from portable policy checks or source fixture coverage. Cost: Tasks 4–9 remain behind their applicable native prerequisites. Task 4 must later integrate durable replay/transactional deduplication; no replay receipt is fabricated here.

The native environment, inherited handles, real process identity, pipe DACLs, owner replacement and lifecycle behavior still need Windows execution. The verifier's output limit bounds retained evidence after capture, not capture-time memory. Production launcher/Job limits, positive operator admission and durable effects are unavailable. M0 remains incomplete. The preparation brief remains absent. Specification, implementation plan, lock, fixed budgets and financial thresholds are preserved. Spending and provider requests remain zero.

Native verification instructions are in [the Windows handoff](../docs/WINDOWS_HANDOFF.md). Relevant primary API references are [named-pipe security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights), [CancelIoEx](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex), [GetOverlappedResult](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-getoverlappedresult) and [explicit handle-list inheritance](https://docs.python.org/3.14/library/subprocess.html#subprocess.STARTUPINFO).
