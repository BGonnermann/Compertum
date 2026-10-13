# Offline paper message contracts

11 October 2026. **193 identical source/package checks passed, zero failures/errors/skips.** Static review closed on pass2 of at most3. All144Python modules plus config/schema/lock files match the installed package. No M5 milestone or financial acceptance.

Two pure modules prepare immutable, canonical paper-only request fixtures and validate bound responses. Supported requests cover account, clock, calendar, individual/client-ID order lookup, submit and individual cancellation. Fixed routes reject live/altered endpoints. Bounded JSON rejects duplicate keys, malformed success fields, wrong identity, nonfinite financial strings and inconsistent order quantities/status. Raw bytes and their digest remain exact. No credentials, environment access, transport, account calls, dispatch or new dependency was added. Existing paper capabilities remain unavailable.

A cancel204 means only that the cancellation request was accepted. A timeout or404 remains unconfirmed and never grants retry permission. Caller-provided account context stays explicitly unverified. Provider clock/calendar shapes do not establish pinned-calendar agreement. The response age field measures creation-to-receipt time rather than network latency; normalized timestamps have microsecond precision and raw replies preserve original precision.

Review reproduced and fixed acceptance of malformed timezone offsets and fills in unrouted acknowledgement states. Five regression cases failed before correction. Explicit receipt and clock cases verify the shared correction. The old contract-test workspace now uses pytest's admitted temporary root; its assertions are unchanged. Failed attempts/logs remain retained. Passing disposable directories were archived before cleanup.

Source archive `ae530736fce05d3a8d0c02457a38bab3cd7e7eea8d1316bfb4c247b4ce2c1de0`; wheel `01193846c0f0c75317f0264b6cbf8b3c0bbdf1d392fb0569a04120a68677eb0b`. [Machine receipt](../artifacts/m5/paper_contracts.json). Test/command records: `.cache/test-runs/m5-paper-contracts-20261011-01`. Source/package equality and independent review establish this offline component only.

Next: finish offline walkthrough preparation in dependency order, then obtain the distinct account-read authority required by BUILD_SPEC before any actual account access. Each real broker write still needs a concrete reviewed plan. M3 full native campaign verification remains independently RAM-blocked; M6 still requires10actual supervised sessions.
