# M3 clean environment and paired campaign implementation

Local synthetic engineering only. Extend the existing sealed campaign and bounded auditor routes. Preserve the original checkout and both existing environments, all financial gates and resource limits.

## Dependency checklist

- [x] Retain the exact38 compatible dependency wheels named by uv.lock;109086784B, all archive hashes verified. No package installation or version change. Evidence: backups/locked-dependency-wheels-20261010-01.
- [x] Observe actual installed payloads in both environments against those archives. Observation alone does not preregister or admit a campaign.
- [x] Integrate and verify the bounded payload-manifest primitive after the prior native campaign component is accepted. Archive hash and member evidence must use the same immutable <=64MiB buffer. Reject ambiguous metadata, unsafe/colliding paths, missing/changed bytes, unreadable inventory, unsupported rewritten scripts and resource overflow. Honor wheel library/data relocation. Pure primitive grants no run authority.
- [ ] Capture and pin actual interpreter/base executable, prefix, package/module/lock roots, source archive, wheel, dependency manifests and installer bootstrap. Pin uv _virtualenv.py/.pth separately; source-only editable hook must contain exactly the registered src path, with matching project metadata. Wheel lane refuses editable hooks or source-root imports. Generated installer metadata is separate evidence, not original-wheel payload.
- [ ] Before Python starts, give each new coordinator/evaluation/worker attempt a unique, initially nonexistent absolute PYTHONPYCACHEPREFIX plus -B/PYTHONDONTWRITEBYTECODE. Verify actual startup values and module origins. Reject unlisted sourceless modules/archive imports. Preserve old cache files; do not hash them as proof of original source execution. Enforce this in existing launcher allowlists and native identity binding; no arbitrary command route.
- [ ] Preregister source/wheel pair IDs, distinct run/seal IDs, common input/definition/data/holdout/runtime pins, expected environment-manifest hashes and exact comparison rules before either campaign exists. Extend coordinator ticket -> evaluation journal -> native admission; retain refusals and enforce unique membership. No retrospective clean label or caller pass flag.
- [ ] Through the bounded auditor route, compare all63 outcomes, own-environment fits, deterministic outputs, failure/skip reasons, scorecards and inner unit audits; retain different histories/process IDs/seal receipts separately. Matching failures remain failed.
- [ ] Integrate frozen shortlist/final transaction/recovery/operator controls, then freeze source for complete fresh paired63-unit campaigns and measure actual complete aggregate feasibility. Continue M4 afterward.

## Measured bounds and source references

Existing source scan:9819 original dependency payload files,345161969B,28.93seconds with staged full-inventory checker.98xx includes nested vendored RECORD payloads; only each installed distribution's own RECORD is rewritten. This was an ordinary bounded verification subprocess, not native Job admission evidence. All native workers remain120seconds/4GiB/4cores; owners remain256MiB and compact RPC remains64KiB/5seconds.

Use wheel relocation and installer-record rules from [PyPA wheel specification](https://packaging.python.org/en/latest/specifications/binary-distribution-format/) and [installed distribution metadata](https://packaging.python.org/en/latest/specifications/recording-installed-packages/). Python documents that [pycache_prefix redirects source-associated cache reads](https://docs.python.org/3.14/library/sys.html#sys.pycache_prefix); -B alone prevents writes, not reads. Native startup checks must establish the stated cache policy.

Initial staged regressions:39 pass. Independent review found an archive reread race and silently skipped traversal errors; targeted regressions reproduced and repairs applied. Keep final review and fresh integrated source/wheel verification before any acceptance claim.
