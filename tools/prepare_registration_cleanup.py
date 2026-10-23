"""Instantiate the reviewed cleanup script for one completed registration test job."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LABELS = ('ai-registration-tests04', 'ai-registration-tests05', 'ai-registration-tests06')


def prepare(label):
    if label not in LABELS:
        raise ValueError('LABEL_DENIED')
    evidence = ROOT/'artifacts/ai/history-verification-20261019-01'
    closed = json.loads((evidence/(label+'.closure.json')).read_text())
    if (closed['status'] != 'PASSED' or closed['exit_code'] != 0
            or closed['exit_observed'] is not True or closed['remaining_children'] != 0):
        raise ValueError('JOB_DID_NOT_PASS')
    xml = ET.parse(evidence/(label+'-results.xml'))
    count = len(xml.findall('.//testcase'))
    if not count or any(xml.findall('.//'+name) for name in ('failure', 'error', 'skipped')):
        raise ValueError('TEST_RESULTS_DID_NOT_PASS')
    source = (ROOT/'tools/Remove-CompletedTestFiles.ps1').read_text()
    source = source.replace("$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))",
                            "$root = '"+str(ROOT).replace("'", "''")+"'")
    source = source.replace("$record = Join-Path $parent 'test-retention01'",
                            "$record = Join-Path $parent 'retention-"+label+"'")
    start = source.index('$runs = @(')
    end = source.index("Add-Type @'", start)
    source = source[:start]+("$runs = @(\n    @{Name='"+label+
        "'; Evidence='artifacts/ai/history-verification-20261019-01'; Expected="+str(count)+"}\n)\n")+source[end:]
    destination = ROOT/'.cache/test-runs/m5-local-economics-20261017-01/ai-registration-preparation11'/('cleanup-'+label+'.ps1')
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(source)
    print(json.dumps(dict(script=str(destination), historical_passed=count)))


if __name__ == '__main__':
    prepare(sys.argv[1])
