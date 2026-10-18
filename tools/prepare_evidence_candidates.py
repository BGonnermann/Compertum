"""Build disabled storage integration sources. Never execute or admit them."""
import hashlib
import json
from pathlib import Path

GUARD = "raise RuntimeError('PREPARATION_ONLY_FULL_SCAN_NOT_AUTHORIZED')"
ORIGINAL = "ROOT/'artifacts/m5/risk-dispatch-20261017-01'"


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('CANDIDATE_SOURCE_CHANGED: ' + old[:60])
    return source.replace(old, new)


def wrapper_candidate(source):
    if GUARD not in source.splitlines()[:2]:
        raise ValueError('PREPARATION_GUARD_REQUIRED')
    source = replace_once(source, 'OUT=Path(__file__).parent', 'OUT='+ORIGINAL)
    source = replace_once(source, 'name=sys.argv[1]', """sys.path.insert(0, str(ROOT/'tools'))
import evidence_folder as evidence
EVIDENCE=ROOT/evidence.NAMESPACE
proposal=json.loads((ROOT/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').read_text())
name=sys.argv[1]
kind=sys.argv[2]
bindings=evidence.output_bindings(proposal,kind,name)""")
    source = replace_once(source, 'bindings=evidence.output_bindings(proposal,kind,name)',
        "bindings=evidence.output_bindings(proposal,kind,name)\nif kind=='stage':bindings[name+'-clock.json']=4096")
    source = replace_once(source, "plan=json.loads((OUT/(name+'.job.json')).read_text())",
                          "plan=json.loads((EVIDENCE/(name+'.job.json')).read_text())")
    source = replace_once(source, "receipt=OUT/(name+'.closure.json')", "receipt=EVIDENCE/(name+'.closure.json')")
    # The plan is prepared before this process. Its bytes remain charged as existing evidence.
    source = replace_once(source, 'current_usage={}',
        "usage_roots=evidence.add_folder_check(usage_roots,ROOT)\ncurrent_usage={}")
    source = replace_once(source, '    original=scratch;amount=scratch_usage()',
        "    evidence.unused_allowance(values[-1])\n    original=scratch;amount=scratch_usage()")
    source = replace_once(source,
        "    journal=diagnostics.DiagnosticJournal(ROOT/'artifacts/m5/local-economics-20261017-01'/(name+'-parent-progress.jsonl'),monitor_poll)",
        """    output=evidence.EvidenceFolder(EVIDENCE,bindings,monitor_poll,
        writable={name+'-parent-progress.jsonl',name+'.closure.json'})
    journal=evidence.EvidenceJournal(output,name+'-parent-progress.jsonl',monitor_poll)""")
    source = replace_once(source, 'journal=None', 'journal=None\noutput=None')
    source = replace_once(source,
        "    with receipt.open('x') as stream:json.dump(record,stream,indent=2);stream.flush();os.fsync(stream.fileno())",
        """    if output is not None:
        output.save_closure(name+'.closure.json',record)
    else:
        record.update(status='FAILED',closure_unavailable=True)""")
    return source


def census_candidate(source):
    if GUARD not in source.splitlines()[:2]:
        raise ValueError('PREPARATION_GUARD_REQUIRED')
    source = replace_once(source,
        "sys.path.insert(0, str(Path(__file__).parent.parent/'storage-frame-reuse-20261015-13'))",
        "sys.path.insert(0, r'C:\\Users\\bgonn\\Desktop\\Compertum\\artifacts\\m5\\storage-frame-reuse-20261015-13')")
    source = replace_once(source, 'OUT=Path(__file__).parent',
        "OUT=M/'artifacts/m5/risk-dispatch-20261017-01'")
    source = replace_once(source,
        "    raw=(__import__('json').dumps(value,indent=2)+'\\n').encode();assert len(raw)<2*1024**2\n    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())",
        "    if value.get('status')=='FIRST_GATE_FAILED_STOP':output.save_failure(path.name,value)\n    else:output.save(path.name,value)")
    source = replace_once(source, 'extra_usage=dict.fromkeys(extra_prefixes,0)',
        "extra_prefixes['artifacts/m5/simulated-evidence-next-01']=8\nextra_usage=dict.fromkeys(extra_prefixes,0)")
    source = replace_once(source,
        "journal=diagnostics.DiagnosticJournal(L/(label+'-child-progress.jsonl'),deadline_poll)",
        """evidence=load('evidence_folder',M/'tools/evidence_folder.py')
EVIDENCE=M/evidence.NAMESPACE
bindings=evidence.output_bindings(read(M/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json'),'capacity',label)
output=evidence.EvidenceFolder(EVIDENCE,bindings,deadline_poll,writable={
    label+'-child-progress.jsonl',label+'-measurement.json',label+'-result.json',label+'-postresult-failure.json'})
journal=evidence.EvidenceJournal(output,label+'-child-progress.jsonl',deadline_poll)""")
    for suffix in ('-measurement.json', '-result.json', '-postresult-failure.json'):
        source = source.replace("OUT/(label+'"+suffix+"')", "EVIDENCE/(label+'"+suffix+"')")
    # The existing census loop adds limit minus actual usage to the records hold.
    # It already counts actual records during traversal. No old hold is reduced.
    return source


