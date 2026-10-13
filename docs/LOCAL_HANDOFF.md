> Current owner direction (13 October 2026): work and edit only in `C:\Users\bgonn\Desktop\Compertum`; GitHub checkpoints are explicitly authorized. Older checkout, preservation and publication restrictions below are historical. Read [CURRENT_CHECKPOINT.md](CURRENT_CHECKPOINT.md) and the root AGENTS.md first.

# Local development handoff

Current status: offline M1 is complete; approved real-data access works, but data qualification is blocked on missing source evidence and sampled minute gaps. Use [CURRENT_CHECKPOINT.md](CURRENT_CHECKPOINT.md) for the current checklist, evidence and exact next action. Earlier dated next-task statements below are historical.

Date: 8 October 2026 ET.

The owner asked local Codex to take over development and confirmed: "Cloud stopped; no unpublished work to transfer." Local Codex is the sole implementation owner. This explicitly supersedes earlier cloud-only source ownership and verification-only restrictions. Other operating limits remain in force.

## Working source

- Repository: https://github.com/BrennanCompertum/Compertum
- Development checkout: `C:\Users\bgonn\Desktop\Compertum-development`
- Local branch: `local/m0-development`
- Published starting commit: `cb0759e4bd9d28c6608bc3c5f9fb8da49e622781` (merged native fixture repairs).
- Original project: `C:\Users\bgonn\Desktop\Compertum`; preserve its independent history, changes and runtime state.
- Prior verification checkout: `C:\Users\bgonn\Desktop\Compertum-native-20261008-01`; retain its pinned `68f9643cc591b7a3ab3307f3351fae324b4fd729` source, environments and evidence.

No runtime state, environments or old source were copied into development. No unpublished Task 4 source was received. Task 4 is queued from the published plan; earlier cloud claims about unpublished work do not establish completion here.

## Current evidence and next work

M0 accepted on9October2026: ENGINEERING_FOUNDATIONS_READY,10/10 gates. Latest report: reports/M0_ACCEPTANCE.md. Source/installed-wheel identity remains unchanged since the health repair; six live checks added fresh evidence. M1 is the next milestone but has not started. Older task-in-progress descriptions below are historical.

Local Tasks 4�8 source is now implemented and under final M0 verification. Tasks 1�3 were freshly reproduced on native Windows before dependent implementation. See `reports/M0_LOCAL_PROGRESS.md` and the newest acceptance receipt for measured results; earlier failed reports remain historical evidence.

The active run is `.cache/test-runs/m0-local-20261009-01/`; final acceptance orchestration creates a separate `m0-acceptance-UUID` namespace. Both source and installed-wheel environments use Python 3.14.7 and the unchanged lock. Retain all fixture state, backups, red/green logs and old wheels. A fixture intentionally marked evaluation-compromised must stay compromised; future tests use a fresh namespace rather than clearing it.

Native supervised work is foreground and bounded. `python -m compertum --project-root FIXTURE_ROOT start --mode research --config config.toml` starts/attaches. `status`, `research pause --reason TEXT`, `research resume`, `research stop --run UUID`, `checkpoint`, and `shutdown --checkpoint` use authenticated local control. `foundation check --suite m0 --offline --config config.toml` runs the deterministic fixture with a complete recovery checkpoint. A retained watchdog halt prevents subsequent admission; M0 provides no automatic clear.

Manual AI export uses `ai export --task UUID --provider subscription`. Imports use `ai import --task UUID --response artifacts/inbox/response.json` and an adjacent `response.json.metadata.json` containing exactly provider, model_label, received_at (UTC), and provenance (`OPERATOR_SUPPLIED` or `SYNTHETIC_FIXTURE`). Exported packets carry the response schema and exact task/input/prompt identities. Proposed text is retained, never executed. No hosted response or usage is inferred from a synthetic import.

