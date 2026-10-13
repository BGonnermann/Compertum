# Durable paper preparation consumption

Verified offline,11 October2026: **1,323matching source/installed-package passes**, zero final failures or errors. One non-Windows refusal test per lane is inapplicable and excluded. Independent review closed3/3. Receipt: artifacts/m5/paper_consumption.json.

Paper preparations now use the existing native execution database, intent/event tables and attempt history. Stable client identity, strict immutable request bindings and a separate PAPER_PREPARATION scope prevent fake records from being treated as paper records. Legacy fake records and event bytes remain readable. The shared limits remain256intents/attempts,512events,64KiBrecords and16MiBSQLite.

Consumption writes a create-only external event and durable history head before the SQLite transaction. A crash leaves a consumed intent or blocks on incomplete evidence. Restoring an older database cannot grant a second first consumption while surviving attempt evidence is intact. Consumed preparations remain inert: they confer no transport authority, grant, financial acceptance or broker outcome.

| Verification group | Source | Installed |
| --- | ---: | ---: |
| Paper/native boundary regressions |856|856|
| Shared journal and snapshot recovery |108|108|
| Fake economics and observations |107|107|
| Fake risk and approval controls |188|188|
| Fake operation/restart progression |56|56|
| Full native reserve/crash/restore/read |8|8|
| Total applicable passes |1323|1323|

Native evidence uses the actual1GiB non-sparse reserve and separate Windows processes. It covers termination before consumption, after identity upgrade, before/after external-head publication and after SQLite commit; repeated restoration of an older multi-database/message/artifact backup; existing fake-operation recovery; and the full read/publication/restart/cancel flow. A deliberately blocked fixture also proves bounded process cleanup and owner reacquisition. No real credentials or external account requests were used.

Review reproduced and repaired native reserve type/lease substitution, mixed paper history entering fake economics/pending-work counts, and a Windows fixture-launcher timeout risk. Initial failures remain saved. A full-root storage admission hit the unchanged5second deadline; two older generated failure fixtures were archived and byte-verified before duplicate removal. Their original failure logs remain.

The installed legacy read test initially exposed a fixture startup race. Waiting for existing mutual-health proof fixed the test; both native reruns passed. Product bytes and other test inputs were unchanged, so their earlier results remain applicable. The failed run is preserved.

Source archive: `a6dd895afa40a3be603c830c0d4586324ece1d882955495c26785f65f5138b58`. Wheel: `b8857a07e4a633ec0e9c560cf1ccec2a170e61aaadf24a2a4a7ebc0f55cf1c17`. All161installed Python modules match the frozen source exactly. Latest available RAM: 8191918080bytes; M3 requires8589934592bytes. Storage observation: OBSERVED_WITHIN_DEADLINE.

Actual M5 is still pending. Next work connects exact grants, fresh risk/ownership inputs, supervision, transport and bounded incident reconciliation, and builds the independent M6 evidence checker. A coordinated replacement of every retained local evidence source remains undetectable locally. Ten actual supervised market sessions and252strategy-forward sessions remain separate elapsed requirements.
