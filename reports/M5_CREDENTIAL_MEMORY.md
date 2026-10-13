# Native credential memory

11 October 2026. **377 matching source/package checks passed, zero failures/errors/skips.** Thirty checks cover actual Windows DPAPI with invented keys, owner lifetime and cleanup failures. Independent review closed2/3. All148package modules and configuration/schema/lock bytes match.

Current-user DPAPI binds each encrypted record to the native project identity, account alias and fixed paper endpoint. Whole-payload integrity is checked after decrypting. Open plaintext is registered with the execution lease and wiped at context exit or owner release. A real child-process exit and new execution generation can reopen the synthetic envelope. Wrong role/context, corrupt material and closed ownership refuse access. Native output is cleared before LocalFree, including failed calls; cleanup failure prevents plaintext return. Caller-owned input bytearrays remain caller-owned. No credentials are discovered or persisted; no network operation occurs.

Review found that valid-shaped corrupted plaintext could evade the initial context-only check. The regression failed before the complete-payload integrity correction. Native tests and a separate semantic reproduction now agree across source and wheel. Randomized ciphertext is intentionally different. Python header strings cannot guarantee erasure of all copies; this does not protect against hostile same-user code.

Source `fca97981232815826c2271fd56b5d3b062360604d411913293321af763c73b07`; wheel `5b0212d10aa56eb26de4b5839a02a14aad6c8c427eea9c91a9ab890b2bcaa898`. [Receipt](../artifacts/m5/credential_memory.json). Detailed evidence `.cache/test-runs/m5-paper-credentials-20261011-01`. Earlier failures retained; only verified passing fixture copies were archived and removed.

Next: prepare the bounded cooperative paper GET transport and OS-protected provisioning under existing owner controls before requesting actual credential/read authority. M5 actual walkthrough and M6 remain incomplete.
