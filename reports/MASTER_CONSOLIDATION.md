# Master folder and GitHub consolidation

13 October 2026. Owner requested all new edits in `C:\Users\bgonn\Desktop\Compertum` and an up-to-date private GitHub repository for rollback.

## Preservation

- Verified backup of 179 original files including Git metadata: `backups/master-consolidation-20261013-01/master-before.zip`, SHA-256 `b7919f106a7864216d92eac339ed25ebddc8aa01577ec25d560e26b306dbbcca`.
- Original staged foundation saved in commit `999e55a826ba97c07fe00ba92e06c6a37e5d8ac6`. Archive retains unstaged original versions too.
- Copied 729 current development files, then archived six generated egg-info files; 723 canonical files remain before documentation additions. All 483 frozen source/config/test files match the verified release exactly.
- Reversibly moved 24 obsolete master-only source/test/tool files to `backups/master-consolidation-20261013-01/master-only-original`; they cannot interfere with current package/test discovery.
- Kept original preparation brief and `reports/M0_INDEPENDENT_REVIEW.md`. Brief hash matches BUILD_SPEC.
- Siblings, environments, data, runtime records and backups remain unchanged.

## Verification

Byte comparison passed. Independent review confirmed frozen identity and obsolete-file handling. Previous 545 paired checks remain historical development-environment evidence. Fresh master verification: **89 source and 89 installed-package tests passed**, zero failures/errors/skips, with identical test IDs and all190 Python modules matching. Initial run retained61 passes and28 setup errors: duplicate old/new project metadata caused the identity validator to reject fixtures. Archived the copied build metadata and installed the existing verified wheel offline without changing Python3.14.7 or third-party dependencies. The same tests then passed in both modes. Receipts: `.cache/test-runs/master-consolidation-20261013-01/verification.json` and JUnit files.

Independent publication review CLEAR1/3; six README links resolve; no excluded runtime/secret paths tracked; token/private-key pattern scan found no matches. `.gitattributes` preserves exact source bytes. Seven inherited blank-at-EOF findings are retained to preserve the frozen source. Published checkpoint047dce70314671be13d1edeb17ea5324e96848ec to `BrennanCompertum/Compertum` main. Remote read-back equals local HEAD. The merge preserved both prior histories and left the reviewed tree unchanged; all483 frozen Git blobs match their original hashes. No force update. The working tree was clean after publication.

M3 is incomplete: 63 source and 48 package outcomes were verified before interruption. A copied SQLite/WAL snapshot confirms source63 COMPLETED; wheel48 outcomes and49 attempts, with attempt49 still RUNNING and no completion receipt. No Python process remained when inspected. The interruption cause and valid recovery remain unresolved.

## Publication and rollback

Track code, config, tests, specs, plans and reports. Exclude secrets, environments, data, state, logs, private artifacts and backups. Historical reports may reference local evidence absent from GitHub.

Commit/push meaningful verified checkpoints under standing authorization; explicitly record incomplete work. No timer, force-push or destructive reset. Git restores tracked files; runtime recovery depends on preserved local records and identities.

## Publication-failure addendum

Integrated the four previously reviewed regression cases in `tests/test_final_audit_publication.py`, preserving the exact reviewed file hash. They passed4/4 against source and4/4 against the installed package. Combined fresh master coverage is **93 distinct tests per environment**, zero failures/errors/skips, same IDs. These simulated tests prove that failed result publication and restart with no published result remain blocked despite successful worker exit. They do not replace native campaign acceptance. Product source and all190 installed/source modules remain unchanged. Receipt: `.cache/test-runs/master-consolidation-20261013-01/final-verification.json`.
