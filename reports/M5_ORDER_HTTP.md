# Native order transport

11 October 2026. Offline component verified with795matching source/package passes, zero final failures/errors and one inapplicable non-Windows skip per lane. Independent review closed1/3. All157installed Python modules match.

The private transport sends only validated whole-share day orders, individual cancellation requests, and order-ID/client-ID lookups. It shares the verified native GET lifecycle, keeps POST bytes alive through native handle closure, clears owned buffers after closure, uses a total deadline of at most10seconds and never retries. Local tests cover exact request bytes, malformed input, errors, redirects/authentication challenges, disconnect, timeout, cancellation and uncertain cleanup.204 is only a transport observation; no fill/cancellation/flat conclusion is inferred.

The existing full Windows account-read test passed in both environments after the shared lifecycle change. Separate processes used an actual allocated1GiB reserve and verified encrypted publication, a lost start reply without repeated reads, restart with zero new reads, and cancellation of a stalled request.

Source SHA256 db8ffa81d32df99af507e9e6d317023a3e1aeecc46600028e64a2b3e86adf33c. Wheel SHA256 3823de217d2e0d4a2b1b432160dfe415117fd29796e0884c9850e6c49628e75f. Exact test/archive/review hashes: artifacts/m5/order_http.json. Native test receipts: .cache/test-runs/m5-read-native-20261011-01/order-source01-command.json and order-wheel01-command.json.

Preserved failures: expected missing-module red test; pytest case names exceeding the Windows environment-string limit, repaired by short explicit case IDs; one storage inventory timeout. The completed generated scratch tree was losslessly archived and byte-verified before removing its duplicate. Original failure logs and receipts remain. Final storage scan4.8914826seconds; project14,025,609,688bytes, disk216,152,031,232bytes free. RAM8,165,912,576bytes remains below the8,589,934,592M3floor.

No real keys/account requests or actual paper TLS tests. No public write capability. Next required work is execution-private request/response qualification, then exact durable write authorization, ownership/risk/supervision and reconciliation.

Official contracts checked11October2026: [order submission](https://docs.alpaca.markets/us/reference/postorder), [individual cancellation](https://docs.alpaca.markets/us/reference/deleteorderbyorderid-1), [native buffer lifetime](https://learn.microsoft.com/en-us/windows/win32/api/winhttp/nf-winhttp-winhttpsendrequest).
