# Read-only preview checks. CPU totals identify interval use, not a lifetime budget.
function Get-PreviewResourceSample {
    param([Parameter(Mandatory)][hashtable]$Allowance)
    foreach ($candidate in @(Get-Process | Where-Object { $_.ProcessName -match '^python|strata|llama' })) {
        if ($candidate.Id -ne $Allowance.pid) { throw 'A competing Python, research or model process is running' }
        $details = Get-CimInstance Win32_Process -Filter ('ProcessId='+$candidate.Id) -ErrorAction Stop
        if (-not $details -or -not $details.CommandLine) { throw 'The preview identity cannot be read' }
        $fingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($details.CommandLine))).ToLowerInvariant()
        $created = $details.CreationDate.ToUniversalTime().ToString('o')
        if ($created -cne $Allowance.creation_utc -or $details.ExecutablePath -cne $Allowance.executable -or $fingerprint -cne $Allowance.command_sha256) {
            throw 'The preview identity changed'
        }
        $candidate.Refresh()
        $memory = $candidate.WorkingSet64
        $cpu = $candidate.TotalProcessorTime.TotalSeconds
        if ($memory -gt 67108864) { throw 'The preview exceeds its current memory allowance' }
        @{
            pid=$candidate.Id; creation_utc=$created; executable=$details.ExecutablePath
            command_sha256=$fingerprint; working_set_bytes=$memory; cpu_seconds=$cpu
            monotonic_seconds=([Diagnostics.Stopwatch]::GetTimestamp()/[double][Diagnostics.Stopwatch]::Frequency)
        }
    }
}

function Confirm-PreviewResourceWindow {
    param([AllowEmptyCollection()][object[]]$Before, [AllowEmptyCollection()][object[]]$After)
    if ($Before.Count -ne $After.Count -or $After.Count -gt 1) { throw 'The process set changed or contains competing processes' }
    if ($After.Count -eq 0) { return @{preview_present=$false} }
    $first=$Before[0]; $last=$After[0]
    foreach ($key in @('pid','creation_utc','executable','command_sha256')) {
        if ($first[$key] -cne $last[$key]) { throw 'The preview identity changed during measurement' }
    }
    $elapsed=$last.monotonic_seconds-$first.monotonic_seconds
    $delta=$last.cpu_seconds-$first.cpu_seconds
    # Refuse stale or incomplete samples; a delayed observation cannot grant admission.
    if (-not [double]::IsFinite($elapsed) -or $elapsed -lt 0.5 -or $elapsed -gt 2) { throw 'The preview measurement interval is invalid' }
    if (-not [double]::IsFinite($delta) -or $delta -lt 0 -or $delta -gt 0.10) { throw 'The preview is active or its CPU counter changed' }
    if ($first.working_set_bytes -gt 67108864 -or $last.working_set_bytes -gt 67108864) { throw 'The preview exceeds its current memory allowance' }
    return @{
        preview_present=$true; pid=$last.pid; creation_utc=$last.creation_utc
        elapsed_seconds=$elapsed; cpu_delta_seconds=$delta
        working_set_bytes=$last.working_set_bytes; maximum_working_set_bytes=67108864
        maximum_sample_cpu_seconds=0.10; before=$first; after=$last
        lifetime_cpu_is_diagnostic_only=$true; preview_stopped=$false
    }
}
