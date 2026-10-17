# Ownership and accounting

16 October 2026. This work supplies gate 2 of `M5_PAPER_ADMISSION_PLAN.md`.
The first bounded increment implements deterministic calculations. A later
private owner wrapper must authenticate the original inputs before admission.

## Calculation contract

Add `calculate_reconciliation` in `src/compertum/paper_reconciliation.py`.
Accept only keyword arguments: project ID, account alias, opening cash,
current cash, retained attempts, observed orders, observed positions and
activity rows. Collections are bounded tuples. The opening has zero holdings
and orders because the immutable opening producer requires that condition.
Limits are 256 attempts, 200 orders, 64 positions, 200 activity rows and 1 MiB
of combined canonical encoded inputs. Each number retains the existing
64-character bound. Share quantities cannot exceed one billion.

Validate each retained attempt with the existing disjoint record validator.
Only native submit and cancel records can explain native observations.
Bind each order to its original stable client ID and exact submitted terms.
Require every native submission to appear in complete observed order history.
Missing or uncertain submissions cannot be treated as absent orders.

Apply each exact fill once in transaction-time order. Bind broker order ID,
symbol, side, whole quantity, cumulative quantity and remaining quantity.
Compare observed cumulative fills and prices with complete activity totals.
Reject overfills, missing fills, duplicate events, foreign orders, short
positions, unexplained holdings and negative intermediate cash.

Use bounded decimal arithmetic independent of the caller's decimal context.
Use precision 160 with inexact and rounded operations trapped. This exceeds
the accepted integer, fractional, quantity and summation digit bounds.
Compare cash within the existing $0.01 tolerance. Preserve the exact difference.
Unsupported activities and unexplained fees or actions remain blocking.
Bind symbols and asset IDs in both directions. Check attempt, submission,
fill and cancellation chronology. Limit fills cannot cross their order limit.
Position quantity, average entry price and cost basis must agree internally.
Full position cost reconstruction remains explicitly unverified.

The result is a private calculation, not proof of current ownership or cash
coverage. Always retain false transport and financial authority. Matching
arithmetic cannot prove absent delayed fees, complete corporate-action
coverage, fresh observations, native provenance or current owner identity.
Do not change public routes, native transport or existing admission gates.

## Verification and bounds

Freeze exact cases and source hashes before execution. Start with valid empty,
buy, partial-fill, cancel and buy/sell examples. Add identity substitutions,
missing/duplicate events, foreign activity, malformed values, quantity and
cash mismatches, caller decimal-context changes and collection bounds.
Run relevant existing activity, native-record and portfolio compatibility
checks in both source and installed environments.

Private evidence uses `artifacts/m5/ownership-economics-20261016-01`.
Temporary files use fresh `.cache/test-runs/m5-ownership-economics-20261016-01`
with a 64 MiB ceiling. The complete initial capacity census passed under
the current category caps, including this additional hold. It grants no
ordinary runtime or saved-stop recovery. All native fixture reserves remain.

Use at most three evidence-led review and repair rounds for this increment.
Final qualification needs a frozen wheel, matching exact source and installed
inventories, complete environment checks and independent review. Reuse the
successful isolated installed prefix; preserve its previous release archive.
Do not alter the original `.venv` or locked dependencies.

## Remaining gate 2 integration

Authenticate the immutable opening, complete external guard, current native
portfolio observations and encrypted native activity. Pin original bindings
before and after callbacks. Never refresh historical evidence into current
authority. Resolve fee/action coverage through qualified producers. Freeze
and verify those cases separately before connecting risk or dispatch.
