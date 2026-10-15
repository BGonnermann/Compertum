# Native storage scanner verification

14 October 2026. Owner approved native-reader rounds 4–6 using existing GCC, with no installation or spending. Original Python rounds 1–3 remain used and preserved.

The scanner keeps every path and native AllocationSize charge. A small C adapter combines checked directory opening and 64KiB native reads. Python retains traversal, category accounting, link validation, caller-thread volume probes and the five-second deadline including closure. No cached inventory, excluded path or resource-limit increase.

The DLL loader verifies a manifest hash anchored in Python code, rejects linked DLLs, locks files through verification/loading, restricts dependency search and compares the loaded file's volume/file identity. Runtime/recovery Python hashes therefore bind the native payload. Wheels carry 214 Python modules plus C source, manifest and DLL, with the `py3-none-win_amd64` platform tag. The DLL is ignored local build output; the builder, C source and manifest are published.

## Verified results

- 43 identical source/installed case IDs passed; zero failures, errors or skips. Each ran in a closed native four-CPU/4GiB/120-second Job with the unchanged 128MiB test namespace. Child jobs are capped; parent admission is not affinity capped.
- 18 compiled C boundary cases passed against the final C source. These cover opening, inherited handles, attribute query failure, directory/reparse rejection, query status/size, EOF and checked close failures.
- Offline wheel build and project-only installation passed. Python 3.14.7 and all 38 dependencies stayed unchanged. Complete source and installed environment byte checks passed.
- Three full-master scans passed in actual one-CPU128MiB Jobs: 4.5656359 seconds / 112,795 files;4.9476213 seconds / 115,052 files;4.9298646 seconds / 115,059 files. The last invokes the original watchdog volume callback. All eight component jobs and the separate aggregate audit closed with zero active children.
- The 576-file source archive, 217 package payload files, exact test inventories, environment proofs and 326 evidence pins passed aggregate verification. No actual managed session was started on master. The managed watchdog fixture checks remain separate from these full-master scan measurements.

Local aggregate: `artifacts/m5/native_storage_pair_verified.json`, SHA `eb08494998a4dcd395c08e6a0423f790d76a3a7b0ab4c3ea7b8de36e61e4c58e`.

Source archive SHA `6273bff6b4d29c0b4e22de32bb9e5652af3425ac5c70013019ebabf8646555cf`; wheel SHA `1b4f48710b0e3b337f7c9ba45b198d632238725fee8ba9993cfa31e171a56199`; C SHA `8cc036f4e2282a84fda138b76fed589d207236dad8bdd594b57245f9a2562478`; DLL SHA `78e69409c1064da95f82efafe0fd470bf021913a028a7f1afbf7f051c51c5d62`.

## Failed evidence retained

Earlier Python/full-master refusals and native variants remain. Review 4 found a DLL-reparse lock gap; its red case reproduced it. Review 5 cleared the file-identity repair. Fixture rename collisions and a Windows path-prefix comparison failure were repaired without weakening checks. The next source 43 attempt refused its full-master admission scan before creating a child. Offline measurements found queued native readers slower; the final C adapter requests only the attributes needed for the same directory/reparse checks.

Two direct-script environment checks refused because the helper itself appeared outside the frozen environment. They briefly overlapped and are not accepted evidence. Corrected inline invocations ran serially and passed the complete unchanged checks. Failed receipts, prelaunch hash/capacity refusals and all failed fixture roots remain. No cleanup occurred in this scanner increment.

Final independent review 6 is CLEAR. The timing margin is narrow: preserve closed passing scratch before substantial fixture growth, then measure the changed tree. Limits remain five seconds, one CPU/128MiB for the watchdog, 50GiB total and unchanged category caps.

Original intent release 18 remains separately verified at 393 matching cases per environment, including all 106 formerly pending installed cases. Its original wheel/source and historical audit remain preserved. The native scanner is a new release identity. Neither result accepts M5 financially or reopens the terminal M3 audit; M6 remains 0/10 actual sessions.

Exact next action: publish/synchronize this cleared checkpoint, preserve and byte-verify passed disposable fixtures, then continue native ownership/accounting under the approved admission plan. Keep Strata off and actual broker actions outside this local implementation scope.
