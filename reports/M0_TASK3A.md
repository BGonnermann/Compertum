# M0 Task 3A: ownership source and portable authorization

Status: **PORTABLE_SOURCE_VERIFIED; NATIVE_OWNERSHIP_UNVERIFIED; NAMED_PIPE_UNIMPLEMENTED; DISPATCH_DISABLED; M0_INCOMPLETE; PAPER_DISABLED.**

The owner reassigned source implementation to this cloud session on 8 October 2026. The isolated branch is `codex/m0-task3-cloud`; the bootstrap branch and original home project are preserved. This is a partial source stage of Task 3, not Task 3 completion.

## Added source

- A Windows-only ctypes boundary with explicit fixed-width structures and signatures, non-inherited handles, final root path and volume/128-bit file identity, process creation times, process-token user/logon SIDs and complete native process enumeration.
- Exclusive share-zero role handles, retained root/state/lock directory handles, separate bounded metadata publication with flush/write-through rename, generation changes and conservative prior-exit checks. A constructed `OwnerLease` is not authority; consumers require the private live-handle registry. Lock identity is rechecked and authority loss permanently invalidates the lease. Revocation attempts disposal of every retained handle; one failed close does not stop the remaining cleanup. Disposal refuses to close a numeric handle observed to refer to a different file.
- Bounded canonical protocol envelopes; duplicate keys, nonfinite/oversized/deep messages, claimed PID fields, wrong peer/role/generation, financial commands and wrongly scoped capabilities are rejected. Operator receipt subjects survive replacement authenticated CLI processes; worker subjects bind instance/role/generation. These inputs are supplied observations and registrations, not OS authentication evidence.
- Nine actual Windows ownership fixtures and an explicit verification entry point. Fixtures use isolated project-local namespaces and credential-free child environments. They do not enable production workers or initialize shared stores.

## Measured cloud verification

Fresh baseline: 68 passed, zero skips. After the new interfaces existed, 22 failing portable checks exercised absent behavior; 14 refusal checks already passed. The initial protocol/policy suite then passed 36 checks. Additional RED→GREEN cases cover the CLI refusal gate, non-ASCII capability input and permanent lease invalidation after authority loss.

Current complete source suite: **115 passed, 9 skipped**. All nine skips are the Windows ownership fixtures; none receive native acceptance credit. The rebuilt noneditable wheel passed **105 contract/configuration/runtime checks, zero skips**, in the second locked environment. Wheel SHA-256: `61d8344adc547397538dce958df974ba564ba22fedc1c467bd73287af7189c85`. Third-party dependencies, specification, plan and lock are unchanged.

The verification entry point was run in this Linux session with `--run-fixtures`: exit 3, `NATIVE_WINDOWS_UNAVAILABLE`, `fixture_run=false`, all native gates unverified. No fixture receipt was created by that command. No provider requests, broker transport, market-data collection, financial commands, training or paid service was used. Spending remains $0.

## Independent review and repair

One fresh-context whole-stage review found no Critical issues, one Important handle-disposal issue and two Minor bounds/documentation issues. The single repair pass observed five failing portable regression cases before implementation, then passing cleanup and pre-serialization refusal checks. Native loss-of-handle coverage was added as an unrun Windows fixture. No second review was used.

The Important issue is repaired in source: authority is revoked before cleanup, cleanup attempts every remaining handle even after a failure, and uncertain or foreign file identities are not closed. Cleanup uncertainty remains recorded on the revoked guard; native behavior still requires Windows verification. The envelope allocation finding is repaired with collection-count and cumulative encoded-string checks before stack expansion/serialization. The fixture-log finding is resolved by accurately documenting its 1 MiB retained-evidence cap. `capture_output` still buffers output in memory before checking that cap; it is not a capture-memory bound.

## Pending gates and limits

Native Task 1 remains unverified. The Windows declarations and behavior are candidate source; real home tests may reveal compatibility or lifecycle repairs. Existing fixtures are a subset of full Task 3: genuine native permission-denial/PID-reuse/prior-boot cases and the complete ownership/IPC integration remain pending. Full role teardown/process-exit behavior belongs to its later supervisor integration; a library refusal is not proof of a running role exiting.

Named-pipe DACLs, bounded overlapped transport, mutual OS peer verification, private bootstrap delivery, response authentication and native capability invalidation are not implemented here. `start_role_pipe` refuses; `request` refuses effectful dispatch. Task 4 must provide durable receiver dedup/transition evidence; an in-memory cache does not qualify replay. Tasks 4-9 are not activated by this stage. The fixture runner is not Task 5 process/storage enforcement or whole-child-tree cancellation. A file identity check cannot by itself attest the lifetime of a handle reopened on the same file; native lifecycle/integration coverage remains pending.

## Rulings

1. Develop Task 3A source in Linux without native acceptance; keep transport/dispatch closed. Cost if wrong: Windows fixtures may require repairs before any runtime is accepted.
2. Continue source development while native Task 1 is unverified under the cloud handoff exception. Cost if wrong: interpreter/filesystem differences may require repairs; no dependency gate is waived.
3. Require an explicit private exclusive-handle context for `verify_prior_exit`, in addition to the plan's `ProcessIdentity` example. Cost if wrong: later callers must supply this context; PID data alone never gains takeover authority.
4. Restrict roots to local fixed volumes and refuse uncertain existing-lock/missing-metadata recovery. Cost if wrong: unsupported volumes or a failed initial metadata publication need separately verified recovery, not automatic takeover.

## Primary API references

- [CreateFile and exclusive/non-inherited handles](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [Volume and 128-bit file identity](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)
- [Process creation times](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)
- [Complete process snapshots](https://learn.microsoft.com/en-us/windows/win32/toolhelp/taking-a-snapshot-and-viewing-processes)
- [Named-pipe rights and create-instance caveat](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)