def fixture_candidate(source):
    """Bind fixture evidence without changing plans, clock rules, or identities."""
    source = replace_once(source, "ROOT=Path(__file__).parents[2];O=", "ROOT=Path(r'C:\\Users\\bgonn\\Desktop\\Compertum');O=")
    source = replace_once(source, 'def run_phase(phase):',
        """def run_phase(phase):
 import _prepared_evidence_context as context
 from evidence_capture import CapturedProcess
 output=context.output;destination=output.folder;name=context.name
 capture=None""")
    source = replace_once(source, "clock_path=O/(plan_path.stem+'-clock.json')", "clock_path=destination/(name+'-clock.json')")
    source = replace_once(source, "  with clock_path.open('x') as out:json.dump(frame,out,indent=2)",
        "  output.save(clock_path.name,frame)")
    source = replace_once(source,
        "receipt=O/(prefix+'-'+lane+'-'+phase.lower()+'-receipt.json');assert not receipt.exists()",
        "receipt=destination/(name+'-receipt.json');assert not receipt.exists()")
    source = replace_once(source,
        "token=str(uuid4());stdout=O/(token+'.supervisor.stdout');stderr=O/(token+'.supervisor.stderr')",
        "stdout=destination/(name+'-supervisor.stdout');stderr=destination/(name+'-supervisor.stderr')")
    source = replace_once(source,
        "  with stdout.open('xb') as out,stderr.open('xb') as err:",
        "  if True:")
    source = replace_once(source,
        "   process=subprocess.Popen(arguments,\n    executable=sys._base_executable,env=env,stdout=out,stderr=err,creationflags=0x08000000)",
        """   capture=CapturedProcess(arguments,output.open(stdout.name),output.open(stderr.name),output.poll,
    executable=sys._base_executable,env=env,creationflags=0x08000000)
   process=capture.process""")
    source = replace_once(source,
        "  driver.call('shutdown');process.wait(timeout=5);assert process.returncode==0 and stderr.read_bytes()==b''",
        "  driver.call('shutdown');process.wait(timeout=5);capture.finish();assert process.returncode==0 and stderr.read_bytes()==b''")
    source = replace_once(source, "  with receipt.open('x') as out:json.dump(record,out,indent=2)",
        """  if capture is not None:
   try:capture.finish()
   except BaseException as error:
    output.failed=True
    record.update(status='FAILED',output_error=str(error))
  if record['status']=='FAILED':output.save_failure(receipt.name,record)
  else:output.save(receipt.name,record)""")
    source = source.replace("O/plan['history_receipt']", "destination/context.receipts[plan['history_receipt']]")
    source = source.replace("O/plan['resting_receipt']", "destination/context.receipts[plan['resting_receipt']]")
    return '"""Disabled fixture copy. No broker stage is authorized."""\n'+GUARD+'\n'+source


def stage_candidate(source):
    source = replace_once(source, 'M=Path.cwd();L=Path(__file__).parent',
        "M=Path.cwd();L=M/'artifacts/m5/risk-dispatch-20261017-01'")
    source = replace_once(source, "assert sha(Path(__file__))==batch['runner_sha256']",
        "assert sha(L/'run_checks.py')==batch['runner_sha256']")
    source = replace_once(source, 'check()\nclass Inventory:', """check()
import builtins, time, types
from unittest.mock import patch
sys.path.insert(0,str(M/'tools'))
import evidence_folder as evidence
proposal=read(M/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json')
mapping=read(Path(__file__).with_name('output-bindings.json'))
name=mapping['stages'][label]['output_label']
bindings=evidence.output_bindings(proposal,'stage',name)
# Clock records consume 4096 bytes each from the 1 MiB preparation allowance.
bindings[name+'-clock.json']=4096
started=time.monotonic()
def output_poll():
 if time.monotonic()-started>=120:raise TimeoutError('JOB_DEADLINE')
owned={name+suffix for suffix in ('.xml','.log','-receipt.json','-supervisor.stderr','-supervisor.stdout','-clock.json')}
output=evidence.EvidenceFolder(M/evidence.NAMESPACE,bindings,output_poll,writable=owned)
sys.modules['_prepared_evidence_context']=types.SimpleNamespace(output=output,name=name,receipts=mapping['receipts'])
fixture=Path(__file__).with_name('test_dispatch_evidence_prepared.py')
original_ids=list(ids)
ids=[fixture.relative_to(M).as_posix()+'::'+item.split('::',1)[1] for item in ids]
xml=output.folder/(name+'.xml')
original_open=builtins.open
def bounded_open(file,mode='r',*args,**kwargs):
 if str(file)==str(xml) and mode in ('w','wb'):
  stream=output.open(xml.name)
  return stream if mode=='wb' else evidence.TextOutput(stream)
 return original_open(file,mode,*args,**kwargs)
class Inventory:""")
    source = replace_once(source,
        "with (L/(label+'.log')).open('x',encoding='utf-8') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):",
        "with evidence.TextOutput(output.open(name+'.log')) as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log),patch('builtins.open',bounded_open):")
    source = replace_once(source, "str(L/(label+'.xml'))", 'str(xml)')
    source = replace_once(source, 'check();sys.exit(code)', 'check();output.finish();sys.exit(code)')
    return '"""Disabled stage writer. No broker stage is authorized."""\n'+GUARD+'\n'+source