The real Strata adapter requires an exact full-request tokenizer callback and recorded model identity. Qualification is explicit, bounded, model-only and proposal-only. The owner explicitly approved the six bounded live checks and separately approved starting the unchanged existing launcher. Fresh qualification passed6/6 with exact input counts matching server usage. Strata remains running and idle. Native owned-request timeout remains unverified and automatic dispatch remains disabled. Deterministic server tests and native client limits do not establish live Strata qualification. No fallback capability is enabled by the six-check function alone.

Follow BUILD_SPEC v1.1 and M0_IMPLEMENTATION_PLAN. Record fresh progress and receipts under the unchanged category budgets. Tests use fresh checked `.cache/test-runs` namespaces. One bounded independent reviewer has inspected M0 and its material repairs.

## Retained boundaries

New spending stays zero. No commits, pushes, merges or publishing without explicit authorization. No administrator or security changes, unattended services, production workers, Strata requests outside the approved six-check qualification or Strata startup/reconfiguration, broker access, market-data collection, protected evaluation, training or later milestones. Preserve original source/runtime and historical results. Python remains exactly 3.14.7; do not change the lock or build third-party dependencies from source as a compatibility workaround.

## 9 October continuation decision

After reviewing the offline M1 proposal, the owner said: "I don't know why project rules say that but you are approved to do whatever you need." This removes the stale M0-only implementation restriction and delegates routine design, planning and execution for the proposed offline data component. The primary agent continues directly, with one bounded independent review at completion. No repeated design/plan approval is requested for this accepted component. Existing separate boundaries for external account access, spending, trading, publishing, protected data and Strata remain.

M0 acceptance remains tied to its preserved source archive and receipt. New M1 changes receive separate receipts and cannot retroactively change the accepted M0 source identity.

## M1 offline data component complete

See reports/M1_OFFLINE_DATA.md, docs/M1_OFFLINE_PLAN.md and artifacts/m1/offline_data.json. New data modules validate synthetic JSON and publish via existing StorageManager; no network clients or production CLI added. Source/regressions131passed, installed wheel38passed; exact snapshot/feature hashes agree. M0 acceptance remains historical and byte-preserved. The reproduction environment now has the M1 wheel; prior M0 wheels/logs remain preserved. Native Strata cancellation and automatic dispatch are unchanged. The next local development increment is baseline simulation; real-data access still requires a concrete separate decision.

## Autonomous continuation, 9 October 2026

The owner authorized continued offline work while away. Saved synthetic runs and prediction reporting are now verified. See reports/M1_SAVED_RUNS.md and reports/M1_PREDICTIONS.md plus their artifacts/m1 receipts. Current next work is supervised operator integration, including publishing prediction reports alongside saved results. Do not repeat the stale M0-only approval question. Real data and financial acceptance remain unverified; no credentials, broker access, spending, publishing, Strata changes or unattended service were introduced. Prior stage archives and original project remain preserved.
## Saved-run policy correction, 9 October 2026

Final spec reconciliation corrected the cap to two attempts per replay and made deterministic errors terminal. Fresh checks: 14 source and 14 wheel passes; 4 native crash/stop passes per environment, no failures/skips. See reports/M1_RUN_POLICY.md and artifacts/m1/run_policy.json. Prior saved-run/prediction receipts and archives remain unchanged. Next remains supervised operator integration; full M1 is incomplete.

## Supervised replay controls, 9 October 2026

Foreground baseline status/resume/step/pause/stop now operate existing saved runs through bounded workers. Reports/M1_SUPERVISED.md and artifacts/m1/supervised.json bind the evidence: 172 source and172 wheel regressions before native repairs, then23 current source and11 wheel native passes. Worker outputs match. Native reconnect and transient metadata-sharing repairs received separate reviews; no limits or permissions changed. Current authorized next work is docs/M1_PREDICTION_PUBLICATION_PLAN.md. Continue execution/follow-up loops without a routine component handoff.

## Saved prediction publication completion, 9 October 2026

The owner approved the timing repair, then conditionally approved deleting two old test reserve files after their tests had completed and passed. Those conditions and both backups were verified before deleting exactly the two files named in backups/verification-reserves-20261009/approved-cleanup.json. Reports and backups remain; this approval does not authorize other cleanup.

