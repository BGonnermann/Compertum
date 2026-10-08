# M0 bootstrap progress

Status: **M0 INCOMPLETE — Task 1 cloud checks pass; native target checks pending.** This fresh source workspace has no acceptance credit from the earlier home project.

## Verified cloud setup

- Preserved BUILD_SPEC v1.1 and the M0 plan byte-for-byte.
- Resolved 39 packages in universal uv.lock, including the owned package and platform-conditional dependencies. Both Linux environments contain 38 installed distributions, including Compertum.
- Installed third-party wheels with --locked --no-install-project --no-build --no-managed-python --no-python-downloads. No third-party source build or interpreter download.
- Installed owned source separately with the locked setuptools backend, without dependency resolution/build isolation.
- All specified runtime and development dependencies import on cloud Python 3.12.14.
- Built compertum-0.0.1-py3-none-any.whl. A second fresh environment installed that noneditable wheel. Distribution versions, lock hash and installed wheel tag/lock identities match exactly. The clean package imports from site-packages, not the editable source tree.
- Windows/Python 3.14.7 wheel-only resolution preflight against exported locked requirements succeeds. This is cross-platform resolution evidence, not a native installation/import check.
- Ten focused pytest checks pass, including an owned incompatible-wheel fixture that blocks resolution without creating an environment or changing the lock. Fixture code is not built/imported. Small fixtures remain under unique project-local .cache/test-runs/ namespaces.

Observed tools: cloud Python 3.12.14, Git 2.51.1, uv 0.12.23. Native Windows 11/Python 3.14.7 remains the target; no home interpreter change occurred.

Lock SHA-256: 0c65878c37ef75171be95896bfb77b972dc74a1058ba230d755927ed14f0a315.

Owned wheel SHA-256: 4baaa62bdae43d2fa14dd50c4fbc0a7fb754a2ea7c7488b046d7a382971f809c.

## Interfaces and evidence

compertum.environment.collect_environment(project_root) records metadata, bounded document/source hashes and explicit unknowns. It writes no application files/receipts. tools/environment_receipt.py launches source; compertum-setup is a setup-only packaged entry point. Use Python -B or PYTHONDONTWRITEBYTECODE=1 to suppress interpreter bytecode writes during read-only inspection.

tools/verify_environment.py checks isolated-environment imports, versions and installed WHEEL tags against lock wheel identities. uv verified downloaded hashes; this helper does not independently re-download archives. The metadata collector keeps its own unperformed import check UNVERIFIED; separate receipts verify imports.

Commands, logs and receipts are included in checkpoint_evidence/ in the saved bundle. Source/cache/both environments occupied approximately 470 MiB at the cloud du observation. This does not establish native allocation, reserve or watchdog acceptance; those remain Task 5 work.

## Earlier failure and review

The first package-index attempt timed out (exit 2); no environment was activated then. Access later recovered and the same wheel-only lock succeeded. The retained error is historical, not the current dependency state. No interpreter incompatibility was inferred.

The first checkpoint received one independent review: one Important bounds issue, no Critical/Minor findings. Four RED-to-GREEN regressions fixed file reads/traversal and incomplete hash observations; nine tests then passed. This update packages that helper, resolves dependencies, verifies reproduction and adds a wheel-incompatibility fixture. Its bounded independent review result is included separately in checkpoint_evidence/.

## Pending gates and resume

- Native Windows interpreter/hardware/storage observations and actual installation/imports remain unverified. Every later ownership, role-authenticated IPC, Job Object, storage/recovery and provider gate also remains unverified.
- The referenced preparation brief was not supplied; provenance remains unverified.
- Historical connection gate: BGonnermann/Compertum returned 404 while the checkpoint was prepared. On 8 October 2026 the owner selected and connected BrennanCompertum; private access to BrennanCompertum/Compertum is now verified. The checkpoint is prepared for its isolated `codex/m0-bootstrap` branch on top of the initial remote history. Confirm the actual branch head before local work; detailed historical receipts remain in the saved ZIP.
- Task 2 portable contracts/configuration are implemented; see reports/M0_TASK2.md. Tasks 3-9 have not started. This helper is not compertum doctor, a runtime supervisor or an enforcement adapter.

Next: follow `docs/WINDOWS_HANDOFF.md` from the selected GitHub branch. Verify native Task 1 and rerun portable checks before implementing Task 3 on Windows. Do not force-push the unrelated historical cloud or home history, move the home project or raise budgets.

## Decisions and costs

1. Authorized cloud development uses existing Python 3.12.14; source metadata allows 3.12-3.14 while .python-version retains 3.14.7. Cost if wrong: actual native compatibility may require a separate decision.
2. Preserve an isolated branch and saved source while remote access is unavailable. Cost: reconcile against the remote tree after access is restored; no publication claim.
3. Stop activation after the first network failure, then resume only after wheel-only resolution succeeds. Cost: temporary delay; no dependency gate waived.
4. Future native/runtime/AI/provenance/sync review exclusions remain unverified and assigned to their owning tasks. Cost if wrong: a checkpoint could be mistaken for a runtime, so M0 stays explicitly incomplete.

New spending: $0. Product AI/provider qualification requests: 0. No broker transport, authenticated market-data fetch or financial calculations. M1 remains disabled.
