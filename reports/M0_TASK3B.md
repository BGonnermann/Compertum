# M0 Task 3B: restricted pipe inspection source

Status: **PORTABLE_SOURCE_VERIFIED; NATIVE_IPC_UNVERIFIED; WORKER_BOOTSTRAP_UNIMPLEMENTED; DURABLE_DISPATCH_DISABLED; M0_INCOMPLETE; PAPER_DISABLED.**

This continues the sole cloud implementation owner's Task 3 branch. It does not complete Task 3 or authorize dependent mutable stores. Source development remains separate from native Windows acceptance. The home project, specification v1.1, implementation plan, dependency lock and budgets are preserved.

## Source added

- A Windows-only ctypes pipe adapter with explicit security attributes and overlapped structures. Generated local pipe names bind project, role, process instance and generation. Servers require first-instance creation and reject remote clients. The protected DACL admits only explicit operator/logon SID data rights; the client mask excludes create-instance and generic-write rights.
- Framed messages have a 65,536-byte maximum, checked before body allocation. Connect/read/write share a maximum five-second exchange deadline. Cancellation has a separate one-second completion observation. Buffers, event and OVERLAPPED storage are retained before submission; an uncertain or interrupted completion closes the process's pipe admission gate and retains the allocation. This adapter permits one pending native pipe operation per process. It does not establish Job-tree or Strata cancellation.
- Both ends query native pipe peer PID, retain a process handle, observe creation time and token user/logon SIDs, and reject mismatches. Operator authentication never enrolls a writer. All worker actors remain refused until private inherited bootstrap and scoped child enrollment are implemented.
- `inspect_request` and `RoleEndpoint.inspect_once` exchange only `PROTOCOL_VALIDATED_ONLY` decisions with request/subject/payload/generation correlation. An acknowledgement prevents unread output being discarded on disconnect. There is no state-changing callback. `request` still refuses with `DURABLE_DISPATCH_UNAVAILABLE`.
- Owner metadata publishes the deterministic pipe name under the exclusive live owner. Transport teardown runs before owner handles close. Lost ownership revokes authority even when cleanup fails.
- Eleven real Windows IPC inspection fixtures, alongside the nine previous ownership fixtures. The verification entry point accepts `--suite ownership`, `--suite ipc` or `--suite all`. A successful inspection fixture run cannot mark native Task 3 or M0 complete.

## Measurements in this cloud session

Baseline: **115 passed, 9 skipped**, with `PYTHONPATH=src` pointing at the worktree. An initial invocation without that source selection failed collection because the environment's older editable package lacked the runtime module; it was an invocation error, not a code or native result.

New portable policy cases first failed nine checks for absent framing/security/reply behavior. A transport-before-lock cleanup regression failed before its implementation. Cancellation-error handling first failed for an invalid native handle. The verifier's five new/updated refusal checks failed before the suite selector and explicit IPC fields were added.

Final source command:

```bash
PYTHONPATH=src ../../.venv/bin/python -B -m pytest -q
```

Result: **133 passed, 20 skipped**, zero failures. All twenty skips are Windows fixtures and receive no native acceptance credit.

The owned wheel was rebuilt offline using the existing locked backend and installed without dependencies in the second locked environment. Contract/configuration/runtime/pipe-policy tests against that installed wheel: **118 passed, zero skips**. The adapter imports from that environment's `site-packages`, not the source checkout. Wheel SHA-256: `d6e6ade6b81e1f344dcdf9e5c9346a2f09aa39c14695ea13135800ebe2e47f72`.

`tools/verify_native_ownership.py --suite all --run-fixtures` on Linux returns exit 3, `NATIVE_WINDOWS_UNAVAILABLE`, `fixture_run=false`, native ownership/IPC/Task 1/Task 3 unverified. No native fixture was run by that command. Detailed cloud source/wheel logs and JUnit receipts are retained under `.cache/test-runs/task3b-20261009/`; only source and this summary are published.

## Independent review and single repair pass

One fresh read-only review found no Critical issue, one Important interruption-lifetime issue and two Minor native-coverage gaps. The Important issue was reproduced by two failing policy tests, then repaired. Both submission interruption and cancellation interruption now retain outstanding buffers/event/OVERLAPPED storage and refuse new pipe operations. The full 133-pass cloud suite and 118-pass installed-wheel subset passed after the repair. Injected native return codes prove Python policy only, not actual Win32 completion.

Deferred native coverage gaps:

1. The occupied-first-instance test does not independently probe the DACL by requesting create-instance rights. The explicit mask excludes that bit in source; native denial remains unverified.
2. Published-endpoint takeover, missing/wrong acknowledgement and pending native read/write cancellation need additional real Windows fixtures. Closing an endpoint and refusing reuse is not evidence of a successful replacement owner.

## Remaining gates

Native Task 1 and every native ownership/IPC observation remain unverified. Private inherited child bootstrap, scoped worker enrollment/revocation and remaining native lifecycle cases are next source work. Durable completed-request replay depends on Task 4's receiver transaction/dedup store; no volatile cache substitutes for it. Tasks 4-9 are not activated. The verification runner retains its earlier capture-output limitation: its 1 MiB evidence limit is checked after capture and is not an in-memory output cap.

The preparation brief is still absent. No provider requests, broker credentials/transport, authenticated market data, protected evaluation or spending occurred. No interpreter, Strata, OS setting, GitHub main or bootstrap branch was changed.

## Rulings for this stage

1. Use a separate protocol-inspection API while `request` remains unavailable until durable receiver state exists. Cost if wrong: later callers must integrate the receipt API; no inspection response can confirm a state change.
2. Serialize native pipe operations within each process and retain allocations after uncertain completion, refusing further pipe use until that process is safely replaced. Cost if wrong: a failed native cancellation reduces availability; it never grants authority or frees storage still in use.

## Windows verification command

After the native Task 1 environment is verified, run from a clean checkout of the published branch:

```powershell
.\.venv\Scripts\python.exe -B tools\verify_native_ownership.py --suite all --run-fixtures
```

Keep local source edits paused and return the measured report. A fixture pass remains a partial capability observation, not M0 acceptance.

## Primary API references

- [Named-pipe security and individual access rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)
- [CreateNamedPipeW](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew)
- [Native client PID](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid)
- [Native server PID](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeserverprocessid)
- [CancelIoEx and outstanding operation lifetime](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex)
- [GetOverlappedResult](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-getoverlappedresult)
