# Private paper input context

14 October 2026. **255 matching cases passed in each source/installed environment**, with zero failures/errors/skips and all24 jobs closed. Both complete environments and aggregate verification passed. Final independent review3/3 is CLEAR, including the permanent-refusal correction and preserved failed runs. Earlier44-case source verification is historical evidence for the preceding implementation version.

## Implemented behavior

`PaperReadOwner.input_context()` accepts only authenticated subject and original packet, FRESH-job and capture identities. It resolves the account publication from the coordinator ledger, verifies encrypted originals, and binds the current private account observation to the held market producer and published lineage. No caller-provided manifest, account ID, clock, approval flag or diagnostic can replace those originals.

Every diagnostic rechecks current identity, credentials, health and original ages. Confirmed opening observations retain their first immutable reference. Missing evidence remains explicit; corruption refuses. The final clocks are checked after decryption, secrecy scanning and durable reads. A refused, closed or replaced context cannot revive. Closing it leaves borrowed HISTORY/FRESH resources intact. Status remains BLOCKED, financial/transport authority remains false and actual flatness remains unknown.

Successful context creation and diagnostics add no records, account requests, reservations, quota consumption, order plans or broker dispatch. Failed market validation can invoke the existing market invalidation path, which persists its INTERRUPTED refusal state. Native supervision, exact grants, ownership/economic reconciliation, fee/feed/action/halt evidence and other unresolved admission requirements remain blocking.

## Corrections and retained evidence

- Missing method:13 expected failures established the initial acceptance gap.
- Review1: eight regressions reproduced late-read freshness, missing final alias/history/proposal checks and context revocation during verification. These were corrected; implementation review2/3 was CLEAR on its recorded44-case version.
- Self-audit: two regressions proved that restoring an invented clock could revive a refused context. Diagnostic refusal now permanently closes that private context. Final review3/3 must cover this additional correction.
- A malformed capture injected by a test caused a separate teardown error. The failed fixture remains unchanged. Fresh tests retain injected/original bytes and restore only that invented fault for ordinary handle cleanup, without resuming any runtime.

Every failed run exited and closed its children. Original source archives, plans, logs, XML and fixtures remain under `.cache/test-runs/m5-input-context-20261014-12`. Earlier passing fixtures are not counted as fresh final-release coverage.

The first aggregate helper incorrectly equated pytest call-phase passes with complete JUnit cases. The original teardown run reports11 passing test bodies plus1 teardown error; its XML has10 complete passes and1 errored case. Corrected verification checks both facts explicitly. The failed helper, its pinned inputs, failure receipt and original fixtures remain unchanged. No product code or final test requirement changed for this correction.

## Final verification inventory

| Cases | Count per lane |
| --- | ---: |
| Private input context | 46 |
| Account, preflight, read publication and quotas | 125 |
| Current market owner | 20 |
| Durable lineage publication/recovery | 46 |
| Original opening integration | 13 |
| Public routing | 5 |
| Total | 255 |

The final freeze binds537 source/configuration/test files and207 product modules. Plan SHA `935d8d3e4c53f3f11cda5501fa332225e5d4621330ca6cbcfce0f1e17fd099b6`; group-map SHA `00b208bddb4dcb9209fa7f4f35a478ed771018e8ab77322adcc04f015d6b59cd`. Final source results use `.cache/test-runs/m5-input-final-20261014-12`; installed results use `.cache/test-runs/m5-input-package-20261014-12`.

The offline wheel matches all207 source modules; Python and38 dependencies are unchanged. Source archive SHA `be6a13e526980652bcb782c7fe6d67cf41a47b1bf1700a225877963100dc6093`; wheel SHA `d6083417634779d6557a149385006a4baedeeb2d7877ba378169d85c48e9de42`. Complete environment manifests are `cc8274c04d1d85a8ae5b70b7373c6d3006c15494fa98883f171d6ae8769e4148` (source) and `d2425358ab5bb631f75d6418c617de0808e34c72573e4da0b11e46359374e181` (installed).

Aggregate `artifacts/m5/input_context_pair_verified.json` SHA `e7c0d1abe00717fd961966fc54f0fded1ffea4c372a239a6157f1d122d7facab` verifies exact case equality, all frozen inputs, source archives, installed modules, full environment proofs and preserved failures. Its263 evidence pins have SHA `d4cff379691570b6538364da87d456cae0e15cfb4535f0a5e96149b28b2bcbf1`. The successful verifier ran6.5245749seconds with exit0; its command receipt SHA is `42b2dd96968a4dc4ee1e7f0ffbdf63dab47faac4cbe494b4223eadc672006c0b`. Longest test job65.3231066seconds; peak Job memory258,949,120bytes. All children exited; no job deadline or memory/namespace violation occurred.

All jobs retain120second/4GiB/fourCPU/16process limits,16/12GiB host admission/stop and the unchanged five-second storage scan. Fresh namespaces use a stricter128MiB ceiling. Real Windows stores and DPAPI, local market replies, invented account replies/origins and simulated clocks qualify component engineering only. No new full-reserve lifecycle or actual account access is claimed. No Strata, scheduled work or spending occurred.

Full M5 and financial acceptance remain open. M3's terminal lost-audit history is unchanged. M6 remains0/10 actual supervised market sessions.

Next: publish this reviewed checkpoint, then implement [native operator presence](../docs/M5_NATIVE_PRESENCE_PROGRESS.md), followed by exact intent/confirmation and the remaining admission dependencies.
