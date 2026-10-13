# M4 recovery integration checkpoint

11 October 2026. C=.cache/test-runs/m4-recovery-integration-20261011-01. Prior component B=.cache/test-runs/m4-execution-contracts-20261011-01. Preserve historical receipts.

- [x] Preserved attempts and native storage repair: 255 identical source/package passes; prior artifact unchanged.
- [x] Recovery fixes and independent review closed. Missing active database, per-intent conflict, partial aborted generations and inconsistent published/prior-active history regressions preserved.
- [x] Recovery source/package verification: 313 identical passes, zero failures/errors/skips, 132 exact installed Python files. artifacts/m4/fake_execution_recovery.json and reports/M4_FAKE_EXECUTION_RECOVERY.md. Passing fixtures archived/hash-verified; all failed fixtures retained.
- [ ] Authenticated execution-owner/operator/watchdog controls per docs/M4_OWNER_INTEGRATION_PLAN.md.
- [ ] Full allocated 1 GiB reserve and native integration, after capacity is available. Full M4 remains incomplete.

Capacity work: exact SciPy cache duplicate was matched to both verified dependency payloads, archived/hash-verified and removed under existing passing-copy cleanup approval. Both installed payloads are unchanged. Archive backups/m4-verified-scipy-cache-20261011-01.zip SHA256 61957c75cfb728a0414e18d704f4ecec674226acc5b6f97daed2def5df5c9741. No active environment or original checkout changed. C/scipy-cache-archive01.json, scipy-cache-cleanup01.json and scipy-installed-preserved01.json.

Last successful whole-project check resources02: scratch 5,250,207,440 / 5,368,709,120 bytes; scan 4.673064 s; free 225,748,705,280 bytes; RAM 8,467,968,000 below 8,589,934,592 required. capacity-diagnostic01 subsequently failed STORAGE_SCAN_DEADLINE while combined fixtures existed. Those passing fixtures are now archived and removed; do not reinterpret that failed scan as capacity admission.

Scope correction: the 64 MiB small-component allowance is not a global namespace cap. BUILD_SPEC/M0 explicitly require full 1 GiB reserve measurement within 5 GiB scratch and 50 GiB total. A separate declared full-reserve namespace is allowed once real capacity is demonstrated. No allocation or category exemption has been made.

Exact next action: implement persisted fake session/operator authority using existing native owner channels, while the bounded read-only capacity review identifies safe verified duplicates. Do not restore caller-supplied health booleans as authority. Recovery remains dependent on surviving newer evidence.
