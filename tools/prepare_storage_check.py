"""Prepare disabled copies of two retained maintenance programs.

This command writes source copies only. It cannot launch a storage census.
It refuses changed originals and existing destinations.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/m5/risk-dispatch-20261017-01'
DISABLED = ('"""Prepared source only. No full scan is authorized."""\n'
            "raise RuntimeError('PREPARATION_ONLY_FULL_SCAN_NOT_AUTHORIZED')\n")


def replace(source, old, new, count=1):
    assert source.count(old) == count, (old, source.count(old), count)
    return source.replace(old, new)


def original(name, pin):
    raw = (OUT / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin, name
    return raw.decode('utf-8')


def prepare(output_folder=OUT):
    census = original('capacity_census_clock03_candidate.py',
        '62b8770928773abf11a37d81be1498f5125a90e221f72d4cffd1d80c43543adc')
    wrapper = original('run_jobs06.py',
        '89362a5f6432c6c6e47d100757394d306dd31ba0f7660f135debb7a3e89364ad')
    census = replace(census, "from checked_common import M, OLD, PREV, archive, guard_module, load, read, sha",
        "from checked_common import M, OLD, PREV, archive, guard_module, load, read, sha\n"
        "diagnostics=load('prepared_storage_diagnostics',M/'tools/storage_check_diagnostics.py')")
    census = replace(census,
        "        for name,pin in current['files'].items():\n"
        "            if name in preserved.namelist():assert __import__('hashlib').sha256(preserved.read(name)).hexdigest()==pin,name",
        "        diagnostics.verify_archive_members(preserved,current['files'])")
    census = replace(census,
        "def poll():\n    guard.poll()\n    if time.monotonic()-started >= 110:\n        raise RuntimeError('CENSUS_110_SECOND_DEADLINE')",
        "def deadline_poll():\n"
        "    diagnostics.poll_deadline(started,110,guard.poll,error='CENSUS_110_SECOND_DEADLINE')\n\n"
        "journal=diagnostics.DiagnosticJournal(L/(label+'-child-progress.jsonl'),deadline_poll)\n"
        "next_progress=0.0\n"
        "def progress(force=False):\n"
        "    global next_progress\n"
        "    if force or time.monotonic()>=next_progress:\n"
        "        journal.emit(phase,anchor=started,elapsed=time.monotonic()-started,cpu=time.process_time()-process_started,\n"
        "                     metadata_calls=metadata_calls,metadata_seconds=metadata_seconds,counts=dict(counts))\n"
        "        next_progress=time.monotonic()+5\n\n"
        "def poll():\n    deadline_poll()\n    progress()")
    census = replace(census, "\n    verify_inputs();verify_release()",
        "\n    phase='verify_inputs_before';progress(True);verify_inputs()\n"
        "    phase='verify_release_before';progress(True);verify_release()", 1)
    # The later verification call has a different indentation level.
    census = replace(census, "        verify_inputs();verify_release()",
        "        phase='verify_inputs_after';progress(True);verify_inputs()\n"
        "        phase='verify_release_after';progress(True);verify_release()")
    census = replace(census, "    with ExitStack() as locks:",
        "    phase='preservation';progress(True)\n    with ExitStack() as locks:")
    census = replace(census, "phase='traversal';traversal_started=time.monotonic()",
        "phase='traversal';traversal_started=time.monotonic();progress(True)")
    census = replace(census, "        phase='ledgers';result['phase_timings']",
        "        phase='ledgers';progress(True);result['phase_timings']")
    census = replace(census, "        verify_cost_seal()\n        charged = capacity_gate(result)",
        "        phase='cost_seal_after';progress(True);verify_cost_seal()\n        charged = capacity_gate(result)")
    census = replace(census,
        "                            result['categories'][which] += value['charged'] + sum(row['charged'] for row in extra)",
        "                            entry_charge=diagnostics.observation_charge(value,extra)\n"
        "                            result['categories'][which] += entry_charge")
    census = census.replace("value['charged'] + sum(row['charged'] for row in extra)", 'entry_charge')
    census = census.replace("value['charged']+sum(row['charged'] for row in extra)", 'entry_charge')
    census = replace(census, '    poll()  # The retained directory locks have now also closed.',
        '    poll()  # The retained directory locks have now also closed.\n'
        '    journal.close()\n    deadline_poll()')
    census = census.rstrip() + '\nfinally:\n    if not journal.stream.closed:journal.close()\n'

    wrapper = replace(wrapper, "def monitor_poll():\n    guard.poll()\n    if time.monotonic()-started >= plan['seconds']:\n        raise RuntimeError('JOB_DEADLINE')",
        "diagnostics_spec=importlib.util.spec_from_file_location('prepared_diagnostics',ROOT/'tools/storage_check_diagnostics.py')\n"
        "diagnostics=importlib.util.module_from_spec(diagnostics_spec);diagnostics_spec.loader.exec_module(diagnostics)\n"
        "journal=None\n"
        "def monitor_poll():\n    diagnostics.poll_deadline(started,plan['seconds'],guard.poll)\n\n"
        "def progress(force=False):\n"
        "    journal.emit_progress(record['phase'],force=force,anchor=started,elapsed=time.monotonic()-started,cpu=time.process_time(),\n"
        "                 completed_counts=len(record.get('capacity_sample_seconds',[])),\n"
        "                 exit_code=record.get('exit_code'))")
    wrapper = replace(wrapper, "    sample_started=time.monotonic()\n    values=usage_module.namespace_usage",
        "    sample_started=time.monotonic()\n"
        "    record['active_capacity_sample']=dict(started_elapsed=sample_started-started,process_cpu_started=time.process_time())\n"
        "    progress()\n    values=usage_module.namespace_usage")
    wrapper = replace(wrapper,
        "    record.setdefault('capacity_sample_seconds',[]).append(time.monotonic()-sample_started)",
        "    record.setdefault('capacity_sample_seconds',[]).append(time.monotonic()-sample_started)\n"
        "    record.setdefault('capacity_process_cpu_seconds',[]).append(time.process_time()-record['active_capacity_sample']['process_cpu_started'])\n"
        "    record.pop('active_capacity_sample')\n    progress()")
    wrapper = replace(wrapper, "    guard.admit()\n    capacity();last_capacity=time.monotonic()",
        "    guard.admit()\n"
        "    journal=diagnostics.DiagnosticJournal(ROOT/'artifacts/m5/local-economics-20261017-01'/(name+'-parent-progress.jsonl'),monitor_poll)\n"
        "    record['phase']='initial_count'\n    capacity();last_capacity=time.monotonic()")
    wrapper = replace(wrapper, "    info=create_suspended(api,",
        "    record['phase']='child_setup';progress(True)\n    info=create_suspended(api,")
    wrapper = replace(wrapper, "    record['pid']=info.pid",
        "    record['pid']=info.pid\n    record['child_started_elapsed']=time.monotonic()-started\n"
        "    record['phase']='child_running';progress(True)")
    wrapper = replace(wrapper, "            capacity();last_capacity=time.monotonic()",
        "            record['phase']='periodic_count'\n            capacity();last_capacity=time.monotonic()")
    wrapper = replace(wrapper,
        "    capacity()\n    monitor_poll()\n"
        "    record.update(exit_code=code.value,status='PASSED' if code.value==0 else 'FAILED',peak_memory_bytes=api.limits(job).peak_job_memory)",
        "    record['exit_code']=code.value\n    record['child_exit_elapsed']=time.monotonic()-started\n"
        "    record['phase']='final_count';progress(True)\n"
        "    diagnostics.finish_child(record,code.value,capacity,monitor_poll)\n"
        "    record['peak_memory_bytes']=api.limits(job).peak_job_memory")
    wrapper = replace(wrapper, "    record['remaining_children']=api.active(job)",
        "    record['remaining_children']=api.active(job)\n"
        "    if journal is not None:diagnostics.close_diagnostics(record,journal)")
    targets = [(output_folder/'capacity_census_clock04_prepared.py', DISABLED+census),
               (output_folder/'run_jobs07_prepared.py', DISABLED+wrapper)]
    assert all(not path.exists() for path, _ in targets), 'PRESERVE_PREPARED_CANDIDATES'
    for path, source in targets:
        compile(source, str(path), 'exec')
    for path, source in targets:
        with path.open('xb') as stream:
            stream.write(source.encode())


if __name__ == '__main__':
    prepare()
