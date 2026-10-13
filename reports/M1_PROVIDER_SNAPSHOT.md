# Verified real-provider snapshot

All 13 symbols now have 252 warmup sessions and the required daily, entry-minute and closing-minute data for 43 sessions from 2 October to 30 November 2023. There are 9,906 raw/split observations and no gaps. The period includes the daylight-saving change and Thanksgiving early close.

The new reader retains original responses, exact prices, pagination lineage, receipt times and simulated historical availability separately. It rejects duplicates, mixed profiles, out-of-scope requests and protected dates. Actual historical receipt times remain unknown.

94 source tests and 94 installed-wheel tests passed; zero failures or skips. Both environments reproduced the exact 11,071,555-byte snapshot. Eight collection-safety checks passed; all 250 bounded HTTP requests succeeded. Independent review found no remaining material issue. Earlier source and evidence remain preserved.

This verifies the input reader and price coverage. It does not establish full M1, historical action completeness, actual broker fee billing, historical tradability or financial acceptance. Qualification and real replay are next.

Receipt: [provider_snapshot.json](../artifacts/m1/provider_snapshot.json). Checkpoint: [CURRENT_CHECKPOINT.md](../docs/CURRENT_CHECKPOINT.md).