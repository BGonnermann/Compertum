"""Verify saved storage-preparation evidence and calculate a review-only budget.

This tool cannot archive, remove, grant storage, start a runtime or change limits.
Run with -B. Outputs may be created only beneath master/artifacts/m5.
"""
if not __debug__:
    raise RuntimeError("OPTIMIZED_PYTHON_DENIED")
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import time

GIB=1024**3
MIB=1024**2
CAPS={"backups":20*GIB,"scratch":5*GIB,"records":5*GIB,"data":15*GIB,"models":5*GIB}
ROOTS=(
    ".cache/test-runs/m3-pair-validation-repair-20261013-01/source_native01-pytest",
    ".cache/test-runs/m3-review-health-20261013-01/installed_native11_r2-pytest",
    ".cache/test-runs/m3-review-health-20261013-01/source_native11_r2-pytest",
    ".cache/test-runs/m3-pair-validation-repair-20261013-01/source_green01-pytest",
)
ROOT_CAPS=(917504,163840,163840,65536)
BACKUP_MAXIMUM=1572864
EXECUTION_RECORDS_MAXIMUM=16*MIB
PUBLICATION_RECORDS_MAXIMUM=2*MIB
DOCUMENT_UPDATES={"docs/CURRENT_CHECKPOINT.md","docs/FIXTURE_CONSOLIDATION_PLAN.md","docs/FIXTURE_CONSOLIDATION_GATES.md"}


def review_budget(capacity, measurements):
    """Count every simultaneous allowance before crediting any removal."""
    assert tuple(row["root"] for row in measurements)==ROOTS
    assert tuple(row["combined_physical_cap"] for row in measurements)==ROOT_CAPS
    assert sum(ROOT_CAPS)+131072+131072==BACKUP_MAXIMUM
    assert capacity["probe_growth_hold_bytes"]==8*MIB
    assert capacity["outstanding_conservative_bytes"]["records"]>=8*MIB
    before={key:capacity["categories"][key]+capacity["outstanding_conservative_bytes"][key] for key in CAPS}
    during=dict(before)
    during["backups"]+=BACKUP_MAXIMUM
    during["records"]+=EXECUTION_RECORDS_MAXIMUM+PUBLICATION_RECORDS_MAXIMUM
    remaining={key:CAPS[key]-during[key] for key in CAPS}
    free_after=capacity["free_bytes"]-8*MIB-BACKUP_MAXIMUM-EXECUTION_RECORDS_MAXIMUM-PUBLICATION_RECORDS_MAXIMUM
    reasons=[]
    if not capacity["capacity_qualified"] or capacity["barriers"] or capacity["unknown_streams"] or capacity["ledger_failures"]:
        reasons.append("INCOMPLETE_MEASUREMENTS")
    reasons += ["CATEGORY_CAPACITY:"+key for key in CAPS if key!="scratch" and remaining[key]<0]
    if sum(during.values())>50*GIB:reasons.append("TOTAL_CAPACITY")
    if free_after<50*GIB:reasons.append("FREE_SPACE_FLOOR")
    for row in measurements:
        if row["rounded_stream_allocation"]>row["combined_physical_cap"]:
            reasons.append("ROOT_ARCHIVE_CAP:"+row["root"])
    file_release=sum(row["conservative_file_release_bytes"] for row in measurements)
    return dict(
        status="REVIEWABLE_WITH_EXPLICIT_NO_SCRATCH_GROWTH_EXCEPTION" if not reasons else "PREPARATION_BLOCKED",
        refusal_reasons=reasons,
        snapshot_categories=capacity["categories"],
        snapshot_pending=capacity["outstanding_conservative_bytes"],
        simultaneous_charges=during,
        remaining_after_all_proposed_growth=remaining,
        backup_maximum_bytes=BACKUP_MAXIMUM,
        preparation_records_hold_bytes=8*MIB,
        publication_records_maximum_bytes=PUBLICATION_RECORDS_MAXIMUM,
        execution_records_maximum_bytes=EXECUTION_RECORDS_MAXIMUM,
        future_scratch_growth_bytes=0,
        starting_scratch_overage_bytes=max(0,before["scratch"]-CAPS["scratch"]),
        conservative_file_release_after_approved_removal=file_release,
        estimated_scratch_remainder_after_approved_file_removal=CAPS["scratch"]-(during["scratch"]-file_release),
        removal_credit_used_for_starting_admission=False,
        free_bytes_after_all_proposed_growth=free_after,
        free_space_floor_bytes=50*GIB,
        total_remaining_after_all_proposed_growth=50*GIB-sum(during.values()),
        maintenance_exception_approved=False,
        execution_authorized=False,
        removal_authorized=False,
        production_admission=False,
    )


