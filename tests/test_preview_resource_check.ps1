param([string]$LegacyLauncher)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$script:checks = 0
function Assert-True($value, $message) {
    if (-not $value) { throw $message }
    $script:checks++
}
function Assert-Refuses([scriptblock]$action, [string]$message) {
    $refused = $false
    try { & $action } catch { $refused = $true }
    Assert-True $refused $message
}
# These fixtures describe the already identified server, without opening a process.
$allowance = @{pid=42;creation_utc='2026-10-15T13:34:48.0000000Z';executable='python.exe';command_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes('preview'))).ToLowerInvariant()}
$script:fixture = [pscustomobject]@{Id=42;ProcessName='python';WorkingSet64=28491776;TotalProcessorTime=[TimeSpan]::FromSeconds(600)}
$script:fixture | Add-Member ScriptMethod Refresh {}
$script:details = [pscustomobject]@{CreationDate=[datetime]::Parse($allowance.creation_utc).ToUniversalTime();ExecutablePath='python.exe';CommandLine='preview'}
function Get-Process { $script:fixture }
function Get-CimInstance { $script:details }
if ($LegacyLauncher) {
    $tokens=$null; $errors=$null
    $tree=[Management.Automation.Language.Parser]::ParseFile($LegacyLauncher,[ref]$tokens,[ref]$errors)
    $node=$tree.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Confirm-ProcessAdmission'},$true)
    . ([scriptblock]::Create($node.Extent.Text))
    $result=@(Confirm-ProcessAdmission)
    Assert-True ($result.Count -eq 1) 'An idle long-running preview must be eligible for interval measurement'
    exit 0
}
. (Join-Path $root 'tools/preview_resource_check.ps1')
$sample = @(Get-PreviewResourceSample $allowance)
Assert-True ($sample.Count -eq 1 -and $sample[0].cpu_seconds -eq 600) 'Lifetime CPU must be recorded without rejecting the preview'
function Sample([double]$cpu=600,[double]$tick=10) {
    @{pid=42;creation_utc=$allowance.creation_utc;executable='python.exe';command_sha256=$allowance.command_sha256;cpu_seconds=$cpu;working_set_bytes=28491776;monotonic_seconds=$tick}
}
$base=Sample
Assert-True ((Confirm-PreviewResourceWindow @($base) @((Sample 600 10.5))).cpu_delta_seconds -eq 0) 'Idle preview must pass'
Assert-True ((Confirm-PreviewResourceWindow @((Sample 0 10)) @((Sample 0.1 10.5))).cpu_delta_seconds -eq 0.1) 'Exact CPU boundary must pass'
$atLimit=Sample 600 10.5; $atLimit.working_set_bytes=67108864
Assert-True ((Confirm-PreviewResourceWindow @($base) @($atLimit)).working_set_bytes -eq 67108864) 'Exact memory boundary must pass'
Assert-Refuses { Confirm-PreviewResourceWindow @($base) @((Sample 600.101 10.5)) } 'Busy preview must refuse'
Assert-Refuses { Confirm-PreviewResourceWindow @($base) @((Sample 599 10.5)) } 'CPU counter regression must refuse'
Assert-Refuses { Confirm-PreviewResourceWindow @($base) @((Sample 600 10.49)) } 'Short sample must refuse'
Assert-Refuses { Confirm-PreviewResourceWindow @($base) @((Sample 600 12.01)) } 'Delayed sample must refuse'
Assert-Refuses { Confirm-PreviewResourceWindow @($base) @() } 'Exited preview must refuse'
Assert-Refuses { Confirm-PreviewResourceWindow @() @($base) } 'New preview must refuse'
Assert-True ((Confirm-PreviewResourceWindow @() @()).preview_present -eq $false) 'An absent preview requires no stop or restart'
foreach ($key in @('pid','creation_utc','executable','command_sha256')) {
    $changed=Sample 600 10.5; $changed[$key]='changed'
    Assert-Refuses { Confirm-PreviewResourceWindow @($base) @($changed) } "Changed $key must refuse"
}
$tooLarge=Sample 600 10.5; $tooLarge.working_set_bytes=67108865
Assert-Refuses { Confirm-PreviewResourceWindow @($base) @($tooLarge) } 'Memory overage must refuse'
Assert-Refuses { Confirm-PreviewResourceWindow @($base,$base) @($base,$base) } 'Multiple previews must refuse'
$script:fixture.Id=43
Assert-Refuses { Get-PreviewResourceSample $allowance } 'Competing Python must refuse'
$script:fixture.Id=42; $script:details.CommandLine='changed'
Assert-Refuses { Get-PreviewResourceSample $allowance } 'Live command identity drift must refuse'
$script:details.CommandLine='preview'; $script:fixture.WorkingSet64=67108865
Assert-Refuses { Get-PreviewResourceSample $allowance } 'Live memory overage must refuse'
@{scope='SIMULATED_PREVIEW_CHECKS';passed=$script:checks;failed=0;errors=0;skipped=0;product_tests=0} | ConvertTo-Json -Compress
