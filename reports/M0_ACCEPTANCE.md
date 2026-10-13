# M0 acceptance

**M0_BLOCKED. STRATEGY_NOT_EVALUATED. PAPER_DISABLED. New spending: $0.**

Implementation remains at M0. BUILD_SPEC version 1.1 and the preparation/implementation-plan files are preserved. Engineering readiness is withheld; no strategy, financial calculation, authenticated market-data access, brokerage credential, account action or order was exercised. M1 was not started.

## What works

- Python 3.14.7, compatible locked wheels, an isolated environment and a non-editable clean-wheel reproduction with the same 39 distribution versions. No interpreter substitution or third-party source-build fallback.
- Native single-owner handles, canonical root identity, verified process creation/SID, generation fencing, private watchdog bootstrap, local authenticated named pipes and durable request deduplication.
- Owner-checked SQLite/WAL records, serialized reads/writes, once-only message projections, checkpoint history and complete synthetic recovery sets. Restored missing/corrupt databases are rejected. Known consumption survives; every restored unconsumed seal is conservatively compromised because M0 has no independent external rollback witness. Arms/plans are invalidated.
- Suspended child assignment before resume, CPU affinity, committed-memory limits, denied breakaway, timeout/tree termination, bounded capture, reservations, crossing-write/flush/reparse refusal and crash recount. The real 1 GiB non-sparse execution reserve was measured; scaled release/floor/refill checks passed.
- Separate watchdog/native disk writer checks and real terminal lifecycle checks. Offline fixtures survive matching checkpoints, reject mismatched hashes and expired leases, and preserve interrupted history. Financial commands return exit 3.
- Sanitized manual subscription packets/provenance/expiry/import checks. Hosted response/access/quota remain unknown; no API credits are assumed. Local model-only qualification and stricter wrapper evidence are described below.

## Required gates still blocked

1. **Complete project storage verification fails.** Normal-user inspection cannot traverse private directories created by the earlier sandbox account. The final scanner refuses incomplete coverage with `PermissionError`; no permissions were changed and no paths were silently excluded. A preserved earlier measurement was 6.774 seconds, exceeding five seconds; complete coverage and the five-second deadline remain unverified. Runtime admission stays conservative. Small-root growth tests do not establish the main-root gate.
2. **The complete AI suite needs a rerun under the final strict wrapper.** Seven real worker-v1 checks passed under the earlier wrapper. After correcting its limit to one CPU and 256 MiB, native hashing and three live checks—JSON, structured fictional call and supplied-result JSON continuation—passed. Usage is 39/40 requests and 7/8 AI tasks for UTC 2026-10-08; a seven-request rerun cannot fit today. This is an unverified required gate, not a skipped passing test. Automatic hosted/local dispatch remains disabled.
3. **Native cancellation is unverified.** Owned timeout/verified idle behavior passed; no global cancellation was sent. Any task requiring cancellation stays disabled.

The runtime supports the documented default configuration. Unsupported lower aggregate limits are refused explicitly. Git identity is unconfigured, so no author identity or commit was invented; staged source, patch and hash receipts provide the local checkpoint.

## Verified setup

Python 3.14.7; Git and uv present; Ryzen 7 7700X registry identity; native physical RAM about 62.9 GiB; RTX 5070 Ti/driver and free VRAM recorded in the fresh environment receipt; CUDA compiler 13.4.59. DDR5 type/speed remain supplied, not independently verified. Registry build is 26300/26H2, with a legacy `Windows 10 Home` product-name value; exact branding remains unresolved. C: is about 930.47 GiB total with over 50 GiB free. Physical topology behind the two logical volumes remains unresolved; new project files stay on C:.

Strata remains the existing `127.0.0.1:8080` service, model `qwen3.8-flash-next-iq2_xs`, engine 0.1.40.2, 65,536 context positions and one slot. Binary, configuration, server source, both weight shards and tokenizer/template files were hashed in place with before/after file identity checks. Model hashing ran in a native 600-second Job. No Strata environment, server configuration or model file was changed.

