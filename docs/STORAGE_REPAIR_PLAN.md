# Storage scanner repair

14 October 2026. Owner requested the storage repair, the remaining106 installed checks and continued local implementation, with every existing limit retained.

The serial native scan exceeded five seconds while opening thousands of directories. The diagnostic profile attributed about3.83 seconds to27,600 opens, with instrumentation overhead. The repair uses at most four readers, one64KiB buffer each and a four-batch queue. The caller merges every entry, resolves reparses and runs volume checks. Readers retain non-delete-shared directory handles through validation. Error paths join every reader; cleanup time counts toward acceptance. No path exclusions, cached inventories or reduced allocation charges.

Checklist:

- [x] Preserve the original failure and freeze repair scope in `.cache/test-runs/m5-storage-repair-20261014-01/contract01.json`.
- [x] Reproduce serial reads in a diagnostic red test; preserve two subsequent Windows fixture expectation failures and their correction.
- [x] Pass ten diagnostic scanner checks, including callbacks, locks, deadline and error cleanup.
- [x] Complete three real full scans below the unchanged five-second limit:3.467,3.654,3.567 seconds;105,781 files each.
- [ ] Independently review the implementation and qualify affected native scanner/watchdog cases, including actual128MiB/one-CPU behavior.
- [ ] Complete106 original installed18 cases without changing that installed package or its original source archive.
- [ ] Build/install the separately identified scanner release offline, qualify affected source/package cases and record an explicit evidence bridge.
- [ ] Publish verified results, synchronize the existing clone, then continue the approved local admission implementation.

Use at most three repair/review rounds. Keep original18 review counters and all failed receipts. New scanner bytes cannot be attributed to earlier source/package checks. The preliminary probes are diagnostics; full acceptance requires native bounded jobs and review. Current category headroom after the initial scans is163,282,064 bytes scratch and5,695,520 bytes backups. Do not remove failed evidence, raise limits, start Strata or perform broker actions.

Exact next action: finish independent scanner review and freeze the affected native inventory and original-package continuation bridge before those workloads run.

## Current approved continuation

Original release18 intent and confirmation checks are verified:393 identical source/installed cases,39 closed jobs per environment and0 failures/errors/skips. All106 formerly pending installed cases passed against the unchanged original package. Final independent review3 is CLEAR_ORIGINAL_RELEASE18. Aggregate SHA62601bca9b1606171ad3bbfd926a550ce6bd642f7249fccde9915e4409d7922d binds1027 evidence pins. The repaired scanner separately passed32 source checks; installed scanner qualification and full-master one-CPU128MiB/five-second operating qualification remain open. The owner approved three additional native-reader review rounds,4–6, using existing GCC and unchanged limits.

The first three Python review rounds are used. Native rounds4–6 are separately owner-approved. Full-master timing remains unqualified; do not repeat unchanged probes. The393/393 result is the original intent release, not the changed scanner. Prepare the native ABI and frozen compiler/build inputs, then verify the new identity against actual limits. No compiler/runtime installation is authorized.
