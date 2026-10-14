# Account and presence final integrity

14 October 2026. Necessary local prerequisite before exact native intents. Independent preparation review found the combined-context callback issue in account-only and presence paths. These are static findings awaiting reproduction; integrity15 does not claim to fix them.

- [ ] Finish integrity15 paired verification, final review and publication.
- [x] Prepare12 isolated probe drafts in `.cache/test-runs/m5-account-presence-integrity-20261014-16/test_account_presence_integrity.draft`; no tests or product changes yet.
- [ ] Freeze and reproduce late credential-scan changes to account-only artifacts, original rows and slot bytes.
- [ ] Reproduce late presence inspection revocation and acknowledgement artifact/slot changes; prove no acknowledgement is inserted on refusal.
- [ ] Finish all callback work before bounded non-decrypting publication/slot and original-row proofs, then pure clocks/identity checks.
- [ ] Verify affected source/package cases, complete environments, failed-evidence preservation and independent review; publish/synchronize.
- [ ] Continue exact native intent and confirmation records.

Concrete locations: `paper_account_context._snapshot` loads the slot after `_originals`; `paper_presence._current` runs slot/health callbacks after original and presence-row checks; `_acknowledge` rechecks rows after callbacks but does not recheck ciphertext. `load_paper_slot` calls DPAPI validation and `_reject_reflections`, so it is not a passive byte read.

Keep verified nonempty history readable. Preserve original account freshness, presence expiry, immutable history and permanent invalidation. Do not reuse public CURRENT diagnostics as native authority. No actual account/order action, attempt consumption, new permission, paid data, Strata or scheduled service.

Primary writer; one bounded independent reviewer; at most three review/repair rounds. Preserve failed evidence and exact inputs. Existing120-second/4-GiB/four-CPU/16-process jobs,16/12-GiB host gates,128-MiB namespaces, five-second runtime storage scan and50-GiB category budget remain. Exact next action after integrity15 publication: activate isolated final-credential-callback probes before changing these product modules.

Independent probe preparation review completed:12 draft cases (5 account,4 presence inspection,2 acknowledgement,1 final-live boundary). First/current artifact distinction and initial clean opening are explicit. A bounded SQL trace counts attempted acknowledgement INSERTs without retaining statements; tests also require zero rows and no issued identity. The live-boundary case runs the real delegate then injects revocation; it is not represented as an actual MutualHealth.status callback. All probes remain unrun.

Prepared final-verification helper (not run) selects the12 new probes plus151 combined/account/opening compatibility cases from integrity15 and59 presence cases:222 distinct cases per lane, unless reproduced review findings require additions. This targets the two changing modules; unrelated unchanged account-binding tests are not claimed as fresh coverage. The helper requires published integrity15 and a frozen repaired16 plan before creating fresh namespaces.

Latest aggregate storage census leaves122.67MiB scratch headroom, below a fresh128MiB namespace reservation. After integrity15 publication, archive/verify its14 passing installed15c fixture roots and remove only those temporary copies before the first16 job. Prepared helper requires the published151-case receipt. Backup headroom is189.54MiB at that census; archive admission rechecks it. Limits remain unchanged.