All nine pending recovery checks now pass on unchanged final source. The complete current collection reconciles to 491 unique passes and 11 Windows-inapplicable skips across recorded phases. Final native checks passed 17/17 in source and installed-wheel environments, and all nine outputs match byte-for-byte. The accepted saved prediction publication component is complete; see reports/M1_PREDICTION_PUBLICATION.md and artifacts/m1/prediction_publication.json.

A generated inventory report briefly exceeded the scratch cap; its exact bytes were preserved in a verified archive and the receipt condensed. Final scratch is below the unchanged 5 GiB cap, with about 8 MiB left. The new recovery fixtures remain. Do not start another large test batch without a fresh capacity check. Original project, Git indexes, prior acceptance reports, lock and specification remain unchanged. No commit or publishing is authorized; full M1 and financial acceptance remain incomplete.

## Real-data access checkpoint - 9 October 2026

The owner approved the bounded read-only increment. The existing connector returned the development sample; 33 calls and all supported checks are retained. Fifteen admission regressions passed; an independent reviewer found no material mismatch. The connector omits raw/split adjustment and pagination evidence, four entry minutes are absent, and action completeness remains unverified. No runtime source changed or real data were admitted. An existing direct read-only connection or original export location is the pending missing input. Do not repeat the already-granted scope approval. See CURRENT_CHECKPOINT.md, M1_REAL_DATA_PLAN.md and reports/M1_REAL_DATA_ACCESS.md.

## Direct Alpaca access - 9 October 2026

Owner authorized using existing Alpaca entries in Desktop/v20/.env. Direct market-data-only access passed with 28 HTTP 200 pages, original bytes and terminal pagination. The credential file is unchanged and values were not copied. Nineteen safety tests and native success/process/HTTP deadlines passed. Four IEX minute gaps persist; provider-rounded split prices fail direct normalization assumptions and action coverage/knowledge remain unverified. Current decision is whether to test historical SIP at $0 under a distinct explicit feed profile. Do not ask again for credential-location authorization. See CURRENT_CHECKPOINT.md and reports/M1_DIRECT_DATA_ACCESS.md. Full M1 remains incomplete.

## SIP continuation closeout, 9 October 2026 ET

The owner explicitly approved historical SIP and existing V20 credentials; both choices are resolved. The bounded increment is verified in reports/M1_SIP_DATA_EVIDENCE.md and artifacts/m1/sip_data_evidence.json: 26 pages, 55 daily/104 minute rows per adjustment, 135 source and 80 wheel passes, exact actual-sample reproduction. New provider evidence parser and exact normalization do not change the synthetic strategy gate. All older receipts remain immutable. Full historical action/metadata coverage, warmup, real snapshot integration and adopted/sealed protocol remain before full M1. Follow docs/CURRENT_CHECKPOINT.md; do not restart stale credential/feed approval questions or claim action coverage from pagination. No new deletion or publication.

10October2026 ET: action evidence increment verified in reports/M1_ACTION_QUALIFICATION.md and artifacts/m1/action_qualification.json. 177 source /122 wheel passes; 329 actions and32 SPY observations reproduce. Full real-data qualification fails on explicit gaps; see docs/CURRENT_CHECKPOINT.md before further work. Existing credential/feed approvals persist. No commit, publication, financial admission or new deletion.

## Issuer reconciliation closeout, 10 October 2026 ET

The bounded issuer evidence pass is verified in reports/M1_ISSUER_RECONCILIATION.md and artifacts/m1/issuer_reconciliation.json. 236 observations,201 filled dividend dates,32 SPY economic distributions,118 source/118 wheel passes and exact actual-data reproduction. Product source/environment unchanged. Partial coverage remains explicit:111 unmatched provider dividends, historical knowledge/mapping/lifecycle/sector gaps and full warmup. Existing credential/feed permissions persist. Follow docs/CURRENT_CHECKPOINT.md; do not treat the24-request batch limit as proof that all further sources are unavailable. No real Snapshot, protocol seal, strategy run, publication or new deletion.