def self_check():
    rows=[dict(root=root,combined_physical_cap=cap,rounded_stream_allocation=cap,conservative_file_release_bytes=1000000) for root,cap in zip(ROOTS,ROOT_CAPS,strict=True)]
    seed=dict(categories=dict.fromkeys(CAPS,0),outstanding_conservative_bytes=dict.fromkeys(CAPS,0),capacity_qualified=True,barriers=[],unknown_streams=[],ledger_failures=[],probe_growth_hold_bytes=8*MIB,free_bytes=100*GIB)
    seed["categories"]["scratch"]=CAPS["scratch"]+310888
    seed["categories"]["backups"]=CAPS["backups"]-BACKUP_MAXIMUM
    seed["outstanding_conservative_bytes"]["records"]=8*MIB
    result=review_budget(seed,rows)
    assert not result["refusal_reasons"] and result["remaining_after_all_proposed_growth"]["backups"]==0
    assert result["starting_scratch_overage_bytes"]==310888 and not result["removal_credit_used_for_starting_admission"]
    cases=1
    for change,reason in ((lambda x:x["categories"].__setitem__("backups",x["categories"]["backups"]+1),"CATEGORY_CAPACITY:backups"),(lambda x:x["outstanding_conservative_bytes"].__setitem__("backups",4096),"CATEGORY_CAPACITY:backups"),(lambda x:x.__setitem__("free_bytes",50*GIB+8*MIB+BACKUP_MAXIMUM+EXECUTION_RECORDS_MAXIMUM+PUBLICATION_RECORDS_MAXIMUM-1),"FREE_SPACE_FLOOR"),(lambda x:x.__setitem__("capacity_qualified",False),"INCOMPLETE_MEASUREMENTS"),(lambda x:x["categories"].__setitem__("records",CAPS["records"]-8*MIB-EXECUTION_RECORDS_MAXIMUM-PUBLICATION_RECORDS_MAXIMUM+1),"CATEGORY_CAPACITY:records")):
        sample=copy.deepcopy(seed)
        change(sample)
        assert reason in review_budget(sample,rows)["refusal_reasons"]
        cases+=1
    return dict(in_memory_budget_checks_passed=cases,failed=0,skipped=0,product_tests_run=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--evidence-dir",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--self-check",action="store_true")
    args=parser.parse_args()
    if args.self_check:
        print(json.dumps(self_check()))
        return
    if args.evidence_dir is None:parser.error("--evidence-dir is required")
    root=args.project_root.resolve(strict=True)
    evidence=args.evidence_dir.resolve(strict=True)
    assert evidence.is_relative_to(root/"artifacts/m5")
    started=time.monotonic()

    def poll():
        if time.monotonic()-started>10:raise RuntimeError("PREPARATION_VERIFICATION_DEADLINE")

    def sha(path):
        digest=hashlib.sha256()
        with path.open("rb") as source:
            while data:=source.read(1024**2):
                poll()
                digest.update(data)
        return digest.hexdigest()

    def read(path):
        poll()
        return json.loads(path.read_bytes())

    launch_review=read(evidence/"prelaunch-review03.json")
    assert launch_review["round"]==3 and launch_review["result"]=="CLEAR_FOR_BOUNDED_READ_ONLY_PREPARATION"
    for name,pin in launch_review["files"].items():assert sha(evidence/name)==pin,name
    inputs=read(evidence/"inspection-inputs.json")
    assert len(inputs)==463
    drift=[]
    for name,pin in inputs.items():
        if sha(root/name)!=pin:
            assert name in DOCUMENT_UPDATES,name
            drift.append(name)
    assert sum(name.startswith("src/compertum/") for name in inputs)==217
    assert sum(name.startswith(".venv/Lib/site-packages/compertum/") for name in inputs)==217
    command=read(evidence/"inspection-command.json")
    assert command["status"]=="READ_ONLY_PLANNING_JOB_CLOSED" and command["exit_code"]==0
    assert command["process_exit_observed"] and command["active_processes_after_cleanup"]==0
    assert command["elapsed_seconds"]<=75 and command["peak_job_memory"]<=128*MIB
    assert command["native_cpu_count"]==1 and command["growth_allowance_bytes"]==8*MIB
    metadata=read(evidence/"gate-metadata.json")
    capacity=read(evidence/"gate-capacity.json")
    links=read(evidence/"gate-links.json")
    assert metadata["metadata_entries"]==1827
    assert tuple(group["root"] for group in metadata["groups"])==ROOTS
    assert sum(row["files"] for row in metadata["measurements"])==1098
    assert sum(row["directories"] for row in metadata["measurements"])==718
    assert sum(row["links"] for row in metadata["measurements"])==11
    assert not links["incoming"] and not links["unresolved"] and not links["barriers"]
    assert len(links["links"])==1638
    assert len(capacity["ledgers"])==1 and capacity["ledgers"][0]["path"]=="state/research.sqlite"
    for ledger in capacity["ledgers"]:assert sha(root/ledger["path"])==ledger["sha256"]
    reserve=capacity["execution_reserve_observation"]
    assert reserve["size"]==GIB and reserve["allocation"]>=GIB and not reserve["attributes"]&0x4A00
    original=root/".cache/test-runs/m5-fixture-consolidation-plan-20261015-01"
    historical=read(original/"plan-evidence.json")
    assert len(historical["groups"])==65 and len(historical["receipt_pins"])==112
    for group in historical["groups"]:assert sha(original/group["manifest"])==group["manifest_sha256"]
    for name,pin in historical["receipt_pins"].items():assert sha(root/name)==pin,name
    result=review_budget(capacity,metadata["measurements"])
    result.update(metadata_entries=1827,source_files_matched=217,installed_files_matched=217,frozen_inputs_checked=463,authorized_document_drift=sorted(drift),original_reports_matched=65,original_receipt_pins_matched=112,retained_links_checked=1638,incoming_links_inside_master=0,outside_master_incoming_links="UNPROVEN_REQUIRES_EXPLICIT_REMOVAL_REVIEW",reservation_rows=sum(len(ledger["reservations"]) for ledger in capacity["ledgers"]),measured_compressed_bytes=sum(row["combined_compressed_bytes"] for row in metadata["measurements"]),rounded_archive_stream_bytes=sum(row["rounded_stream_allocation"] for row in metadata["measurements"]),measurements=metadata["measurements"],job_elapsed_seconds=command["elapsed_seconds"],job_peak_memory_bytes=command["peak_job_memory"],product_tests_passed=0,product_tests_failed=0,product_tests_skipped=0,archives_written=0,files_removed=0,scanner_rounds_used=12,tool_sha256=sha(Path(__file__)),evidence={name:sha(evidence/name) for name in ("inspection-inputs.json","inspection-command.json","gate-metadata.json","gate-capacity.json","gate-links.json","gate-summary.json","owner-preservation-choice.json","task-contract.md")})
    if args.output is not None:
        output=args.output.absolute()
        assert output.parent.resolve(strict=True).is_relative_to(root/"artifacts/m5")
        raw=(json.dumps(result,indent=2,sort_keys=True)+"\n").encode()
        assert len(raw)<32768
        with output.open("xb") as sink:
            assert sink.write(raw)==len(raw)
            sink.flush()
            os.fsync(sink.fileno())
    print(json.dumps({key:value for key,value in result.items() if key not in ("evidence","measurements")}))
    if result["refusal_reasons"]:raise SystemExit(1)


if __name__=="__main__":
    main()
