# M0 native Windows acceptance - 9 October 2026

**ENGINEERING_FOUNDATIONS_READY: all 10 M0 gates verified.** STRATEGY_NOT_EVALUATED. PAPER_DISABLED. M1 has not started.

## Checkout and environment

- Checkout: `C:\Users\bgonn\Desktop\Compertum-development`
- Repository: https://github.com/BrennanCompertum/Compertum
- Branch: `local/m0-development`; published base: `cb0759e4bd9d28c6608bc3c5f9fb8da49e622781`.
- Implementation remains uncommitted/unpublished; base commit alone does not identify it. Source manifest SHA256: `635ed71cf096cdade2c2018ba596dae98c1eba4b195210ddc1f815b0625a3678`. Package SHA256: `ddab106f2695102d09f2f9b0a7758c52036a61db4cd673d7313ca1f878d97c49`; installed wheel matches.
- Windows 11 Home x64 build26300, Python3.14.7,39 locked distributions in two isolated environments. Third-party wheels only. No interpreter substitution, lock change, system installation or administrator changes.
- Qualification used the project's Python3.14.7 plus Strata's existing tokenizer/frontend tools read-only, including regex2026.9.10, Jinja2 3.1.6 and MarkupSafe3.0.3. These are external qualification-tool dependencies, not additions to the project lock or either environment. Locations are in `tokenizer-preparation.json`.
- `uv.lock`, BUILD_SPEC v1.1 and M0_IMPLEMENTATION_PLAN remain unchanged. Lock SHA256: `178974e50c154e7f424bbe94fc6656dbcebf379523358bde3aec794bfe649c53`.

## Commands and measured results

| Check | Pass / fail / skip |
| --- | --- |
| Full source pytest suite | 342 / 0 / 11,90.67s |
| `python -B tools/verify_native_ownership.py --suite all --run-fixtures` | 54 / 0 / 0 |
| Installed-wheel contract/configuration/persistence checks | 72 / 0 / 0 |
| Reporting repair regressions | 11 / 0 / 0 |
| Health compatibility repair, source and installed wheel | 26 / 0 / 0 in each environment |
| Current361 test-ID reconciliation | 350 unique passes,11 Windows-inapplicable skips |
| `python -B .cache/test-runs/m0-strata-20261009-01/run_six.py` | 6 / 0 / 0,7.10s total runner time |
| Live artifact/token/identity verification | All6 request/response pairs and reported token counts matched |

Source and installed-wheel `foundation check --suite m0 --offline` both exited0, produced complete separate-owner recovery manifests and identical29-byte artifact SHA256 `735c5148dc1073d5833c2e5911158205ef74706174656f54272e3b990e340ff4`. Actual non-sparse1GiB reserve allocation was measured. No required native gate was skipped.

The original aggregate verifier exited3 because live qualification was then unavailable; that receipt remains unchanged. The final acceptance combines that run with the tested reporting/health repairs and this fresh live qualification. No product source changed after the latest affected source/wheel checks, or during live qualification. Exact commands, exit codes and timings remain in both run directories' `commands.jsonl`.

## Live Strata qualification

The owner separately approved six model-only checks and startup of `D:\Strata\run-iq2_xs.bat` unchanged. Model `qwen3.8-flash-next-iq2_xs`, engine Strata0.1.40.2, configured context65536,one serving slot. Binary/model/tokenizer/template/config/expert-profile hashes retained; both weight shards were streamed in place without copying. The served template matches the recorded tokenizer template. Configuration/binary/tool hashes and weight sizes/mtimes were unchanged after the run. Strata remains running and idle.

| Check | Input tokens | Output tokens | Seconds | Result |
| --- | ---: | ---: | ---: | --- |
| json_object | 99 | 11 | 1.260 | PASS |
| math_domain | 117 | 11 | 0.721 | PASS |
| fictional_tool_proposal | 336 | 54 | 1.417 | PASS |
| second_turn_fixture_result | 190 | 7 | 0.746 | PASS |
| context_a | 92 | 8 | 0.564 | PASS |
| context_b | 92 | 8 | 0.577 | PASS |

Each request used temperature0,reasoning_effort=none,stream=false,at most16384 input/2048 output tokens and120seconds. Exact full-template counts matched measured server usage6/6. The adapter's native Job enforced1CPU,256MiB and one process/no children. Only synthetic inputs were sent; the fictional tool proposal had no real execution. Exact requests,responses,settings,latency and usage are retained under the fresh qualification project. No retries or additional inference requests were made.

## Gates and remaining capability limits

Verified: isolated environment; strict contracts/no-order capability; native ownership/roles; durable records/messages; native process/storage limits; recovery cannot unconsume; deterministic operation without AI; manual proposal bridge; bounded local qualification; independent scope/audit review.

Native Strata owned-request cancellation/timeout remains **UNVERIFIED**. Automatic local dispatch remains **false**, as Task8 requires when that separate capability is unavailable. Hosted subscription responses/usage were not observed; manual bridge acceptance does not claim hosted use. These limits are recorded, not marked passed.

## Preserved failures

The initial live preflight failed with `httpx.ConnectError: [WinError 10061]` because Strata was stopped. That attempt sent zero model requests. After separate startup approval, idle preflight and all six live checks passed. The failed preflight result/JUnit/logs remain beside the fresh live receipts.

Earlier native fixture races, persistent-consumption/compromise defects, grant/scan accounting, watchdog acceptance coverage and health metadata handling were repaired and retested. An earlier `HEALTH_UNVERIFIED` run used a retained `UNACCOUNTED_GROWTH` halted fixture; the halt was preserved and fresh accepted evidence used a separate fixture. Detailed red/green history and the previous report are retained under the paths below.

## Evidence and preservation

- Current acceptance: `artifacts/m0/acceptance.json`; local capability: `artifacts/m0/ai/strata_worker_v1.json`.
- Live evidence: `.cache/test-runs/m0-strata-20261009-01/`: `live-result.json`,`live-junit.xml`,`post-verification.json`,`identity-preparation.json`,`serving-after.json`,`independent-final-review.json`,per-request artifacts and `final-source.zip`.
- Full native/wheel run: `.cache/test-runs/m0-acceptance-d5fb0093-113d-43a1-9ff4-221e1801d492/`.
- Native ownership: `.cache/test-runs/native-verification-632b1a11-a1ee-429f-9294-4156192da954/`.
- Installation,repair and live command logs: `.cache/test-runs/m0-local-20261009-01/`.
- Earlier report snapshot: `.cache/test-runs/m0-strata-20261009-01/before-final-M0_ACCEPTANCE.md`.
- Independent reviews: `artifacts/m0/review.json`,health compatibility receipt and final live review.

Original `C:\Users\bgonn\Desktop\Compertum` source,history,runtime state and prior verification checkout were preserved. Original Git index SHA256 remains `46cf3ffa16ca521ec81c5f2816ffc77e6b6f096ca71d3e63c735afbd6edd0a0e`. Historical results and intentionally halted/compromised fixtures remain intact. No commits,pushes,merges,external publishing,spending,broker access,market data,protected evaluation,training,production workers or unattended services. Strata startup and its six requests were explicitly approved; its source,environment and configuration were not modified.

Project usage after qualification:4,446,211,480 bytes total,scratch4,444,256,864 bytes,below5GiB; scan2.713s. Do not allocate another full-reserve fixture without a fresh budget check. The small final source archive is additional retained evidence within the available margin.

Next milestone is M1; it is not started or authorized by this receipt.
