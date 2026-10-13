# M2 immutable model-fit checkpoint

Separate model preparation from evaluation so the saved campaign can checkpoint each successful annual fit. This is synthetic engineering only, with no activation/promotion authority.

- [x] Prepare a bounded immutable FitCheckpoint containing the dataset assembly, FitRows, annual manifest and fitted model, with candidate/year/training/source identities and hashes. Reject provider/protected prices and unregistered/non-ridge variants before fitting.
- [x] Resume evaluation only with the exact expected checkpoint hash supplied by its trusted caller. Revalidate canonical structure, input identity, all nested hashes, fit manifest regeneration, model/fit binding and predictor contract. The hash binds a trusted artifact; it does not authenticate an arbitrary caller or prove an independently approved fit.
- [x] Reuse the stored model without calling the fitter. Preserve current evaluate_candidate behavior and exact output bytes when no checkpoint is supplied. Momentum refuses fitted checkpoints. Annual data/candidate/year/window changes require a different checkpoint.
- [x] Test no-refit reuse, corruption, wrong expected identity, changed inputs/candidate/cutoff, protected/provider rejection and output parity. Source/wheel regressions and all12retained candidate outputs, one independent reviewer, at most3targeted repair rounds. <=16MiB checkpoint; fresh namespace<=64MiB;120seconds per command.
- [x] Retain receipt and continue coordinator-owned persistent fit/fold checkpoints and recovery. No pure artifact API claims durable publication, actual audit approval or fullM2 completion.

Saved lifecycle design dependency: keep existing9-unit replay template unchanged. A separately registered campaign template will need explicit phase/candidate/year/dependency bindings, owner-verified model artifacts, unchanged4CPU/4GiB/daily7200second limits, two transient attempts, and no skipped or duplicated completed fits after recovery. Commit inputs and registry before computation. Preserve failed variants and continue independent tasks where resource/health state permits.
