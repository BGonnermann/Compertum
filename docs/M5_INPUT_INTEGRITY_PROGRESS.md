# Combined input integrity repair

14 October 2026. Targeted error repair before exact native intent records. Static review identified the two account-only review1 defects in the existing combined input context as well. These are pending reproduction, not verified runtime failures yet.

- [ ] Finish account-only increment14 paired verification, final review and publication.
- [x] Prepare six negative probes and two valid-history controls in `.cache/test-runs/m5-input-integrity-20261014-15/test_paper_input_integrity.draft`.
- [ ] Activate and freeze the probes; reproduce distinct first-opening corruption after final scans and corrupt initial unconfirmed history.
- [ ] Make the smallest targeted correction; verify original history need not be empty and invalidated contexts cannot revive.
- [ ] Run affected identical source/package inventories, full environment qualification, aggregate evidence and independent review; publish/synchronize.
- [ ] Continue [exact native intents](M5_NATIVE_INTENT_RECORDS_PROGRESS.md).

Keep source14 unchanged until its verification closes. Reuse existing combined fixtures, native stores/DPAPI and explicitly simulated origins/clocks/reserves. Preserve every failed source archive, result and fixture. No actual account, order, quota or transport action is authorized by this repair. No Strata or scheduled task.

The artifact probes cover both a distinct first-opening artifact on a later confirmed packet and the current account artifact when no opening exists. Both use the existing result/preflight scan boundaries; the latter prevents an unconfirmed path from escaping the same repair.

At most three review/repair rounds for this bounded increment. Primary writes; one independent reviewer. Keep120-second/4-GiB/four-CPU/16-process jobs,16/12-GiB host gates,128-MiB namespaces, five-second runtime storage scan and50-GiB category budget. Do not raise limits or delete failed evidence to admit a run. Exact next action: close14, then freeze/run the eight drafted integrity probes before changing product code.
