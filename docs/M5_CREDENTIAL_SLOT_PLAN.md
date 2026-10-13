# One execution-owned protected credential slot

11 October2026. Offline supporting work: use invented credentials only, no V20/OS authentication-store reads, account calls or real grants. Existing native current-user DPAPI envelope stays unchanged. Primary implementation plus one reviewer, maximum three review/repair passes.

One fixed state/paper-credentials.bin slot, local alias/project/origin bound. Each ciphertext envelope file is at most8KiB. Add one16KiB RUNTIME reservation through existing coordinator admission to cover target plus one incoming staging file. No new table/journal/category; no credential bytes in SQLite or ordinary published artifacts. Existing recovery selects PUBLISHED record artifacts and excludes RUNTIME credentials. Private encrypted read-evidence storage follows separately.

Execution verifies exact runtime reservation and coordinator DB/project identity before typed provision/load. Preserve owner/generation/path/regular-file guards. Atomic native metadata publication with readback; same exact protected envelope is idempotent, any different existing slot conflicts. No rotation, multiple aliases or delete. Existing incoming staging blocks another write/load instead of accumulating files or guessing recovery. All plaintext access remains inside current execution lease. Ordinary receipts contain alias and ciphertext metadata only; check metadata for reflected keys. Error strings never quote inputs.

- [x] Admit fresh64MiB namespace and reproduce missing component.
- [x] Implement fixed slot, unchanged DPAPI bounds, reserved native publication/load and conflict/staging checks.
- [x] Test absent/corrupt/wrong alias/project/role/reservation, path/reparse/hardlink guards, idempotency, interruption, reflected metadata, native child exit/reopen and backup lineage exclusion.
- [x] Independent review, paired source/package regressions, exact local reproduction, retained receipts and checkpoint.

Intentional supporting source change: add only the exact credential RUNTIME path to storage.reserve_runtime_paths. Preserve other completed source bytes. This component neither exposes an operator credential command nor authorizes reading an actual key.

Supporting native publisher change: optional replace=False retains existing default behavior; slot selects create-only. DB pin held through connection close.