## Verification and evidence

**Final frozen-source suite: 67 passed, zero skips.** Clean non-editable reproduction passed with 39 identical distribution versions and the same deterministic artifact. Native reserve recheck measured exactly 1,073,741,824 allocated bytes. Eight acceptance gates passed; main-root process/storage is `VERIFIED_FAIL`, and full local qualification under the final strict wrapper is `UNVERIFIED`.

Deliberate fault injection is identified separately from actual native assignment, process exit, file allocation, socket deadline and live inference evidence. The repaired disk-growth notification passed the unchanged five-second check; the scanner now starts every four seconds and publishes restrictive results immediately. This does not establish complete main-root inventory coverage.

| Evidence | Location |
| --- | --- |
| Final native suite command/output | `artifacts/m0/full_suite.json`; immutable final history under `artifacts/m0/history/` |
| Clean installed-wheel versions, commands and fixture | `artifacts/m0/clean_reproduction.json` |
| Environment/hardware | `artifacts/m0/final_environment.json`, `artifacts/m0/hardware.json` |
| Full reserve and failed main-root timing | `artifacts/m0/journal_reserve_final.json`, `artifacts/m0/storage_timing.json` |
| Live worker-v1 / strict wrapper / historical failures | `artifacts/m0/ai/strata_worker_v1.json`, `artifacts/m0/ai/strict_wrapper.json`, `artifacts/m0/ai/runs/` |
| Classification of earlier weaker text-only checks | `artifacts/m0/ai/history_classification.json` |
| Scope, budgets and machine acceptance | `artifacts/m0/scope_review.json`, `artifacts/m0/budgets.json`, `artifacts/m0/acceptance.json` |
| Independent review and progress | `reports/M0_INDEPENDENT_REVIEW.md`, `artifacts/m0/progress.jsonl` |

The fixture comparison is byte-exact, with SHA-256 `01349740c940b25d6bb01e722a513b7e955319c8cb36e1db20708cd841152da4`. Time/resource limits remain hard limits; no tolerance was widened. AI temperature was zero and exact prompts/settings/responses/usage were retained; no general determinism or mathematical/trading usefulness is inferred from these checks.

Independent review used one read-only agent and three bounded repair cycles. It covered ownership, authentication, assignment, storage and recovery; later primary fixes and actual checks are identified in its report. Earlier native second-turn HTTP failures remain recorded. The intermittent SQLite `InterfaceError` was diagnosed from actual fixture state, repaired by serializing owner-connection reads as well as writes, and given a concurrency regression check.

## Inspect from the project root

```powershell
Get-Content reports/M0_ACCEPTANCE.md
Get-Content artifacts/m0/acceptance.json
.\.venv\Scripts\python.exe -B -m compertum doctor --read-only --json
.\.venv\Scripts\python.exe -B -m compertum status --json
.\.venv\Scripts\python.exe -B -m compertum ai status --json
git -c safe.directory=C:/Users/bgonn/Desktop/Compertum diff --cached --stat
```

To rerun only the offline foundation after inspecting receipts:

```powershell
.\.venv\Scripts\python.exe -B -m compertum foundation check --suite m0 --offline --json
```

This creates a new bounded engineering fixture and does not certify main-root storage. Model qualification must wait until its full request allowance fits; do not raise the daily ceiling. A later complete verification uses `python -B tools/verify_m0.py`, preserving failed/unverified gates.

## Remaining decisions

- Choose an authorized way to make the complete project inventory readable to one operating identity, preserving evidence; then establish the five-second native monitoring deadline. No ACL change, deletion or workspace relocation was inferred.
- After the UTC request budget resets, repeat the full worker-v1 suite under the final one-CPU/256 MiB wrapper. Native cancellation needs separate owned-request evidence before affected automation can operate.
- Supply a local Git author identity if commits are wanted. Exact Windows/DDR5/storage topology and hosted entitlement/quota remain unresolved observations.

M1, data entitlement/credentials, universe/benchmark adoption and paper integration remain later authorized work. They are not an automatic continuation of this report.
