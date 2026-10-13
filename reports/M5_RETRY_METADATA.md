# Native retry timing observations

**588 matching source/package tests passed**, including 73 focused parser/native cases; zero failures, errors or skips. Independent review CLOSED 1/3. 176 installed modules match frozen source exactly.

Native responses now retain bounded normalized Retry-After timing before status rejection. The parser supports decimal seconds and all three HTTP date forms, validates UTC/calendar/weekday and the obsolete two-digit year rule, and anchors exact integer delays to receipt monotonic time. Duplicate, malformed and excessive values fail with static errors; native handles close. No automatic retry or deadline extension was added.

Eight local response cases replayed three times in each environment: 24 requests per lane and zero resends. Prior fresh/stale market results matched exactly before and after this change: three dates x three repeats, 18 local requests in each of three lanes. Real endpoints, account access and retry lifecycle remain unverified. Private transport metadata is not yet durable attempt evidence.

Two fixture issues were corrected without source/guard changes: a UTF-8 file-write failure, and a replay helper's relative root refused before any request. Original failures remain. Only two fully passed loose scratch trees were removed after exact archive verification; logs remain.

Final storage scan 4.743 seconds; namespace 7,638,909 bytes; peak 44,140,995 below 64 MiB. Available RAM 8,044,548,096 remains below M3's 8 GiB floor. No fresh full-owner reserve acceptance claimed.

Source `b040cf66d3d3e08d1055ee07be094db1790d90b1158fe4096c27073fc0e591d4`; wheel `712de23a7337b7e12c5895e5ec21ffe1b4b7baba57ed918c3ae5946c5167f307`. [Receipt](../artifacts/m5/retry_metadata.json); namespace `.cache/test-runs/m5-retry-metadata-20261012-01`.

Source contract: [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3) and [Microsoft SDK](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/um/winhttp.h). Neither establishes provider entitlement. Next: one execution-owner queue with independent service ceilings, reconciliation priority, single-use native dispatch permits and conservative restart accounting. Producer retries remain a subsequent lifecycle change.
