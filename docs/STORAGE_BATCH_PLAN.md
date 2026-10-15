# Bounded native traversal experiment

15 October 2026. The owner approved the broader native scanning experiment, unchanged limits, continuation of implementation after verification, and master/GitHub synchronization. Scanner rounds 1 through 9 remain used. This extension permits at most three evidence-led rounds, 10 through 12, under the bounded-finish default. It does not reopen M3, authorize broker actions or permit deletion of failed evidence.

The measured hypothesis is that moving sequential traversal and strict row parsing into C reduces Python/C calls enough to complete the full inventory within the existing five-second watchdog. Per-directory native open cost remains; improvement is unproven. Keep the existing GCC, interpreter, dependencies and Windows API checks.

The private prototype adds a C-owned depth-first walker with held ancestor handles and bounded output batches. Python retains the public inventory shape, categories and every link-target resolution. A reparse record ends a batch while its parent remains locked. The next native call occurs only after Python validates that target. The existing volume/deadline probe runs synchronously on the calling thread before native directory operations and around each returned batch. Callback errors latch into Python, stop traversal and trigger checked native cleanup. No exception crosses the C ABI. Every opened handle must be closed on all outcomes, and close failure prevents success.

Native rows retain strict bounds, signed sizes, UTF-16 validation, single-component names, maximum allocation charging and no subtree exclusions. No cached inventory, concurrency, runtime compilation, new services, installation, spending or priority/security/power changes. Keep Strata off.

## Checklist and acceptance

- [ ] Freeze the new interface/behavior probes and exact prototype inputs; observe the original API's missing feature.
- [ ] Build privately with existing pinned GCC and verify native boundary/cleanup behavior.
- [ ] Compare complete small inventories against the unchanged original scanner; verify caller-thread callbacks, reparse lock lifetime and refusal propagation.
- [ ] Complete a fresh full-master candidate scan in the actual one-CPU/128MiB Job within five seconds, including cold initialization and checked closure. An incomplete profile is diagnostic only.
- [ ] Only for a viable candidate, integrate the smallest source change and migrate affected tests to the new boundary without weakening their assertions.
- [ ] Freeze and pass matching source/installed cases, both complete environments and repeated actual-watchdog full-master scans. Review the final bytes before publication.
- [ ] Publish/synchronize the verified result, then resume reader19 and M5 local gates 2 through 5. If round12 remains unresolved, preserve results and report the measured blocker.

Use fresh `.cache/test-runs/m5-native-batch-20261015-10` with a hard128MiB namespace bound and separately enforced sized growth. The bounded private experiment uses actual Windows Jobs, one CPU,128MiB for scanning,4GiB for builds,16 processes and a15-second job deadline. Product test workers retain120seconds,4GiB and four CPUs. Host admission/stop remains16/12GiB; scratch5GiB, records5GiB, backups20GiB, data15GiB, models5GiB, total50GiB and free-volume50GiB remain fixed. Private diagnostics confer no runtime, storage grant, financial or transport authority.

Exact next action: freeze and run the missing-interface probe against the unchanged native library, then build and inspect the private round10 prototype. Carry failed receipts and identities forward. Full M5 acceptance and M6's0/10 actual supervised sessions remain separate from storage engineering.


## Closed result

Rounds10 through12 are used. The original-library missing-interface probe failed as expected; private builds11 and12 passed. Round11's query buffer began at offset36 and failed before inventory comparison. A read-only differential showed aligned success and offset+4 refusal at NTSTATUS0x80000002. Round12 explicitly aligned the buffer and added a compile-time offset assertion. Its two small inventories matched exactly, but its full-master candidate hit five seconds after83,623 files. All23,749 handles closed; peak Job memory60,919,808 bytes. No replacement qualified, no product was changed and no reader case ran.

The original checklist records the required acceptance gates; passing the timing gate, boundary/fault coverage, integration and source/package/environment qualification remain incomplete. Do not continue those jobs under the exhausted experiment. The next action is reviewed documentation publication, with the remaining preservation/operating decision recorded in [the current checkpoint](CURRENT_CHECKPOINT.md). The native prototype and exact inputs remain private and ignored.
