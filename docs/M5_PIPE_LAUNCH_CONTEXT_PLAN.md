# Prepare the launch-context correction

Date: 18 October 2026.

## Accepted scope

Diagnose the missing AppContainer identity. Prepare and independently review the smallest correction.
Do not retry the experiment, run a full storage scan, or change permissions.
Do not change production code, frozen source bindings, identity evidence, or failed attempt records.
Keep Strata off. Keep new spending at zero.
Allow up to three review and document repair rounds. This does not reopen earlier preparation reviews.

- [x] Compare the active chat permissions with the saved defaults and historical token observation.
- [x] Trace the launch calls and locate the first identity check.
- [x] Prepare the exact session permission change and its verification conditions.
- [x] Obtain independent review and resolve any blocking finding.
- [x] Update the checkpoint, README, continuation instructions, and map inputs. Record final PDF verification in the completion receipt.
- [x] Prepare the approval request for delivery without applying it.

## Proposed smallest correction

Change only this chat's active permission selection from Full access to Ask for approval.
Use the app's permission control beneath the composer after owner approval.
The intended effective settings are:

```diff
- sandbox_mode = "danger-full-access"
- approval_policy = "never"
+ sandbox_mode = "workspace-write"
+ approval_policy = "on-request"
+ approvals_reviewer = "user"
```

This describes the active session change. It is not a patch to `config.toml`.
The saved defaults already specify `workspace-write` and `on-request`.
Keep the existing Windows sandbox implementation selection unchanged.
Do not install, recreate, or provision a sandbox. Stop if administrator setup is requested.
Do not add writable roots, change network rules, or change Windows access lists.
Do not add token impersonation or AppContainer creation to Compertum.

## Verification after approval

First confirm that the next turn reports the intended effective permission settings.
Then perform one bounded, query-only identity observation before considering another full storage check.
Use the existing `IdentityReader` checks for the process, its effective token, and its retained immediate parent.
Require AppContainer membership, integrity level 4096, and the exact previously reviewed user, logon, and application identities.
Record hashes and match results rather than raw identity strings.
Keep one CPU, 128 MiB, 16 processes, and the existing 120-second maintenance deadline.
Keep the 16 GiB starting memory floor and 12 GiB running stop floor.
Use fresh evidence names within the existing checked preparation allocation. Preserve the consumed experiment labels.
If any identity differs or cannot be read, stop. Do not replace the pinned identity or fall back to Full access.
Do not treat the permission selection alone as proof that the previous AppContainer identity has returned.

This verification creates no pipe and applies no access grant.
It performs no full storage scan, broker action, experiment retry, or production change.
Successful identity verification does not authorize those actions.

## Exact approval request

> Approve changing only this chat from Full access to Ask for approval, using workspace-write, on-request, and user review.
> Preserve the current Windows sandbox setup.
> Then perform one bounded query-only check against the pinned process, effective-token, and parent identities, with zero retries.
> Stop on any mismatch or setup request.
> Do not run a full storage scan, create a pipe, change a pipe grant, retry the experiment, or take broker actions.

The owner must select the permission mode in the app. No tool in this chat can apply that session selection.
The approval boundary comes from the owner's current instruction and `AGENTS.md` security-change rules.
