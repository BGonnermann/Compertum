"""Prepare a disabled adaptation of the existing bounded maintenance wrapper."""
import hashlib

ORIGINAL_SHA256 = 'b7abaca696db3061c0735af967b722105d1c791d0042aaa3014db04cf661a446'
GUARD = "raise RuntimeError('PREPARATION_ONLY_NATIVE_EXECUTION_DISABLED')"


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('LAUNCHER_SOURCE_CHANGED')
    return source.replace(old, new)


def prepare_launcher(raw):
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('LAUNCHER_HASH_CHANGED')
    source = raw.decode('utf-8')
    source = replace_once(source, 'name=sys.argv[1]', """name=sys.argv[1]
if name != 'pipe-isolated01':raise RuntimeError('EXPERIMENT_LABEL_DENIED')
sys.path.insert(0,str(ROOT/'tools'))
from pipe_experiment_evidence import ExperimentEvidence
from prepare_pipe_experiment import BOUNDS
EVIDENCE=ROOT/'artifacts/m5/simulated-evidence-next-01'""")
    source = replace_once(source,
        "plan=json.loads((ROOT/'artifacts/m5/local-economics-20261017-01'/(name+'.job.json')).read_text())",
        "plan_path=EVIDENCE/(name+'.plan.json')\nplan=json.loads(plan_path.read_text())")
    source = replace_once(source,
        "receipt=ROOT/'artifacts/m5/local-economics-20261017-01'/(name+'.closure.json')",
        "receipt=EVIDENCE/(name+'.closure.json')")
    source = replace_once(source, 'process=thread=None;assigned=False',
        "process=thread=None;assigned=False\noutput=None")
    source = replace_once(source, 'current_usage={}',
        "usage_roots.append(EVIDENCE)\nassert len(usage_roots)==29\ncurrent_usage={}")
    source = replace_once(source, '    original=scratch;amount=scratch_usage()',
        "    if values[-1]>8388608:raise RuntimeError('EVIDENCE_FOLDER_LIMIT')\n    original=scratch;amount=scratch_usage()")
    source = replace_once(source, '    guard.admit()\n    capacity();last_capacity=time.monotonic()',
        """    guard.admit()
    capacity();last_capacity=time.monotonic()
    output=ExperimentEvidence(ROOT,plan_path,plan,monitor_poll)
    output.validate_activation()
    if (plan['cpus'],plan['memory_mib'],plan['seconds']) != (1,128,120):
        raise RuntimeError('EXPERIMENT_LIMITS_CHANGED')""")
    source = replace_once(source, '    guard.poll()',
        "    guard.poll()\n    if output is not None:output.check_inputs(throttled=True)")
    source = replace_once(source,
        "    with receipt.open('x') as stream:json.dump(record,stream,indent=2);stream.flush();os.fsync(stream.fileno())",
        """    if output is not None:
        output.save_closure(record)
    else:
        record.update(status='FAILED',closure_unavailable=True)""")
    return GUARD + '\n' + source
