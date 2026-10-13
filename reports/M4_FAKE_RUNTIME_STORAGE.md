# M4 fake runtime storage

11 October 2026. Verified local fake engineering component. Full M4 and financial acceptance remain incomplete.

194 identical checks passed in each source and installed environment, with zero failures, errors or skips. Each includes one full supervisor reconnect/restart test with an actual allocated 1 GiB reserve. Other checks cover first fake-broker/attempt writes, capacity refusal, interrupted/ignored writes, duplicate reservations, watchdog accounting, sealed inputs, recovery and operator controls. Independent review closed.

The coordinator now admits 287 exact runtime paths through one capacity scan and one atomic transaction. Fake broker database/WAL/SHM allowances are 2 MiB/8 MiB/64 KiB. Attempt identity/head receive 16 KiB each and each of 256 append files receives 64 KiB. Existing storage limits and watchdog rules are unchanged. A failed batch leaves no partial reservations; restart reuses exact matching rows.

Source archive SHA256: 89d0c3449262e09143d6119bc2107f0692f31ea70e0d020bfb38d402deb7f900. Wheel SHA256: fb2a022e95c3a6485f85d5149ec278a9ccba7ff3e09ebe2b7fe47a7550e30b98. All 134 installed Python files match the frozen source. Receipt: artifacts/m4/fake_runtime_storage.json. Test records: .cache/test-runs/m4-plan-storage-20261011-01 and m4-operator-native-20261011-01/operator-{source,wheel}03.*.

All passing disposable fixtures were archived and every byte verified before cleanup. The populated small namespace measured 63,921,824 bytes, below 64 MiB. Final scratch: 4,182,591,192 bytes; backups: 2,681,493,152 bytes; storage scan: 3.89 seconds. All category limits passed.

Next: fresh approval checks against an immutable reviewed plan, then execution-owned observations, saved approval/start and finite progression. No real broker, paper account or protected evaluation was used.