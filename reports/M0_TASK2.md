# M0 Task 2: portable contracts and configuration

Status: **PORTABLE_TASK2_VERIFIED; M0_INCOMPLETE; PAPER_DISABLED.**

## Implemented

- Five versioned JSON schemas with unknown-field rejection at every object boundary: task, control receipt, artifact manifest, recovery manifest and AI proposal.
- Immutable detached records, explicit UTC timestamps, SHA-256/UUID formats, finite JSON values, bounded record copies and project-relative paths. Existing symlink/reparse components are denied during preflight.
- Fixed $0/50 GiB configuration, including the 1 GiB reserve inside the 5 GiB records category. Task budgets cannot exceed trusted role ceilings; AI adapters retain the one-thread/256 MiB ceiling.
- Separate active-time accounting and 24-hour manual waiting, with no process lease/CPU reservation during operator waiting.
- Static financial capability denial (exit 3), broker state NOT_CONFIGURED, and control receipts that cannot call submission a successful effect.
- Recovery fields include writer generations/barrier, DB snapshots, messages and receiver deduplication, task/run/checkpoint states, artifact closure, seals/consumption guard, halt state and reserve accounting. Complete records require declared referential consistency.
- Opaque owner-lease shape cannot be serialized, reassigned or have its retained fields deleted. It does not acquire or prove a native lease.

## Verification

Initial interfaces/defaults produced 32 failing checks, then 32 passed. Clock, strict-record and financial-control cases were added before their repairs. Independent review found three Important findings and one Minor finding; deletion of retained owner fields was regraded Important because it can break the lease lifecycle. Seventeen new failing regressions reproduced the findings; all passed after one repair pass.

Final source suite: **68 passed**, no skips. Final contract/config suite against the noneditable wheel installed in the second locked environment: **58 passed**, no skips. All five schemas and the default TOML are included in that wheel. No second review is claimed after the test-backed repairs.

BUILD_SPEC, M0 plan and uv.lock hashes remain unchanged from Task 1. Configuration, package checks, RED/GREEN logs and review disposition accompany the saved source checkpoint. Only the owned package was rebuilt/reinstalled; third-party versions and the home interpreter were not changed.

## Scope and decisions

1. `validate_record` additionally accepts an explicit keyword-only `project_root`. Records with artifact paths require it; ambient working directory is not path authority. Cost if wrong: later callers must supply this context rather than use the plan's context-free signature.
2. Continue portable Task 2 after Task 1 cloud reproducibility is verified, preserving Task 1 native/provenance gates. Cost if wrong: Windows checks may require a repair before the foundation is accepted; no native or milestone acceptance is granted here.
3. Read-only shape/preflight checks do not verify actual artifact bytes, live owners, barriers, consumption status or race-safe path operations. Cost if mistaken for authority: a forged metadata claim could be treated as a real effect. Later native consumers must verify evidence before acting.

Native ownership/authenticated IPC, Windows path behavior, storage/process enforcement, actual recovery/replay/consumption handling and AI qualification remain assigned to Tasks 3-9 and unverified. The reviewer did not rerun the fixture-writing suite; the primary ran the recorded final suites. Handoff/status updates are documentation, not implementation acceptance.

Next implementation dependency: Task 3 native ownership and role authentication, after native Task 1 and portable checks are reverified on the home PC. This Linux session cannot run its required Windows handle/peer tests; no shared stores or runtime workers were enabled.

Publication handoff, 8 October 2026: the owner selected BrennanCompertum/Compertum and its matching connection verified private access. This source is prepared for `codex/m0-bootstrap`; check its actual GitHub head and `docs/WINDOWS_HANDOFF.md` before local work. Earlier BGonnermann/404 reports are historical. Detailed test logs and wheel evidence accompany the saved ZIP, not the tracked GitHub checkout. The 68/58 counts above remain cloud observations, not new Windows measurements.

New spending: **$0**. Product AI/provider requests: **0**. No financial calculations, broker transport, market-data collection, M1, training or automatic code execution.