def admission_candidate(source):
    source=replace_once(source,'O = Path(__file__).parent',"O = M/'artifacts/m5/risk-dispatch-20261017-01'\nEVIDENCE=M/'artifacts/m5/simulated-evidence-next-01'")
    source=replace_once(source,
        "binding = read(O / 'simulated-resumption01-bindings.json')['bindings'][label]",
        """original_binding = read(O / 'simulated-resumption01-bindings.json')['bindings'][label]
mapping=read(Path(__file__).with_name('output-bindings.json'))['stages'][label]
assert mapping['original_binding']==original_binding
binding=dict(original_binding,stage_label=mapping['output_label'],capacity_label=mapping['capacity_label'])""")
    source=source.replace("O / (binding['capacity_label']", "EVIDENCE / (binding['capacity_label']")
    source=source.replace("O / (binding['stage_label']", "EVIDENCE / (binding['stage_label']")
    source=source.replace("str(O / 'run_checks.py')", "str(Path(__file__).with_name('run_stage_evidence_prepared.py'))")
    return '"""Disabled admission adapter. Keep all existing checks."""\n'+GUARD+'\n'+source


def build(root, destination):
    root, destination = Path(root), Path(destination)
    if destination.exists():
        raise FileExistsError('PRESERVE_PRIOR_CANDIDATES')
    originals = root/'artifacts/m5/risk-dispatch-20261017-01'
    sources = {
        'run_jobs08_prepared.py': ('run_jobs07_prepared.py', wrapper_candidate),
        'capacity_census_clock05_prepared.py': ('capacity_census_clock04_prepared.py', census_candidate),
    }
    prepared = {}
    pins = {}
    for target, (original, transform) in sources.items():
        raw = (originals/original).read_bytes()
        pins[original] = hashlib.sha256(raw).hexdigest()
        prepared[target] = transform(raw.decode('utf-8').replace('\r\n', '\n'))
        compile(prepared[target], target, 'exec')
    fixture = root/'tests/windows/test_paper_fixture_dispatch_control.py'
    raw = fixture.read_bytes()
    pins[str(fixture.relative_to(root))] = hashlib.sha256(raw).hexdigest()
    prepared['test_dispatch_evidence_prepared.py'] = fixture_candidate(raw.decode('utf-8').replace('\r\n', '\n'))
    compile(prepared['test_dispatch_evidence_prepared.py'], 'test_dispatch_evidence_prepared.py', 'exec')
    raw=(originals/'run_checks.py').read_bytes()
    pins['run_checks.py']=hashlib.sha256(raw).hexdigest()
    prepared['run_stage_evidence_prepared.py']=stage_candidate(raw.decode('utf-8').replace('\r\n','\n'))
    compile(prepared['run_stage_evidence_prepared.py'],'run_stage_evidence_prepared.py','exec')
    raw=(originals/'run_native_checks_resume01.py').read_bytes()
    pins['run_native_checks_resume01.py']=hashlib.sha256(raw).hexdigest()
    prepared['run_admitted_stage_prepared.py']=admission_candidate(raw.decode('utf-8').replace('\r\n','\n'))
    compile(prepared['run_admitted_stage_prepared.py'],'run_admitted_stage_prepared.py','exec')
    destination.mkdir()
    for name, source in prepared.items():
        (destination/name).write_text(source, encoding='utf-8')
    original_bindings=json.loads((originals/'simulated-resumption01-bindings.json').read_text())
    stages={label:dict(output_label='evidence01-'+label.removeprefix('simclock02-'),
        capacity_label=f'evidence01-capacity{number:02}', original_binding=binding)
        for number,(label,binding) in enumerate(original_bindings['bindings'].items(),1)}
    receipts={label+'-receipt.json':binding['output_label']+'-receipt.json' for label,binding in stages.items()}
    (destination/'output-bindings.json').write_text(json.dumps(dict(status='DISABLED',stages=stages,receipts=receipts),indent=2),encoding='utf-8')
    pins['simulated-resumption01-bindings.json']=hashlib.sha256((originals/'simulated-resumption01-bindings.json').read_bytes()).hexdigest()
    candidates={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.iterdir()}
    (destination/'inputs.json').write_text(json.dumps(dict(status='DISABLED', inputs=pins, candidates=candidates), indent=2), encoding='utf-8')
