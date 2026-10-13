# Saved fake plan controls

Verified 11 October 2026: 285 matching source and installed-package passes, zero failures/errors/skips. This includes actual 1 GiB reserve, public named-pipe controls, lost approval reply, unchanged retry, checkpoint exclusion and restart invalidation in each environment. Independent review closed after three bounded passes.

Plans preserve their original observation. Approval and start use fresh execution-owned observations. Changed session, restart, halt or expired supervision permanently invalidate continuation. Starts have no broker effects.

Source archive SHA256: `08d02125dab20293d99617809fb3378f376d3eb534ccaec3cb72e4243dba581f`.
Wheel SHA256: `ea383b6c8ce7ee2662c463ad27bfe80f3ef4df7bfb77e7c06a6472c10a55690c`. All 136 installed Python files and config/schema/lock match. Detailed receipt: artifacts/m4/saved_plan_controls.json. Test records: K=.cache/test-runs/m4-saved-plan-controls-20261011-01 and G=.cache/test-runs/m4-operator-native-20261011-01.

The first native test failed because it expected public request IDs to survive a supervisor generation change. The corrected assertion requires REQUEST_CONFLICT and checks that the original execution receipt remains unchanged. The complete failed fixture is retained under backups/failed-fixtures-20261011-01 with K/failed-relocation01.json. Passing disposable fixtures were archived and every byte verified before removal.

Next: persist selected intents before finite simulated progression, then current-source recovery and resource-admitted numerical/campaign checks. Full M4, M5, M6 and financial acceptance remain incomplete.
