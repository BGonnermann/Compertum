# Reviewed first batch under docs/TEST_RETENTION.md. No recursive deletion.
[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$watch = [Diagnostics.Stopwatch]::StartNew()
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$parent = Join-Path $root '.cache/test-runs/m5-local-economics-20261017-01'
$record = Join-Path $parent 'test-retention01'
$runs = @(
    @{Name='ai-history-tests03'; Evidence='artifacts/ai/history-verification-20261019-01'; Expected=121},
    @{Name='ai-review-tests03'; Evidence='artifacts/ai/review-plan-verification-20261018-01'; Expected=58}
)
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class RetentionMemory {
    [StructLayout(LayoutKind.Sequential)] public struct Status {
        public uint length, load;
        public ulong total, available, pageTotal, pageAvailable, virtualTotal, virtualAvailable, extended;
    }
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool GlobalMemoryStatusEx(ref Status value);
    public static ulong Available() {
        var value = new Status(); value.length = (uint)Marshal.SizeOf<Status>();
        if (!GlobalMemoryStatusEx(ref value)) throw new Exception("Memory query failed");
        return value.available;
    }
}
'@
$self = [Diagnostics.Process]::GetCurrentProcess()
$mask = $self.ProcessorAffinity.ToInt64()
$self.ProcessorAffinity = [IntPtr]($mask -band (-$mask))
if ([RetentionMemory]::Available() -lt 16GB) { throw 'Available memory is below 16 GiB.' }
function Check-Limits {
    if ($watch.Elapsed.TotalSeconds -ge 120) { throw 'Cleanup reached its 120-second deadline.' }
    if ([RetentionMemory]::Available() -lt 12GB) { throw 'Available memory is below 12 GiB.' }
    $self.Refresh()
    if ($self.WorkingSet64 -gt 512MB) { throw 'Cleanup exceeded 512 MiB of working memory.' }
}
function Check-Ancestors([string]$path) {
    $item = Get-Item -LiteralPath $path -Force
    while ($null -ne $item) {
        if (!($item.Attributes -band [IO.FileAttributes]::Directory) -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Unsafe directory: $($item.FullName)"
        }
        $item = $item.Parent
    }
}
function Hash-File([string]$path) {
    Check-Limits
    (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
}
function Save-New([string]$name, $value) {
    $raw = $value | ConvertTo-Json -Depth 12 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($raw)
    $used = (Get-ChildItem -LiteralPath $record -File -Force | Measure-Object Length -Sum).Sum
    if ($used + $bytes.Length -gt 1MB) { throw 'Cleanup records would exceed 1 MiB.' }
    $stream = [IO.File]::Open((Join-Path $record $name), 'CreateNew', 'Write', 'None')
    try { $stream.Write($bytes); $stream.Flush($true) } finally { $stream.Dispose() }
}
Check-Ancestors $parent
if ($Apply -and (Test-Path -LiteralPath $record)) { throw 'This cleanup attempt already exists. Preserve it.' }
# Refuse concurrent Python or pytest work. Do not log process command lines.
$workers = @(Get-Process | Where-Object {
    $_.ProcessName -match '^(python(w)?|pytest)$'
})
if ($workers.Count) { throw 'Python or pytest is running. Wait for it to finish before cleanup.' }
$pins = @{}
$inventory = [Collections.Generic.List[object]]::new()
$summary = [Collections.Generic.List[object]]::new()
foreach ($run in $runs) {
    Check-Limits
    $target = [IO.Path]::GetFullPath((Join-Path $parent ($run.Name + '/pytest')))
    if (!$target.StartsWith($parent + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Target escaped the approved parent.'
    }
    Check-Ancestors $target
    $evidence = Join-Path $root $run.Evidence
    Check-Ancestors $evidence
    foreach ($file in Get-ChildItem -LiteralPath $evidence -File -Force) {
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked evidence file.' }
        $pins[$file.FullName] = Hash-File $file.FullName
    }
    $closure = Get-Content -LiteralPath (Join-Path $evidence ($run.Name+'.closure.json')) -Raw | ConvertFrom-Json
    if ($closure.stage -ne $run.Name -or $closure.status -ne 'PASSED' -or $closure.exit_code -ne 0 -or
        $closure.exit_observed -ne $true -or $closure.remaining_children -ne 0) { throw 'Job closure did not pass.' }
    if (Get-Process -Id $closure.pid -ErrorAction SilentlyContinue) { throw 'The recorded process ID is currently active.' }
    [xml]$xml = Get-Content -LiteralPath (Join-Path $evidence ($run.Name+'-results.xml')) -Raw
    $suites = @($xml.SelectNodes('//testsuite'))
    $cases = @($xml.SelectNodes('//testcase'))
    if ($cases.Count -ne $run.Expected -or $suites.Count -ne 1 -or
        [int]$suites[0].tests -ne $run.Expected -or [int]$suites[0].failures -ne 0 -or
        [int]$suites[0].errors -ne 0 -or [int]$suites[0].skipped -ne 0 -or
        $xml.SelectNodes('//failure|//error|//skipped').Count -ne 0) { throw 'Test results are not wholly passing.' }
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($target)
    [long]$charge = 0
    $startCount = $inventory.Count
    while ($pending.Count) {
        Check-Limits
        $path = $pending.Pop()
        $item = Get-Item -LiteralPath $path -Force
        $link = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
        $kind = if ($link) {'link'} elseif ($item.PSIsContainer) {'directory'} else {'file'}
        $length = if ($kind -eq 'file') {[long]$item.Length} else {0L}
        $cost = if ($kind -eq 'file') {[long]([math]::Ceiling($length/4096.0)*4096)} else {4096L}
        $linkTarget = ''
        if ($link) {
            if ($item.LinkType -ne 'SymbolicLink') { throw 'Unexpected reparse point.' }
            $linkTarget = [IO.Path]::GetFullPath([string]$item.Target)
            if (!$linkTarget.StartsWith($target+'\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Link points outside selected tree.' }
        }
        $inventory.Add(@{path=$path.Substring($root.Length+1); kind=$kind; bytes=$length;
            charge=$cost; modified=$item.LastWriteTimeUtc.Ticks; target=$linkTarget})
        $charge += $cost
        if ($kind -eq 'directory') {
            foreach ($child in Get-ChildItem -LiteralPath $path -Force) { $pending.Push($child.FullName) }
        }
    }
    $summary.Add(@{run=$run.Name; target=$target; historical_passed=$run.Expected;
        entries=$inventory.Count-$startCount; charged_bytes=$charge})
}
if (!$Apply) {
    @{mode='DRY_RUN'; runs=@($summary.ToArray()); elapsed_seconds=$watch.Elapsed.TotalSeconds} | ConvertTo-Json -Depth 5
    exit 0
}
New-Item -ItemType Directory -Path $record | Out-Null
Check-Ancestors $record
Save-New 'plan.json' @{policy='docs/TEST_RETENTION.md'; runs=@($summary.ToArray()); entries=@($inventory.ToArray()); evidence_hashes=$pins}
$removed = 0
try {
    # Remove links first, then ordinary files, then empty directories. Never recurse.
    $ordered = @($inventory | Sort-Object @{Expression={if($_.kind -eq 'link'){0}elseif($_.kind -eq 'file'){1}else{2}}}, @{Expression={$_.path.Length};Descending=$true})
    foreach ($entry in $ordered) {
        Check-Limits
        $path = Join-Path $root $entry.path
        Check-Ancestors ([IO.Path]::GetDirectoryName($path))
        $item = Get-Item -LiteralPath $path -Force
        $link = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
        if ($entry.kind -eq 'link') {
            if (!$link -or $item.LinkType -ne 'SymbolicLink' -or [string]$item.Target -ne $entry.target) { throw 'Link changed.' }
            Remove-Item -LiteralPath $path -Force
        } elseif ($entry.kind -eq 'file') {
            if ($link -or $item.PSIsContainer -or $item.Length -ne $entry.bytes -or $item.LastWriteTimeUtc.Ticks -ne $entry.modified) { throw 'File changed.' }
            Remove-Item -LiteralPath $path -Force
        } else {
            if ($link -or !$item.PSIsContainer) { throw 'Directory changed.' }
            [IO.Directory]::Delete($path, $false)
        }
        $removed++
    }
    foreach ($run in $summary) {
        if (Test-Path -LiteralPath $run.target) { throw 'Temporary tree remains.' }
        Check-Ancestors (Split-Path $run.target -Parent)
    }
    foreach ($path in $pins.Keys) { if ((Hash-File $path) -ne $pins[$path]) { throw 'Retained evidence changed.' } }
    Save-New 'result.json' @{status='VERIFIED'; removed_entries=$removed; evidence_files_verified=$pins.Count;
        runs=@($summary.ToArray()); elapsed_seconds=$watch.Elapsed.TotalSeconds; product_tests_run=0}
    Get-Content -LiteralPath (Join-Path $record 'result.json')
} catch {
    Save-New 'failure.json' @{status='PARTIAL_OR_FAILED'; removed_entries=$removed; error=$_.Exception.Message; elapsed_seconds=$watch.Elapsed.TotalSeconds}
    throw
}