10October2026 follow-up: reports/M1_ACTION_FOLLOWUP.md and docs/CURRENT_CHECKPOINT.md are current.127checks per environment;66additional provider links and71additional date fills.45events remain unmatched and22NVIDIA amount conflicts unresolved. Continue supported source/metadata work autonomously; no routine reapproval, unchanged-denial retry, financial admission, product/environment changes or deletion.

10 October 2026 announcement increment: reports/M1_ANNOUNCEMENT_EVIDENCE.md and artifacts/m1/announcement_evidence.json supersede prior current-status counts. 151 checks per environment; 13 additional XOM links, 26 date fills, seven NVIDIA raw amounts corroborated. 32 events remain unmatched and 15 NVIDIA amount differences unresolved. Both review findings repaired; v1 preserved and v2 current. Continue bounded source/metadata qualification under existing authority. Full M1 and protocol/financial admission remain incomplete.

10 October 2026 cash continuation: all22 prior NVIDIA raw-cash differences have dated issuer corroboration; vendor normalization remains unproved. 163 checks per environment, exact reproduction and independent review;294/317 provider links,23 unmatched(UNH14/XOM9). Current report reports/M1_CASH_CONTINUATION.md; receipt artifacts/m1/cash_continuation.json. Continue bounded remaining-source and identity/metadata work under existing authority, preserving all evidence and caps.

10October2026 XOM closeout:175 focused checks per environment; independent review clean;301/317 linked,16 unresolved(UNH14/XOM2),298 date fills. Four ambiguous2020 amounts remain unknown in raw observations; retrospective corroboration has unknown historical availability. Current receipt artifacts/m1/xom_evidence.json; report reports/M1_XOM_EVIDENCE.md. Continue independent identity/metadata qualification under existing authority.

10October2026 identity/metadata:205 checks per environment after12 red-to-green validation regressions; independent review closed all findings.13 current provider assets,12 SEC matches,11 stock SIC classifications. Historical UUID/tradability remain unverified; XOM successor and Meta/Roundhill distinctions recorded. Sector table is a dated proposal, not adopted/GICS. Current report reports/M1_IDENTITY_METADATA.md and receipt artifacts/m1/identity_metadata.json. Continue exact historical filing-index leads for16 dividend gaps; no changed financial gates.

10 October 2026 historical-source closeout: 216 focused checks passed in each environment, exact result reproduction, independent review with no material defect. Two additional review leads were checked via cached SEC text and concern merger/debt events. Coverage stays 301/317; 16 events unresolved, with a candidate UNH payment-date conflict retained. Current receipt artifacts/m1/historical_filings.json; report reports/M1_HISTORICAL_FILINGS.md; exact remaining requirements reports/M1_REMAINING_INPUTS.md. Available inspected sources do not qualify the real-input contract. Next action is to freeze and verify a reliable new source for the missing event/mapping facts, then requalify; no warmup, realSnapshot, protocol adoption or strategy execution on unqualified inputs. No global claim that no source exists. All budgets and existing permissions remain unchanged.

10 October 2026 renewed qualification: 303/317 linked, 302 date fills, 14 UNH records unresolved. Both remaining XOM declarations retained; 240 source and 240 installed-wheel checks pass; retained real sample and exact two-artifact reproduction verified; independent review clean. Full qualification remains rejected. Record dates/CUSIPs/exact original arrival are not universal gates. Product source/environment unchanged; real-provider adapter and full warmup remain after viable input contract, followed by explicit protocol adoption and baseline tests. Current report reports/M1_INPUT_QUALIFICATION.md, receipt artifacts/m1/input_qualification_followup.json, checkpoint docs/CURRENT_CHECKPOINT.md, draft docs/M1_REAL_PROTOCOL_DRAFT.md. Existing permissions/caps unchanged; no new price/credential use, deletion or publication.
