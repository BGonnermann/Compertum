# M2 covariance mathematics

70 source tests and 70 installed-wheel tests passed, with zero failures, errors or skips. Raw-array and symbolic outputs match exactly. Independent non-author review passed after repairing masked missing inputs, unstable centering with large offsets, and condition-number reporting for permitted negative roundoff.

The component accepts singular PSD covariance for quadratic forecasts and separately refuses unsafe inversion. It preserves original arrays and any tiny negative result rounded to zero. The 12-observation, 12-asset fixture has rank 11; shrinkage cannot repair a zero-variance asset by assumption. No jitter, variance floor or pseudoinverse is used.

[ClaimPacket](../docs/M2_COVARIANCE_CLAIM.md) contains the proof, domains, examples, counterexamples and executed command references. [Receipt](../artifacts/m2/covariance.json) binds source, wheel, raw-array audit, review and storage evidence. Trading usefulness is UNVERIFIED. This completes a mathematical component, not the 12-variant M2 campaign.

Next: fixed variant registry, training cutoffs, training-only scaling and deterministic ridge artifacts, using bounded synthetic fixtures until campaign inputs qualify.
