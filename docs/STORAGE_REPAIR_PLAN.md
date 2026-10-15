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

This initial Python checklist is historical. The original106 continuation is now closed and verified; the current native results follow below.

## Current approved continuation

Original release18 intent and confirmation checks are verified:393 identical source/installed cases,39 closed jobs per environment and0 failures/errors/skips. All106 formerly pending installed cases passed against the unchanged original package. Final independent review3 is CLEAR_ORIGINAL_RELEASE18. Aggregate SHA62601bca9b1606171ad3bbfd926a550ce6bd642f7249fccde9915e4409d7922d binds1027 evidence pins. The repaired scanner separately passed32 source checks; installed scanner qualification and full-master one-CPU128MiB/five-second operating qualification remain open. The owner approved three additional native-reader review rounds,4–6, using existing GCC and unchanged limits.

The first three Python review rounds are used. Native rounds4–6 are separately owner-approved. Full-master timing remains unqualified; do not repeat unchanged probes. The393/393 result is the original intent release, not the changed scanner. Prepare the native ABI and frozen compiler/build inputs, then verify the new identity against actual limits. No compiler/runtime installation is authorized.

Current native verification supersedes the preceding timing status:43 identical source/installed cases and18 C boundary cases passed; both complete environments passed. Final full-master scans passed at4.566,4.948,4.930seconds in actual one-CPU128MiB Jobs, including the original volume callback. Every category/time/memory/CPU limit is unchanged. Aggregate SHAeb08494998a4dcd395c08e6a0423f790d76a3a7b0ab4c3ea7b8de36e61e4c58e binds326 evidence pins and576 frozen inputs. Independent review4 was BLOCKED by a reproduced DLL-link gap; review5 cleared the repair. Final review6 is CLEAR. No cleanup occurred. See [the complete native report](../reports/M5_NATIVE_STORAGE.md).

Native review6 and publication are complete at24b0a5c; master, primary GitHub and requested clone matched. Maintenance07 subsequently archived and verified five passed scanner roots before checked removal; a capped installed full-master scan then passed in4.586seconds.

Current admission is blocked again. Reader19 red01, maintenance08's initial production budget scan and a separately labelled own-process one-CPU read-only diagnostic each exceeded five seconds. No reader test process or maintenance08 backup was created, and no maintenance08 deletion occurred. All217 source/installed payload files still match native06. The proposed four-root maintenance08 plan is independently cleared but cannot run through failed admission. Preserve every refusal and do not repeat unchanged launches.

Exact next action requires the pending owner extension beyond used native rounds1–6: at most rounds7–9, beginning with a separately identified read-only cost profile and a targeted evidence-led correction, followed by fresh matching source/package and actual watchdog qualification. Every resource/financial limit stays fixed. Reader19's34 private syntax-checked drafts await reliable admission. Do not reopen M3's terminal audit or start Strata.
