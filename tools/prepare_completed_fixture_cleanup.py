"""Prepare cleanup for fixed, reviewed source and installed test folders."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
NATIVE = 'artifacts/m5/native-economics-20261017-01'
DISPATCH = 'artifacts/m5/risk-dispatch-20261017-01'
RUNS = {
    'shutdown-green01-source': (NATIVE, 61),
    'current04-recovery-b1-source': (NATIVE, 61),
    'review3-full02-recovery-b1-source': (NATIVE, 61),
    'review3-full02-preflight-b1-source': (NATIVE, 33),
    'dispatch-final01-fast01-source': (DISPATCH, 224),
    'native-reconciliation-green03-source': (DISPATCH, 42),
    'recovery-reply-green01-source': (DISPATCH, 79),
    'native-reconciliation-green01-source': (DISPATCH, 21),
    'dispatch-boundary-green01-source': (DISPATCH, 23),
    'green04-fast-b1-source': (DISPATCH, 80),
    'green02-fast-b1-source': (DISPATCH, 76),
}
INSTALLED = {
    'current04-recovery-b1-installed': (NATIVE, 61),
    'review3-full02-recovery-b1-installed': (NATIVE, 61),
    'review3-full02-preflight-b1-installed': (NATIVE, 33),
    'dispatch-final01-fast01-installed': (DISPATCH, 224),
}


def change(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Cleanup template changed: '+old)
    return source.replace(old, new)


def prepare(label):
    evidence, count = (INSTALLED if label in INSTALLED else RUNS)[label]
    source = (ROOT/'tools/Remove-CompletedTestFiles.ps1').read_text()
    source = change(source, "$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))",
                    "$root = '"+str(ROOT).replace("'", "''")+"'")
    source = change(source, "$record = Join-Path $parent 'test-retention01'",
                    "$record = Join-Path $parent 'retention-old-"+label+"'")
    if label in INSTALLED:
        source = change(source, "$parent = Join-Path $root '.cache/test-runs/m5-local-economics-20261017-01'",
                        "$parent = Join-Path $root '.cache/test-runs/m5-reconciliation-installed-20261016-01/local-economics-20261017-01'")
        source = change(source, "$record = Join-Path $parent 'retention-old-"+label+"'",
                        "$record = Join-Path $root '.cache/test-runs/m5-local-economics-20261017-01/retention-old-"+label+"'")
    start = source.index('$runs = @('); end = source.index("Add-Type @'", start)
    source = source[:start]+("$runs = @(\n    @{Name='"+label+"'; Evidence='"+evidence+
                            "'; Expected="+str(count)+"}\n)\n")+source[end:]
    source = change(source, "($run.Name + '/pytest')", '$run.Name')
    source = change(source, "($run.Name+'-results.xml')", "($run.Name+'.xml')")
    source = change(source, '        $inventory.Add(@{', '        if ($path -ne $target) {\n        $inventory.Add(@{')
    source = change(source, '        $charge += $cost', '        $charge += $cost\n        }')
    source = change(source, "        if (Test-Path -LiteralPath $run.target) { throw 'Temporary tree remains.' }\n        Check-Ancestors (Split-Path $run.target -Parent)",
                    "        Check-Ancestors $run.target\n        if (@(Get-ChildItem -LiteralPath $run.target -Force).Count) { throw 'Temporary children remain.' }")
    path = ROOT/'.cache/test-runs/m5-local-economics-20261017-01/ai-registration-preparation10'/('cleanup-old-'+label+'.ps1')
    with path.open('x', encoding='utf-8') as output:
        output.write(source)
    print(path)


if __name__ == '__main__':
    prepare(sys.argv[1])
