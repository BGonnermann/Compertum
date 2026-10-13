# M2 ClaimPacket: diagonal covariance shrinkage

Status: PURE_MATHEMATICS_COMPONENT_VERIFIED; trading usefulness UNVERIFIED. Classification: established linear algebra and an empirical risk-estimation method. Author: primary Codex. Independent reviewer must not be the author. No novelty, alpha, inverse availability or profitability claim follows from the mathematics.

## Statement, domain and units

Let X be a finite real n-by-p matrix of aligned, complete-case returns, n>=2 and 1<=p<=12. Every row describes the same entry/exit interval across assets. Let Xc subtract each column mean, S=Xc.T Xc/(n-1), D=diag(S), and A_delta=(1-delta)S+delta D. The bounded study permits only delta=0,1/4,1. Returns and portfolio weights are dimensionless; covariance and quadratic forecasts have squared-return units.

1. S and A_delta are positive semidefinite (PSD) in exact arithmetic for delta in[0,1].
2. If delta>0 and all S_ii>0, A_delta is positive definite (PD).
3. If any S_ii=0, positive delta alone does not establish invertibility. Singular PSD remains valid for quadratic forecasts.
4. For12centered observations of12assets, rank(S)<=11. No numerical inverse claim is justified for delta=0.
5. Algebraic PD does not guarantee this implementation's stronger numerical inversion gates. Ill-conditioning, tiny eigenvalues and nonfinite arithmetic may still reject inversion.

## Derivation

For any real vector z, z.T S z=||Xc z||_2^2/(n-1)>=0, proving PSD. Each diagonal entry is nonnegative, so z.T D z=sum_i S_ii z_i^2>=0. A convex combination therefore remains PSD.

For nonzero z and strictly positive diagonal, z.T A_delta z=(1-delta)z.T S z+delta sum_i S_ii z_i^2>=delta min_i(S_ii)||z||_2^2>0. Thus A_delta is PD for0<delta<=1. This proof requires S PSD; positive diagonal alone is insufficient for an arbitrary indefinite input.

Centering multiplies X by H=I-11.T/n. H has rank n-1, hence rank(Xc)<=min(n-1,p), and rank(Xc.T Xc)=rank(Xc). At n=p=12, rank(S)<=11. This is expected geometry, not failed covariance validity.

If S_ii=0 for a PSD matrix, all S_ij=0: the2-by-2principal minor requires S_ii S_jj-S_ij^2>=0. The coordinate vector e_i remains a null vector of A_delta for every delta, so positive shrinkage cannot repair zero variance without changing the stated model.

## Worked examples and adversarial cases

- S=[[1,1],[1,1]], w=[1/2,1/2]: delta0 gives variance1 and a singular matrix; delta1/4 has eigenvalues1/4,7/4 and variance7/8; delta1 gives identity and variance1/2. Only the latter two are algebraically invertible.
- S=diag(1,0): every delta leaves a zero eigenvalue. w=[0,1] has valid zero forecast; inversion must be refused.
- S=[[1,2],[2,1]] has positive diagonal but eigenvalue-1. At delta1/4 its off-diagonal is1.5 and minimum eigenvalue-.5. This refutes dropping the PSD assumption.
- The centering matrix H for12assets provides a deterministic rank11monthly fixture with positive diagonal. No random seed or favorable selection is required.
- S=diag(1,1e-12) is algebraically PD but fails both the scaled eigenvalue and conditioning inversion gates. The quadratic forecast remains valid.
- Pairwise deletion across differing intervals can create S=[[1,1,1],[1,1,-1],[1,-1,1]], with eigenvalue-1. A covariance computed from common complete rows cannot produce this exact matrix. Missing/asynchronous input must be rejected or assembled as explicitly aligned complete cases before estimation.
- sqrt(x**2)=x is false over unrestricted real x; x=-1 is a counterexample. A symbolic checker may establish sqrt(x**2)=abs(x) for real x or=x for nonnegative x. Unknown symbolic results remain UNVERIFIED.

## Exact numerical gates and implementation template

Use the already locked NumPy/SymPy versions and float64; record versions in the receipt. Keep raw input arrays unchanged. Proposed pure module compertum/mathematics/covariance.py has bounded aligned-sample covariance, fixed-delta shrinkage and a matrix/weight assessment. There are no I/O, model promotion, protected-data or trading operations.

