# Native startup verification

354 unique checks passed in each environment, with identical test IDs and zero failures/errors/skips in the final matrix. Source and installed wheel match the frozen package.

Workers now verify the actual executable before they run and start with an unused Python cache path. Their recorded startup identity must match the result before acceptance or reuse. Managed owners make the same check through their authenticated channel. Substitution, stale bytecode, malformed proofs and cleanup failures have retained regression evidence.

Independent review findings were reproduced and repaired. All failures remain recorded, including one test-script argument error and the suite-wrapper timeout, plus two temporary RAM-floor refusals. Native limits remained unchanged. The pure frame test fixture also needed its explicit empty attempt history; production checks were unchanged. All native auditor and scorecard recovery cases were also rechecked. Passing disposable copies were removed only after their archives were byte-verified. Limits are unchanged.

Receipt: artifacts/m3/native_startup.json. This is a startup component result; clean environment preregistration and complete M3 acceptance remain pending. Next: docs/M3_ENVIRONMENT_ADMISSION_NOTES.md.
