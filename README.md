# Compertum

A supervised solo quant research system with bounded AI proposals, reproducible experiments, independent audits, and gated paper trading.

## Current status

This is a fresh source workspace created on 8 October 2026. M0 Task 1's cloud setup is verified: the wheel-only lock, dependency imports, owned package build and second clean environment pass. Task 2 adds validated immutable records, five strict schemas and fixed resource/configuration limits. Native Windows validation is pending; overall M0 remains incomplete and strategy evaluation/paper trading remain disabled.

The selected private repository is [BrennanCompertum/Compertum](https://github.com/BrennanCompertum/Compertum). This checkpoint uses the isolated `codex/m0-bootstrap` branch. See [bootstrap progress](reports/M0_BOOTSTRAP.md) and [Task 2 evidence](reports/M0_TASK2.md) for the resume point, and [Windows handoff](docs/WINDOWS_HANDOFF.md) for local Codex instructions. Detailed historical logs and wheels remain in the saved checkpoint ZIP; they are not tracked in this repository.

The existing home project is preserved separately. Its test results and acceptance receipts do not establish this repository's readiness.

## Start here

1. Read [Cloud development handoff](docs/CLOUD_HANDOFF.md).
2. Read [Build specification v1.1](docs/BUILD_SPEC.md).
3. Follow the nine ordered tasks in the [M0 implementation plan](docs/M0_IMPLEMENTATION_PLAN.md).

Cloud work can develop and test portable M0 components. Windows process ownership, named pipes, Job Objects, storage monitoring, recovery, and the existing Strata server require native validation on the home PC before M0 acceptance.

New spending is $0. Use existing subscription access. M0 enables no broker transport or orders. Engineering completion and strategy acceptance have separate gates.

## Read-only setup inspection

With an existing Python interpreter, from the project root:

```text
python -B tools/environment_receipt.py
python -B -m unittest discover -s tests -p test_environment_receipt.py
```

The first command prints observations without creating an environment or contacting providers. Exit 0 means inspection ran, not that M0 passed. Tests create small, unique fixtures under `.cache/test-runs/`; they are development checks, not native acceptance.

With the installed package, the same inspection is available through `python -B -m compertum.environment`. A setup-only `compertum-setup` entry point is also packaged; use `PYTHONDONTWRITEBYTECODE=1` with it for inspection without Python bytecode writes. The full runtime CLI is not implemented yet.

The home interpreter target stays Python 3.14.7. Package metadata declares source compatibility with 3.12-3.14 for cloud development; observed cloud Python is 3.12.14. Native home installation/imports remain unverified. Windows wheel-only resolution has passed a cloud preflight; that is not native acceptance. No interpreter was installed or replaced.