Before symmetrizing a finite square input A, require ||A-A.T||_2<=1e-10 max(1,||A||_2). Then use B=(A+A.T)/2. Reject a materially negative eigenvalue below -1e-10 max(1,||A||_2). Finite dimension-matched weights w produce the quadratic value v=w.T B w without inversion. Record v and eps_v=1e-10 max(1,||A||_2)||w||_2^2; round only v in[-eps_v,0) to zero. Reject v<-eps_v. A zero weight vector has zero forecast and zero adjustment.

For inversion separately require minimum eigenvalue>1e-10 max(1,||A||_2) and condition number<=1e8. Otherwise report INVERSION_REJECTED while retaining an accepted PSD forecast. Never add jitter, a variance floor or pseudoinverse. Nonfinite intermediate norms/eigenvalues/quadratics and numerical solver failure are explicit refusals, not passes.

Complete-case estimation requires finite numeric rows and matching interval identifiers for all assets in a row; reject missing values, nonmatching identifiers and duplicate intervals. An identifier alone does not prove historical availability or a valid horizon. Actual return assembly/cutoff checks remain part of the later qualified research campaign.

## Falsifiable checks, evidence and limitations

Tests must independently hand-calculate the examples above; verify rank<=11, limiting deltas, zero variance, nearly collinear columns, missing/asynchronous rows, asymmetry and nonfinite values. Check the exact boundary and record permitted tiny negative rounding. Reconstruct from retained raw arrays, not the author's result summary. Include deterministic counterexamples and symbolic sign assumptions. Source and installed-wheel results must match exact classifications and the declared numeric tolerances; neither an unknown symbolic result nor an absent artifact passes.

Expected commands after implementation: python -m pytest tests/test_covariance.py; a retained independent audit script reruns raw-array eigen/quadratic calculations and symbolic examples in both locked environments. Exact commands, outcomes, raw arrays and code hashes will be placed in the receipt; they are not yet evidence of a completed check.

Trading usefulness is UNVERIFIED. The later predeclared study uses exactly252completed daily entry-to-next-entry intervals, requiring253aligned minute references across the watchlist. Backward nonoverlapping H-session compounded blocks yield at most252/50/12observations forH=1/5/21; at least12complete blocks are required. Only label-available endpoints enter, and missing blocks never extend the lookback. It also needs fixed weights, identical samples/means across deltas and the specified out-of-sample second-moment forecast score. This component cannot select a delta by returns, alter allocations, create a thirteenth strategy variant or satisfy the12-variant M2campaign. Full campaign data and financial qualification remain dependencies.

## Sources and contribution

The derivations above are elementary established matrix algebra, supplied here for inspectability. The contribution is a specification-bound implementation and failure tests, not a new theorem. Official numerical references describe sample covariance normalization and symmetric eigensolver assumptions: [NumPy covariance](https://numpy.org/doc/stable/reference/generated/numpy.cov.html), [NumPy eigh](https://numpy.org/doc/stable/reference/generated/numpy.linalg.eigh.html). [SymPy assumptions](https://docs.sympy.org/latest/guides/assumptions.html) documents domain-dependent symbolic reasoning. Retrieved10October2026; use actual locked-library receipts to establish implementation behavior. These references do not prove the proposed trading benefit.
## Executed verification

10 October 2026: 70 source and 70 installed-wheel tests passed, zero failures/errors/skips. Exact raw-array and symbolic outputs agree. Locked NumPy 2.5.3 and SymPy 1.14.0 were used. Independent non-author review approved after red-to-green fixes for hidden masks (including nested rows), unstable large-offset centering, and spectral condition numbers on permitted negative roundoff.

Retained commands: `.cache/test-runs/m2-covariance-20261010-01/source-complete-command.json`, `wheel-complete-command.json`, `audit-source-complete-command.json`, `audit-wheel-complete-command.json`. The test command is `python -m pytest tests/test_covariance.py -q` with the recorded fresh basetemp/XML paths; audit entry point is `audit-reviewed.py source-complete` or `wheel-complete`. Retained raw inputs: `raw-arrays-reviewed.json`; independent review: `independent-review.txt`; receipt: `artifacts/m2/covariance.json`.

Covariance calculation uses offset-first centering. Active masks are rejected before numeric conversion. Condition number uses absolute symmetric eigenvalues, independently of the positive-eigenvalue inversion gate. No variance floor, jitter or pseudoinverse was added. Full campaign return assembly and out-of-sample score remain pending.
