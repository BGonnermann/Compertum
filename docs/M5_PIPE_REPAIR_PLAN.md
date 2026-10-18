# Proposed Windows pipe repair

Status: preparation only. No permission change or native test is authorized by this document.

## Objective and stopping point

Prepare a narrow pipe repair and obtain independent review.
Keep runtime code and Windows permissions unchanged during preparation.
Do not run a full storage scan, clear saved stops, or take broker actions.
Keep Strata off. Preserve failed attempts and their original files.
Limit preparation to three review rounds. Record unresolved findings before stopping.

## What the evidence establishes

The isolated diagnostic runs inside AppContainer, a restricted Windows application environment.
Its user identity matches the intended operator. Its pipe access check and actual open both fail.
The current pipe grants user and logon identities, but no matching AppContainer identity.
The observed error is `CreateFileW:5`, meaning access denied.
The original failed supervisor token was not captured. These later observations cannot reconstruct that token.
Adding an application grant is a candidate repair, not a proved solution.
The pipe name and the object's integrity level can impose additional restrictions.

Microsoft describes separate user/group and AppContainer access checks in its [AppContainer access model](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer).
Microsoft also documents `LOCAL` pipe names and same-app restrictions for UWP processes in [CreateNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea).
These UWP rules do not establish this launcher’s complete behavior. Verify the actual process context before choosing its pipe name.
Microsoft warns that generic write rights include server-instance creation rights in [named-pipe security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights).

## Recommended repair design

Use an explicit, temporary test policy for one newly created pipe.
Do not change the default `pipe_security(operator_sid, logon_sid)` behavior.
Do not automatically add grants when Windows returns access denied.
Do not move execution outside the current sandbox to avoid its restrictions.
If the host policy forbids the proposed access, stop at that boundary.

The candidate policy adds only the observed, approved AppContainer identity to the existing protected access list.
An identity identifier is called a SID in Windows.
The added grant uses exactly `CLIENT_ACCESS = 0x00100083`.
It does not include generic write, full control, permission editing, ownership changes, or server-instance creation.
It does not grant Everyone, All Application Packages, or a shared capability group.
Existing user and logon grants remain unchanged.
Those grants are alternatives in the access list. The existing peer checks still enforce the expected user and logon together.

Read the identity from the retained process token, not a command line, environment variable, or guessed package name.
Read the effective thread token too. Refuse an unexplained difference from the process token.
Bind the approved policy to the process ID, creation time, user, logon, and exact application SID.
Refuse missing, malformed, changed, or unreadable identities.
Do not record capabilities, authentication material, or full token dumps.
Keep any necessary identity evidence private. Published reports use identity-match results and hashes.

Create the temporary pipe with the candidate descriptor from the start.
Do not edit an existing pipe, filesystem access list, registry key, application profile, or security label.
Keep remote-client rejection, first-instance protection, non-inherited server handles, and the existing client access mask.
Keep all message sizes, authentication, capability checks, process ownership, and cancellation rules.
Do not fall back to another name, token, access mask, or transport after failure.

## Patch specification for later implementation

| File | Prepared change | Required boundary |
| --- | --- | --- |
| `tools/diagnose_pipe_access.py` | Add bounded identity and pipe-name observations to a separate diagnostic candidate. | Preserve the original diagnostic and its results. Never change access rules. |
| New isolated test helper | Build a candidate descriptor from verified identity observations and explicit test authority. | No import-time Windows calls. No production entrypoint. |
| `src/compertum/runtime/_pipes.py` | Prepare an explicit policy parameter for future review, only after isolated proof. | Keep the default descriptor byte-for-byte unchanged. Do not apply this change now. |
| `src/compertum/runtime/bootstrap.py` and `owner_channel.py` | Trace private bootstrap and owner-channel creation before any integration. | Preserve inherited-handle lists and original-opener versus child identity checks. |
| `src/compertum/runtime/identity.py`, `_windows.py`, and `ipc.py` | Assess how application identity would join retained peer observations and registration. | Do not trust identity supplied by a client. Do not change persisted identities during preparation. |
| `tests/windows/test_ipc.py` | Add isolated access and peer-authentication cases after permission approval. | Do not run its existing permissive-descriptor fixture under this task. |

