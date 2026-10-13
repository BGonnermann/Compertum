# M0 native verification follow-up

Date: 8 October 2026 ET. Status: **M0 INCOMPLETE; NATIVE TASK 3 UNVERIFIED**.

## Operator-reported measurements

The owner supplied this summary from local Codex. Cloud has not accessed the original Windows report, JUnit or logs. These are attributed measurements, not independently reproduced cloud observations.

- Checkout: `C:/Users/bgonn/Desktop/Compertum-native-20261008-01`.
- Repository: `BrennanCompertum/Compertum`; detached `origin/main` commit `68f9643cc591b7a3ab3307f3351fae324b4fd729`.
- Windows 11 Home x64, build 26300; Python 3.14.7; uv 0.12.1.
- Two fresh environments reproduced all 39 distributions, imports and wheel identities; no lock changes or third-party source builds.

| Check | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Portable source | 189 | 0 | 2 | 11 |
| Installed wheel | 178 | 0 | 2 | 4 |
| Native all | 28 | 25 | 0 | 0 |
| Fresh-process registration | 0 | 11 | 0 | 0 |

Each source/wheel error pair concerns one test's setup and teardown. The report states all 59 published files and 83 original source files retained their hashes, with no source edits, publishing, runtime migration, provider requests or spending.

Evidence retained on PC: `.cache/test-runs/windows-20261009-01/REPORT.md` and `result.json`. An inherited provider key appeared in an initial traceback; operator reports retained logs redacted and subsequent runs allowlisted. Rotation remains an owner action; no key value is retained here.

## Bounded source repair

1. **Oversized pytest identity:** the 65,537-byte malformed input received an automatic parameter ID. Cloud collection reproduces an ID beyond the Windows 32,767-character environment-variable limit. Short explicit case IDs preserve every malformed input and assertion. After the change, all 257 collected IDs are at most 140 characters.
2. **Launcher/worker identity:** the native report confirms a launcher/worker PID mismatch. CPython 3.14.7 `PC/venvlauncher.c` launches the base interpreter as a second process and sets `__PYVENV_LAUNCHER__`. Native helpers now launch the same `sys._base_executable` directly, preserve `sys.executable` through that marker, and retain the existing explicit inherited-handle list. No fallback interpreter lookup is allowed. Peer identity checks remain strict. The added native test must prove PID, environment, interpreter version and dependency import together; cloud cannot prove this.
3. **DACL and cancellation:** no permission weakening, expectation removal or quarantine reset. The DACL probe's unexpected successful client open does not prove a competing server can be created. Exact redacted native traces and a server-side denial observation are still needed. The first cancellation failure's operation and Win32 completion results are needed before changing buffer lifetime behavior.

Primary implementation reference: https://github.com/python/cpython/blob/v3.14.7/PC/venvlauncher.c . Named-pipe access reference: https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights .

## Cloud evidence and limits

- Launch-selection regressions: two behavioral failures against the original launch behavior, then both pass with the repair. These use a captured process-call adapter and do not establish native PID behavior.
- Targeted protocol/launch tests: 30 passed.
- Full repair source suite: 203 passed, 54 skipped; all skips native Windows and UNVERIFIED.
- Collection bound: 257 test IDs, longest 140 characters.
- `git diff --check`: clean.
- Independent read-only review: no Important or Critical findings; reviewer independently measured 30 targeted passes and 54 native fixtures collected. No deferred minor findings.
- Production package behavior, lock, original specification and implementation plan are unchanged.

## Rulings and next gate

Ruling: interrupt unpublished Task 4 source work for an isolated Task 3 fixture-repair checkpoint, because actual target failures take priority. Cost if wrong: later source development is delayed; Task 4 changes remain preserved separately.

Ruling: publish only the demonstrated pytest fix and reviewable direct-runtime fixture candidate; do not guess at DACL/cancellation fixes without primary native traces. Cost if wrong: another bounded native diagnostic run is required. No native pass is claimed.

Next: publish the reviewed candidate, then run allowlisted Windows verification against the exact new commit. Obtain the redacted full report and earliest DACL/cancellation traces. No task-done or M0 acceptance claim; paper trading remains disabled.
