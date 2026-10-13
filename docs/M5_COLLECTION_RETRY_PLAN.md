# Collection retry implementation plan

12 October 2026 UTC. Existing autonomous roadmap authorization; primary implements serially, one independent reviewer, maximum three review/repair passes. Start only after shared service-budget frozen verification closes. No source changes during that verification.

**Goal:** Explicit, bounded retries for operational HISTORY and CURRENT_ACTIONS reads with retained evidence for every attempt.

**Architecture:** Extend the existing collection state machine. A small retry-decision function computes cooperative waiting; the existing shared service queue still controls every dispatch. Version2 private collection evidence retains the attempt chain and identifies the successful page projection. Version1 historical evidence remains readable unchanged.

**Tech stack:** Existing Python3.14.7, native WinHTTP, owner-held state, canonical JSON and existing DPAPI evidence. No new package, scheduler, service or environment change.

**Spec:** BUILD_SPEC.md sections8 and14; M5_SERVICE_BUDGET_PLAN.md; existing market-collection/qualification/evidence/composition contracts. Bounded design inspection by paper_contract_review completed before implementation.

## Scope and routine decisions

- Provider HTTP failures initially eligible:408,429,500,502,503,504. Other responses, reflection/parser/identity failures, malformed retry metadata, and unclassified transport failures stop. No automatic retry for HTTP_NATIVE_FAILED until a separate trustworthy error-stage contract exists. This is explicit partial transport-failure coverage, not a claim of full section8 acceptance.
- Three attempts per logical page, additionally constrained by the existing eight-total-attempt cap,80-second collection deadline,09:25 history cutoff and ten-second native request timeout. All clocks/deadlines remain anchored to the original task. No restored ticket or automatic restart.
- First retry waits at least1second after failure completion; second at least4seconds. Also honor the native Retry-After monotonic target. Refuse if the next attempt cannot start before the original task/cutoff limit. Never sleep in dispatch/poll/heartbeat.
- A logical page binds collection/plan/credential/operation/cursor; each attempt has a new request UUID, ordinal, timestamps and dispatch commitment. The cursor advances only after one selected successful response passes the existing semantic checks. Failed responses remain retained.
- Keep raw body once per attempt. Require confirmed native closure before scheduling another attempt. Retain normalized header observation and fixed terminal reason; no invented response/status/body for missing data. Preserve native original-response provenance and secret scanning.
- Before each dispatch, reserve room within current retention caps for the maximum bounded response and associated request/metadata. Failure to retain a complete next attempt terminates with a fixed capacity reason. Existing plain/cipher limits remain unchanged.
- Fresh-pair/account/order retries are separate contracts: fresh currently allows two total requests, account grants13GETs; no implicit expansion. Section14 prohibits automatic POST retries and defines a separate uncertain-write reconciliation schedule.

## Checklist in dependency order

- [ ] Red tests and pure retry decision: exact1/4second boundaries, status whitelist, three-attempt cap, normalized Retry-After, clock reversal/overflow, expired original deadline. Decision grants no dispatch authority.
- [ ] Collection attempt records and cooperative waiting: fail/fail/success, unique attempt identities/stable page identity, unchanged cursor, cancellation and queue delays, cleanup before retry, total-eight cap and capacity refusal. Preserve failed bodies after secrecy qualification.
- [ ] Version2 encrypted evidence validator and selected page projection; preserve v1 reader bytes and checks. Update composition to use only the validated successful projection while binding full original attempt evidence.
- [ ] Native local responses and encrypted reopen reproduce selected aggregate; malformed metadata/body, uncertain cleanup and substitution remain terminal. No real data/account credentials.
- [ ] Independent review, frozen source/package regression identities and exact replays; retain errors and resource receipts; update roadmap/checkpoint before continuing.

## Files and validation

Create runtime/read_retry.py and focused tests. Extend runtime/paper_market_collection.py and its snapshot/attempt contract; expose only needed trustworthy native dispatch fact in _winhttp_get.py and normalized retry observation in paper_market_qualification.py. Evolve paper_market_evidence.py with an explicit v2 validation path, retaining v1; update paper_market_compose.py for selected records. Semantic validators paper_market_inputs.py and paper_action_inputs.py stay unchanged.

Use a fresh admitted namespace under .cache/test-runs, unchanged storage categories/limits and allowlisted four-thread150-second verification wrapper. Source and installed wheel must have identical unique test identities, zero required failures/skips, exact module hashes and matching native local replays. Preserve prior successful no-retry history/compose outputs and version1 encrypted reopen. Simulated reserve or loopback tests cannot establish actual account/financial/full-reserve acceptance.

## Stop conditions

Only a material missing decision/authority, external dependency, explicit three-pass repair limit or execution limit may stop this accepted work. Record exact state and next action in CURRENT_CHECKPOINT.md. Continue other independent authorized work when a real acceptance gate is blocked. $0, original checkout preserved, no publication/orders/account actions/protected outcomes/Strata changes.

## Isolated preparation checkpoint

2026-10-12T03:39:15.284721+00:00. M3 is using the frozen shared-service source/package. A separate6MiB staging copy was admitted at .cache/test-runs/m5-collection-retry-staging-20261012-01/project after preserving passing historical fixture copies in verified archives. Active source, tests and installed package remain unchanged. New pure retry helper has45passing staged tests after the expected missing-module red check. It is not integrated or a native retry acceptance claim. Continue collection/attempt/evidence contract work in staging; any broader tests need explicit fresh capacity accounting while retaining all M3headroom and one numerical worker. No real credentials or external/account calls. Integrate only after frozen M3verification ends.


## Staged integration verification

2026-10-12T04:19:16.119052+00:00. Separate staging has162 pure/injected checks passed, zero failures/errors/skips. Retry decision, complete attempt chain, native commitment observer, explicit v2 evidence reader and composition are implemented only in staging. Both bounded reviews CLOSED on pass3 after retained red-to-green repairs. Native Windows retry/encrypted reopen remains unverified. Active frozen Q unchanged. Exact source hashes and remaining checklist: .cache/test-runs/m5-collection-retry-staging-20261012-01/progress.json.


Native isolated fixture admission 2026-10-12T04:19:51.417703+00:00:16MiB separate namespace admitted with remaining M3/staging capacity reserved, RAM>=8GiB, storage scan<=5seconds and all452active frozen source hashes unchanged. Native local WinHTTP and DPAPI fixtures may now run against staged source; no numerical worker or active environment mutation. Admission: .cache/test-runs/m5-collection-retry-native-20261012-01/admission.json.


## Native staging checkpoint

2026-10-12T04:42:27.193556+00:00:520selected checks passed, zero failures/errors/skips;13new native retry/cleanup/capacity cases;1preexisting actual1GiB subprocess test deferred until frozen M3ends. Native cleanup review CLOSED2/3 after direct-close regression reproduced and repaired. Exact staged source archive 23f3f18dd4384318588dfca3b47021ab11f645d08cea65bf82fa8c59aa0c0670. Active Q remains unchanged. Staged receipt artifacts/m5/collection_retry_staged.json; exact archive/file inventory .cache/test-runs/m5-collection-retry-staging-20261012-01/staged-source10.json. No installed-package/current-product acceptance yet. Further native fixture suites will run serially with M3 to avoid disk-scan contention.