The first implementation belongs in the isolated helper, not the production pipe class.
Use synthetic identity strings for pure policy checks. They cannot prove Windows access behavior.
Do not treat successful descriptor formatting as successful pipe transport.
If native proof passes, prepare a separate production integration diff and review it before activation.

## Proposed verification sequence

1. Prepare pure policy checks for unchanged defaults, exact rights, explicit authority, and rejected invalid identities.
2. Inspect server and client identities under the intended launcher without changing permissions.
3. Record the OS version, application identity match, integrity levels, pipe name, and requested rights.
4. Before creating a pipe with different access rules, obtain explicit permission for the isolated experiment.
5. After approval, create one new temporary pipe with the reviewed descriptor.
6. Verify the applied access list and a bounded message exchange.
7. Verify refusal of the wrong application identity, wrong peer, changed creation time, and extra requested rights.
8. Verify remote rejection and server-instance denial independently of first-instance protection.
9. Verify timeout cancellation, observed child exit, and zero remaining children.
10. Preserve the result, including failure, and stop without a retry.

Steps requiring unavailable identities remain unverified. Do not simulate them and claim native security coverage.
A security change to build a negative-test fixture needs its own explicit scope.
The experiment must not start a Compertum owner, read a saved runtime, or call a broker.
If the access list passes but the actual open fails, record that distinction and stop.
Do not lower integrity labels or broaden rights to make the experiment pass.

## Bounds and evidence plan

Keep the existing 1 CPU, 128 MiB, 16-process, and 120-second maintenance limits.
Keep the 16 GiB start floor and 12 GiB stop floor for host memory.
Keep five-second pipe operation deadlines and the existing one-second cancellation completion limit.
Allow one native experiment and zero retries only after approval. No native experiment runs during preparation.
Keep C: at 50 GiB, records at 5 GiB, scratch at 15 GiB, and backups at 21 GiB.
Keep the separate D: archive allowance at 200 GiB. Do not use it as runtime space.

Use a new label and exclusive files for every later experiment.
Reserve named outputs before execution within the reviewed 8 MiB evidence folder.
Assign each output to an existing allowance. Reconcile actual use and remaining reservations before adding a test ledger.
Do not assume the forecast has space for extra experiments beyond its ten planned stages and ten capacity checks.
Do not borrow capacity from unrelated folders or unnamed reservations.
Record source hashes, bounds, parent closure, child result, exact errors, and applied-rule comparison.
Preserve diagnostic progress separately from acceptance evidence.
The earlier storage pass is historical and time-limited. Do not change its timestamp or reuse it as fresh admission.
If another full scan becomes necessary, stop for separate authority.

## Delivery strategy

First, prove the smallest isolated pipe case under reviewed, explicit permission.
Second, qualify negative cases and cancellation without starting project owners.
Third, review a production integration diff across public pipes, bootstrap pipes, and owner channels.
Fourth, qualify source and installed-package transport separately under unchanged limits.
Fifth, obtain any required fresh storage authority before the next simulated broker sequence.
Keep the original failed sequence closed. Use new attempt identities with references to its failure evidence.
Resume simulated stages only under their explicit authority and verified prerequisites.
Keep real-broker permissions, market windows, account checks, and action approvals separate.
Only then assess milestone acceptance against `docs/BUILD_SPEC.md`.

## Alternatives

Do not disable AppContainer or use administrator execution to bypass the restriction.
Do not replace pipes with files or sockets solely to avoid the access check.
Do not change every pipe name to `LOCAL` without proving the applicable Windows rule and reviewing identity changes.
Prefer the isolated exact-identity grant because it tests the observed missing permission with the smallest proposed access change.
If that design cannot satisfy host policy, report the unsupported execution context and propose a separately authorized deployment choice.

## Current verification

This is a design and test specification. No executable repair is installed.
No new source, installed-package, or native test result is claimed.
Independent review found no blocking design issue.
The review accepts preparation only. It does not establish a working pipe repair.
See `reports/M5_PIPE_REPAIR_REVIEW.md` for scope and remaining prerequisites.
