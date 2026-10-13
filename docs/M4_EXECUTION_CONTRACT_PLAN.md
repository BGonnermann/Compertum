# M4 execution contract increment

11 October 2026. Follows M4_FAKE_BROKER_ENGINEERING_PLAN.md and BUILD_SPEC sections13-14. Engineering uses invented deterministic fixtures only. No transport, credentials or broker account/order capability.

- [x] Immutable, strict execution intent/observation/decision/plan records, integrated with existing domain/schema conventions. Decimal strings and UTC event times; bounded symbols/orders/children. Schema validity never grants runtime authority.
- [x] Exact Decimal strategy admission: confirmed positions plus remaining open buys, no credit for unconfirmed sells, buffered cash, at-most60/20/40percent caps, six-submission limit and immutable strategy/authorization identities.
- [x] Separate authorized cancellation/long-close predicate under halt, retaining identity, reconciliation, durability, execution/watchdog, supervision, quote/calendar and finite-envelope gates.
- [x] Fixed close child planning (12children/10minutes/session close); explicit residual, downsizing only, no automatic continuation after uncertainty.
- [x] Focused negative checks, hand arithmetic, bounded independent review, source/package verification.
- [ ] Continue execution-owned persistence and separate fake-broker state through crash/reconciliation tests; integrate existing health/recovery owners.

Reuse simulation/policy.py fixed_decimal, number and buy_quantity. Do not reuse exposure_reason as paper admission: its historical halt threshold includes equality, while pretrade caps permit equality. Do not treat simulation Ledger.fill as broker reconciliation. Source/package freeze for current M3 must finish before product edits begin.

Assumptions fixed by specification: strategy buy cash/exposure uses ask times1.001times1.01 (base-cost case); close envelope uses ask times1.01, with bid as sell reference. Open-buy reservation covers only unfilled quantity; confirmed fills already reside in holdings/cash. No new numerical thresholds. Fixture account identity is explicitly fake; no environment-based broker routing.

Independent hand cases (NAV10000,ask100,mean daily dollar volume1000000 unless stated):

| Case | Expected |
| --- | --- |
| Empty portfolio buffered buy | 19shares,reserve1920.919;20cost2022.020 exceeds cap |
| Existing buy10,filled4,cash9600,remaining6 | Projected name1006.606;9more allowed gives1916.515;10gives2017.616 |
| Gross6000,pending sell2000,cash4000 | No additional buy capacity until sell confirmed; afterward19new shares allowed |
| Same-sector holdings3000 | 9new shares yields3909.909;10yields4011.010 and fails |
| Gross5900,new ask10 | 9shares yields5990.9909;10crosses gross cap |
| Daily loss exactly2percent / drawdown10percent | Halt at equality; no discretionary reset |
| Halted owned45shares | Children19,19,7;caps1919,1919,707;strategy submission count does not block authorized reduction |
| Child terminal fills7,19,7 | Sold33,residual12;cash8800;no extra child or enlargement |
| Child max19 repriced ask110 | Downsize to18;one share at ask2000 cannot fit2000cap |
| Owned229 at ask100 | 12children cover228;planned shortfall1;actual holdings remain229 before fills |
| First child accepted,reply lost,lookup404,deadline expires | One acceptance,same ID remainsUNKNOWN;unsubmitted children expire;possible residual26-45 until fills known |

Freshness refuses future timestamps as well as stale values. Quotes/reconciliation30seconds, clock difference5seconds, supervision300seconds, execution/watchdog heartbeat15seconds. Strategy window ends exclusively at09:36. Cancellation acceptance is never terminal cancellation; operation expiry does not erase accepted pending orders.

Next: after M3 frozen matrix, implement the immutable contracts and pure predicates with these exact fixtures. Persistent effects and full M4 acceptance remain separate required work.
