# M1 offline data component - 9 October 2026

- Status: **OFFLINE_COMPONENT_VERIFIED**. M1 is not complete.
- Built strict checks for synthetic daily prices, raw minute references, split adjustments, action dates and exchange-session timing.
- Rejects duplicate or missing rows, mixed feeds, malformed prices/timestamps and information unavailable at the09:25 New York decision cutoff.
- Future minute references never enter feature rows. Future-effective split information is checked before adjusted rows can be returned.
- Keeps actual receipt/admission timestamps separate from simulated historical availability. Unknown action knowledge remains diagnostic; no provider/financial acceptance claim.
- Produces immutable, repeatable snapshots; corrections create new identities. Uses M0 coordinator-owned storage grants and aggregate task output budgets.
- Retains rejected synthetic examples. Sensitive or malformed input keeps only its fingerprint. Damaged/interrupted publication refuses a false success.

## Measured checks

| Run | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| New component plus related M0 contracts/config/storage/persistence/consumption/recovery | 131 | 0 | 0 |
| New component from installed wheel | 38 | 0 | 0 |

Source and wheel are Python3.14.7 with the same locked distributions and unchanged lock. No third-party package was installed or changed. The project wheel was built offline and installed with no dependency resolution into the existing isolated reproduction environment; its previous wheel and all prior evidence remain available.

Exact snapshot SHA256: `68967044c3718633972ffe7c6a23447f9fde992694369428c137d4fdd1f21673`.
Feature rows SHA256: `e3313c29e65e284f21d0a6333293ebda91e31eaffbcd2c001d4b597fbc44f7ff`.
Both environments match exactly. Current package SHA256: `dac632b1213aa6595d3b377121182d7a30c628d7545912708ca1fa6bfb4c0c50`.

Source command: `.venv/Scripts/python.exe -B -m pytest tests/test_data_snapshot.py tests/test_data_publication.py tests/test_contracts.py tests/test_config.py tests/test_storage.py tests/test_persistence.py tests/test_consumption.py tests/test_recovery.py -q --tb=short --basetemp .cache/test-runs/m1-offline-20261009-01/source-verified-tmp --junitxml .cache/test-runs/m1-offline-20261009-01/source-verified.xml`.
The installed-wheel run used the two new test modules and a separate fresh scratch directory. Do not reuse either basetemp. Exact build/install/check argv, exit codes and logs are in the evidence directory's `commands.jsonl`.

## Review and repaired failures

Independent review found escaped secret text could survive rejection, malformed session types could bypass stable error handling, future split knowledge could enter older features, and corrupt retained files could trigger unbounded reads. Each repair has retained failing and passing regressions. An injected interruption after durable publication confirms that the saved bytes survive and retry refuses to invent a success receipt. Final review found no remaining material issue in this component.

## Storage incident and preservation

I included a recovery regression that allocated another1GiB reserve. Scratch temporarily reached5,529,228,048 bytes, exceeding its5,368,709,120-byte limit. This was a verification-orchestration mistake, not an increased limit.

After that test completed, its128-file fixture was moved within this project into `backups/m1-test-evidence-20261009-01`. All file lengths and SHA256 hashes matched before and after the reversible move. No evidence was deleted and no old fixture was reused or cleared. `archive-verified.json` maps the original paths to the archive; the archived fixture is evidence, not a live project. This archive does not constitute an operational recovery or disaster-recovery qualification.

Current categories are within all unchanged caps. Latest measured scratch: 4454346240 bytes; backups: 1076773112 bytes. New regression runs must inspect fixture allocations before execution. Avoid repeating the full-reserve recovery fixture.

Original Compertum project, all M0 receipts and its source archive remain unchanged. New code is confined to the development checkout. No provider or model requests, real-data collection, trading, spending, training, commits, pushes or publishing occurred in this component.

## Files and next work

- Code: `src/compertum/data/`.
- Tests: `tests/test_data_snapshot.py`, `tests/test_data_publication.py`, `tests/helpers/data_fixture.py`.
- Plan: `docs/M1_OFFLINE_PLAN.md`.
- Receipt: `artifacts/m1/offline_data.json`; review: `artifacts/m1/review.json`.
- Evidence: `.cache/test-runs/m1-offline-20261009-01/`, including source/wheel JUnit, red/green logs, exact fingerprints, storage incident/archive records and wheel.
- Next: offline baseline simulation. Full M1 still needs the remaining pipeline and separately authorized real-data coverage/action/reference checks. No strategy has been evaluated.
