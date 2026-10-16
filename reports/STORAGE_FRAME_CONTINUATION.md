# Storage fix continuation

16 October update. The preview check was corrected to measure current resource
use without stopping the preview. Independent review cleared one capacity
census. It completed and refused the scratch hold because of a
1,063,722,952-byte shortfall. The saved stop remains unchanged. See
[the current report](PREVIEW_RESOURCE_CAPACITY.md). The report below preserves
the earlier refusal and stop proposal; stopping the preview is no longer the
next action.

## Earlier 15 October report

15 October 2026. The owner approved up to 1 GiB of disk scratch for an isolated
test environment and retained outputs. The 4 MiB records ceiling, existing storage
category limits, 50 GiB total budget and 50 GiB free-volume floor remain unchanged.
The scanner still has one CPU, 128 MiB and five seconds. Strata stays stopped.

## Current result

The independently reviewed launcher refused before starting a capacity census.
The existing Vesper website preview server had accumulated 6.125 CPU seconds,
above its saved five-second allowance. Its observed working set was 28,491,776
bytes, below the 67,108,864-byte limit. CPU time did not increase during a
half-second observation. The server remains running. No threshold changed.

Census start, launch, closure and result receipts are absent. No native census
Job, candidate build, scan, installation or product test ran. No current complete
inventory, capacity pass or timing benefit is claimed. The refusal is saved
separately because it occurred before normal launch-receipt creation.

## Reviewed preparation

The first gate charges 40 MiB of records holds plus the full 1 GiB scratch hold,
totaling 1,115,684,864 bytes. Actual reservations, named streams, backup checks,
the execution reserve and saved watchdog stop remain covered. Census/parent/outer
limits remain 70/75/85 seconds. The later ten Job slots are disabled.

Review identified missing final deadline checks and interpreter pins. Both were
corrected before the launch request. Final checks now cover hashing, durable
receipt writes and retained directory closure. Late failures retain separate
receipts and return failure. The Python launcher, base executable and environment
configuration are pinned to existing identities.

The reviewer independently verified 933 frozen inputs with zero mismatches.
The primary agent matched all nine release hashes. Two sets of eleven pure
capacity checks passed: **22 passed, zero failed, zero errors, zero skipped**.
They use in-memory values and are not product or native-walker tests. Product
results are **zero passed, zero failed, zero errors, zero skipped**.

Fresh preservation checks matched 217 source files, 217 installed files and the
coordinator database and watchdog-stop bytes. No production file changed. The
original 1 GiB execution reserve remains separate. Prior sources, failed evidence,
twelve scanner rounds and earlier reviews remain retained. An initial generation
script stopped on a source assertion; its partial contract and source are also
retained alongside the corrected generator. This was not a native attempt.

## Next action

The owner decision about temporarily stopping the verified local preview server
is pending. Its reviewed stop procedure records intent first, verifies the exact
process generation and observes exit. It requires explicit authority. It has not
run and grants no restart or file changes.

After approval to stop it and make one census launch, preserve this refusal and
refresh the reviewed documentation bindings before execution. A capacity refusal
ends the attempt. A capacity pass permits completion and review of the missing
32 native subcases and executable commands. It does not release those later
stages or clear the watchdog stop.

The larger allowance does not establish fit within the unchanged 5 GiB scratch
category. The last complete pre-removal count was near that limit; a fresh
complete count remains necessary before scratch writes. Reader19, ordinary
runtime, clone writes and Strata remain stopped. M5 requirements 2 through 5 stay
open and M6 remains zero of ten actual sessions.

Private records remain excluded from Git under
`artifacts/m5/storage-frame-reuse-20261015-13`, including `checked-contract.json`,
`checked-review.json`, `checked-preflight-refusal.json` and all prepared sources.
