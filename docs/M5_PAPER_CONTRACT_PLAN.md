# Offline Paper Contracts Implementation Plan

> For agentic workers: primary executes the accepted autonomous plan; use superpowers:executing-plans. One independent reviewer at completion. The owner has selected continuous local execution; no commit, publishing or account action.

**Goal:** Validate and retain inert paper request/response fixtures while paper transport remains unavailable.

**Architecture:** Immutable canonical bytes bind identity and route. A separate response parser binds raw bytes to that request and returns engineering-only evidence. Existing fake execution and capabilities stay unchanged.

**Tech Stack:** Python3.14.7 standard library, existing canonical encoding/ContractError and pytest; no dependencies.

**Spec:** [M5_PAPER_CONTRACT_SPEC.md](M5_PAPER_CONTRACT_SPEC.md), BUILD_SPEC sections13â€“17 and M5_M6_PREPARATION.md.

## Constraints and review focus

$0; original checkout/Strata preserved; fresh checked test namespace; unchanged50GiB categories and native budgets. Never read credentials, contact an account, enable transport or publish. Three bounded review/repair passes. Test confusing URL spellings, bool/integer confusion, mutable caller dictionaries, malformed/deep/duplicate-key JSON, and ambiguous cancellation/lookup evidence.

## Tasks

- [x] Request records: create src/compertum/paper_contracts.py and tests/test_paper_contracts.py. Interface build_request(*,origin,account_alias,account_id,request_id,created_at,operation,parameters=None,body=None) -> PaperRequest, read_request(content:bytes) -> PaperRequest. PaperRequest.to_payload() returns an independent mapping. Fields/digests and exact routes are defined in the spec. First test must fail because this interface is absent; implement and run adversarial request checks.
- [x] Response records: create src/compertum/paper_responses.py and tests/test_paper_responses.py. Interface parse_response(request:PaperRequest,*,origin,account_id,status:int|None,raw:bytes,received_at:str) -> PaperResponse. PaperResponse retains raw:bytes, content:bytes and to_payload(). Validate supported success shapes, raw hash and request binding; errors/timeouts remain unconfirmed. Add failing tests first, then implement and verify. No event ledger or actual account observation is created.
- [x] Review and qualification: run both new suites plus tests/test_contracts.py and paper capability tests; inspect imports/no side effects. One bounded review, repair with regression evidence if needed. Freeze source, build/install offline, verify package bytes and identical source/wheel results. Save artifacts/m5/paper_contracts.json, reports/M5_PAPER_CONTRACTS.md, README and checkpoint with remaining authority/native gates.

Exact commands use the fresh namespace Invoke-Verification.ps1, .venv/Scripts/python.exe and the existing repro-env wheel interpreter: -B -m pytest tests/test_paper_contracts.py tests/test_paper_responses.py tests/test_contracts.py -q -p no:cacheprovider, fresh --basetemp and --junitxml. Passing means zero failures/errors/skips with expected tests collected and source/package IDs equal. Preserve failed evidence. Do not lower a limit or use source PYTHONPATH for wheel tests.

Next dependent offline tasks after this contract component: separate ENGINEERING_FIXTURE plan/authorization envelope; paper-response lifecycle rehearsal; walkthrough evidence packet/checker. Neither these nor M3 completion grant credential/account/order authority. Actual M5 and elapsed M6 gates remain.
