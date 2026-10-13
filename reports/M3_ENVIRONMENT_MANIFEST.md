# Pinned environment verification

105 unique tests passed in each environment, with identical test IDs and zero final failures/errors/skips. Actual source and installed-package verification each matched the same38 locked dependencies, source archive, project wheel and runtime identity.

The verifier checks archive bytes against uv.lock, installed files, interpreter and virtual-environment configuration, import origins and the source-only editable hook. It refuses unlisted modules, changed files, incorrect roots and exceeded bounds. Generated installation records are explicitly separate from original wheel evidence. Review defects were reproduced and repaired; retained failures remain available.

This establishes a bounded byte-verification component. It does not yet admit a clean campaign. The reviewed paired-input contract also preserves exact mathematical bytes and enforces shared hashes and distinct normalized environment paths. Next: bind immutable expectations to paired registration and native worker results, then finish M3 controls and run the full campaign.

Receipt: artifacts/m3/environment_manifest.json.
