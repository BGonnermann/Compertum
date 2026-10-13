# Supervised saved replay controls

The foreground supervisor now operates existing saved synthetic runs through `baseline status`, `resume`, `step`, `pause` and `stop`, with `--run UUID`. Run creation uses the SavedRuns API. Each explicit step launches one fixed replay in a separate Windows Job. Restart leaves dispatch paused.

The worker inherits only the immutable input handle and the reserved output handle. It opens no shared database. The supervisor records attempts before launch, verifies whole-tree exit, checks the worker result's input/unit/hash binding, publishes the immutable output and accepts its checkpoint. Pauses and stops retain partial artifacts and attempt charges. Status reads compact ledger metadata without decoding the input bundle.

Limits remain four CPU threads, 4 GiB worker memory, 120 seconds per attempt, two attempts per replay and six replay units. The supervisor retains its 256 MiB limit. Per-output allowance is at most 16 MiB and cannot exceed TaskSpec; the existing run aggregate and project categories still apply. Heavy workers share one slot with foundation fixtures. No automatic continuation or retry occurs.

## Verification

Final native source checks: 23 passed. Installed-wheel native checks: 11 passed. No final failures or skips. All six replay records match exactly across environments. Fresh control timings and supervisor-crash receipts are retained beside JUnit and process logs.

Source and installed-wheel regression suites each passed 172 tests before the final native repairs. Those repairs changed only runtime/control.py, supervisor.py and _windows.py; final native checks revalidate those affected paths. Package identities and wheels remain recorded separately. Native final results, exact command lines, measured response times, environment identity and matching output hashes are retained in `artifacts/m1/supervised.json` and `.cache/test-runs/m1-supervised-20261009-01/`. Finalization requires passing native source/wheel JUnit and equality of all six replay records.

Native checks cover pause/resume/stop, restarting paused, killing an active supervisor and observing worker exit, recovery of the interrupted attempt, all six output comparisons, duplicate step requests, shared job slots, wrong-target stop, status polling without request-log growth, changed input refusal, output grants, process assignment and native memory/affinity/tree limits. Only bounded foreground fixtures are launched, with partial test recovery roots and no full 1 GiB reserve fixture.

Retained failures drove specific repairs: numerical imports exhausted the coordinator's memory allowance; an output grant could exceed its declared task budget; result acceptance needed an input/unit binding; status polling used effectful receipt capacity; targeted stop could leave another worker active. A legacy regression also preserved RUN_UNKNOWN precedence. The independent reviewer cleared the repairs; final tests establish their measured result.

Rapid polling then exposed native pipe disconnects at connection handoff. The client now reconnects with the same request ID, encoded command, peer identity and generation under the original five-second deadline. The supervisor tolerates disconnects, including a lost reply/ACK. Native fault tests prove one durable action across retry. Identity, malformed-message and cancellation-uncertainty failures still refuse. This repair received a separate bounded transport review.

A later startup encountered MoveFileExW access denial. A native test reproduced it with a reader temporarily withholding delete sharing. Metadata publication retries the same flushed staging file for at most one second on access/sharing conflicts. Persistent denial still refuses and preserves both old and incoming bytes; successful replacement retains exact-byte verification. A separate review confirmed no permission or ownership changes.

## Operator sequence

Use an existing run UUID created under the current source identity. With the foreground research supervisor running:

```powershell
compertum research resume
compertum baseline resume --run RUN_UUID
compertum baseline step --run RUN_UUID
compertum baseline status --run RUN_UUID
compertum baseline pause --run RUN_UUID
compertum baseline stop --run RUN_UUID
```

`step` returns after admission; status reports the accepted-unit count and artifact paths. Pause stops the active worker and preserves accepted earlier units. Stop is terminal. A changed source, interpreter, dependency lock or input identity requires a new run. Result files use a `.replay` identity header followed by canonical replay JSON; the body matches the pure simulator output. Earlier synchronous `.json` evidence remains untouched.

Checkout `C:\Users\bgonn\Desktop\Compertum-development`, repository `BrennanCompertum/Compertum`, branch `local/m0-development`, published base `cb0759e4bd9d28c6608bc3c5f9fb8da49e622781`. Changes remain uncommitted and unpublished. Python is 3.14.7 with the same 39 distinct distributions and unchanged lock; only the local wheel was rebuilt and installed offline.

Original project/runtime, earlier source archives and receipts are preserved. Prediction publication follows `docs/M1_PREDICTION_PUBLICATION_PLAN.md`. Operator creation/import and real-data acceptance remain separate work. No spending, Strata access, credentials, external data, trading, training, protected evaluation, publishing or unattended service occurred.
