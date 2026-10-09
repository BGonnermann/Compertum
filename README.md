# Compertum

A supervised quant research system with reproducible experiments, bounded AI proposals and independent audits.

**M0 foundations: in progress.** Latest source stage: **Task 3C**, merged into `main`. Updated **8 October 2026 (ET)**.

## Build tracker

```mermaid
flowchart TD
    environment["1. Environment — cloud verified"] --> contracts["2. Contracts — portable verified"]
    contracts --> auth["3. Ownership and IPC — IN PROGRESS"]
    auth --> owners["3A. Ownership — source verified"]
    auth --> pipes["3B. Named pipes — source verified"]
    auth --> bootstrap["3C. Worker bootstrap — source verified"]
    auth --> enrollment["Separate owner registration — pending"]
    owners --> windows["Windows qualification — UNVERIFIED"]
    pipes --> windows
    bootstrap --> windows
    enrollment --> windows
    environment -.-> windows
    windows -. "Native prerequisites" .-> state["4–6. State, resource limits and recovery — QUEUED"]
    state --> runtime["7–8. Supervisor and AI workflows — QUEUED"]
    runtime --> acceptance["9. M0 acceptance — QUEUED"]

    classDef verified fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef active fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef pending fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef queued fill:#f3f4f6,stroke:#6b7280,color:#374151
    class environment,contracts,owners,pipes,bootstrap verified
    class auth active
    class enrollment,windows pending
    class state,runtime,acceptance queued
```

Green means the stated **cloud, portable or source checks** passed. It does not mean Windows acceptance passed. Blue is current work; amber is pending verification or implementation; gray is queued. The diagram groups later tasks; the [implementation plan](docs/M0_IMPLEMENTATION_PLAN.md) defines their exact prerequisites.

| Task | Progress | Completed work / remaining gate |
| --- | --- | --- |
| 1. Environment | Cloud verified; Windows pending | Locked dependencies, package build and clean reproduction pass in the cloud. Native installation/imports remain unverified. |
| 2. Contracts and configuration | Portable verified | Immutable records, five strict schemas, fixed budgets and capability checks. |
| 3. Ownership and IPC | **In progress** | Ownership, named pipes and scoped worker bootstrap source verified. Native lifecycle checks, separate owner registration and later durable replay integration remain. |
| 4. State and durable events | Queued | Owner-checked stores, durable messages and consumption guards. |
| 5. Resource and storage controls | Queued | Native process limits, byte reservations and storage watchdog. |
| 6. Recovery sets | Queued | Consistent snapshots and rollback-safe restore. |
| 7. Supervisor and terminal flow | Queued | M0 commands and durable offline task lifecycle. |
| 8. AI proposal workflows | Queued | Manual bridge and bounded local-model qualification. |
| 9. M0 verification | Queued | Full clean rerun, independent review and acceptance evidence. |

## Latest verified checkpoint

| Check | Task 3C result |
| --- | --- |
| Cloud source suite | **163 passed**, zero failures |
| Installed-package checks | **147 passed**, zero skips |
| Native Windows fixtures | **30 skipped — UNVERIFIED** |
| Independent source review | Completed; two important findings fixed and regression checks passed |
| M0 acceptance | **Incomplete** |

Current focus: finish the remaining Task 3 source/lifecycle work and obtain native Windows environment, ownership, IPC and bootstrap evidence. No runtime effects or paper trading are enabled.

Evidence: [Environment](reports/M0_BOOTSTRAP.md) · [Contracts](reports/M0_TASK2.md) · [Ownership](reports/M0_TASK3A.md) · [Named pipes](reports/M0_TASK3B.md) · [Worker bootstrap](reports/M0_TASK3C.md).

This tracker is updated with each completed source stage, verification result or changed blocker. Detailed specifications and operating instructions live in [the build specification](docs/BUILD_SPEC.md) and [the verification handoff](docs/WINDOWS_HANDOFF.md).
