# Supervised saved-run implementation plan

Use executing-plans with the primary as implementation owner and one bounded independent reviewer. Owner explicitly authorized autonomous execution and follow-up on 9 October 2026, superseding routine design approval pauses. No commit or publication.

Goal: operate existing saved synthetic runs through the foreground supervisor, with responsive status/pause/stop and actual bounded Windows computation. Creation continues through the existing SavedRuns API for this increment. Prediction artifact publication follows as a separate integration step.

Architecture: separate SavedRuns attempt registration, acceptance and interruption from synchronous computation. A ResearchController keeps one active Job and no worker-owned SQLite connection. Add a registered replay template to the existing native launcher. It inherits only the saved input read handle and the reserved output handle. The supervisor polls without waiting on active computation. Pause terminates the Job tree, verifies exit and retains partial bytes before acknowledging controls. Restart is paused and never dispatches automatically.

Bounds: unchanged Python3.14.7 and lock, four CPU threads,4GiB worker memory,120seconds per attempt, two attempts per replay and six fixed replay units. Thus even twelve maximum-duration attempts remain below30minutes. Existing64MiB default/128MiB maximum aggregate artifact budget remains binding, with16MiB admitted per worker output. Single heavy-job slot and daily7200second budget use existing launcher. Coordinator256MiB, five-second control deadline, small status receipts. No network, arbitrary code, services, Strata, credentials, real data, trading, training or protected evaluation.

- [x] Split SavedRuns.begin/accept/interrupt and compact summary from step. Tests prove accepted bytes/checkpoints match synchronous replay, terminal failures, owner guards and attempt bound. Keep old synchronous behavior compatible.
- [x] Add registered inherited-handle replay worker to jobs.py and new runtime/replay_worker.py. Validate frozen identity, snapshots and fixed unit; bound every sink write. Native tests prove actual Job limits, input rejection and exit before adoption.
- [x] Add ResearchController and supervisor/CLI hooks for baseline status/resume/pause/stop. Preserve global health/pause/stop/checkpoint/shutdown behavior and shared fixture slot. No automatic dispatch on resume command; one explicit step admits one unit.
- [x] Run source, native and installed-wheel checks in fresh checked cache namespaces. Inspect responsive controls and crash recovery, exact output equality and immutable evidence. Review/repair at most three rounds; retain all failed and successful logs. Update roadmap, handoff and receipts.

Files: simulation/runs.py owns durable run transitions; research.py owns Job lifecycle; runtime/jobs.py owns admission and process limits; runtime/replay_worker.py owns pure computation over inherited handles; runtime/supervisor.py and cli.py route operator requests; tests cover each boundary.

Scratch starts near4.82GiB of the5GiB category cap. Check headroom before test batches, avoid full1GiB reserve fixtures, and preserve historical results. Storage exhaustion is an external-state boundary; do not delete old evidence or raise caps.

Native execution found two existing runtime races after the core three review rounds. Separate bounded repair/review covered same-ID pipe reconnection under the original deadline, then a one-second retry for transient metadata replacement conflicts. Both retain refusal on persistent/security/cancellation failures. See reports/M1_SUPERVISED.md and separate red/green evidence. No threshold, ACL or ownership rule changed.
