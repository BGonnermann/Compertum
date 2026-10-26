<#
.SYNOPSIS
One owner command for a practice run: start the model server, load the model, run the engine, unload the model.

.DESCRIPTION
Owner-started only (section 19: the owner starts each run). Nothing here runs on its own or on a schedule.
Steps, in order, each one checked before the next:
  1. Free host memory must be at least the start floor (16 GiB) before the model loads.
  2. The server settings must have on-demand model loading off; otherwise the script stops and says so.
  3. The LM Studio server (Bionic) starts on the port if it is not running. No window is needed.
  4. The model loads with its saved per-model settings if it is not loaded, then must be listed by the server.
  5. The engine's own `models` check must report all four roles listed.
  6. The practice command runs (run, gepa, bench or holdout) with the limits you give it; its JSON record is saved and printed.
     bench and holdout measure the prompts on the fixed markets of src\compertum\ai\engine\bench.py. They take -CyclesPerMarket,
     not -Cycles. A holdout run is counted before its first cycle; the holdout retires after its allowed uses.
  7. The model is unloaded at the end unless -KeepLoaded is given, so the memory comes back.
The kill switch is unchanged: New-Item state\engine\STOP in a second window.

.EXAMPLE
tools\practice.ps1 -Requests 80 -Note "practice run 9"
tools\practice.ps1 -Mode gepa -Cycles 8 -Requests 300 -Note "GEPA run 2"
tools\practice.ps1 -Mode bench -Requests 450 -Note "bench baseline 1"
tools\practice.ps1 -Mode holdout -Requests 450 -PromptsRun run-20261026-0123abcd -PromptsCandidate 2 -Note "holdout check of GEPA run 3"
#>
param(
    [ValidateSet('run','gepa','bench','holdout')][string]$Mode='run',
    [int]$Cycles=1,
    [int]$CyclesPerMarket=4,
    [string]$PromptsRun='',
    [int]$PromptsCandidate=-1,
    [double]$Hours=0,
    [Parameter(Mandatory=$true)][int]$Requests,
    [Parameter(Mandatory=$true)][string]$Note,
    [string]$Model='flint@q4_k_m',
    [int]$Port=1234,
    [int]$ContextLength=16384,
    [int]$Parallel=1,
    [switch]$KeepLoaded
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location $root
$python=Join-Path $root '.cache\engine-env\Scripts\python.exe'
$floorGiB=16

function Free-GiB { $os=Get-CimInstance Win32_OperatingSystem; [math]::Round($os.FreePhysicalMemory/1MB,1) }
function Fail($message) { Write-Host "STOP: $message"; exit 2 }

# Options for the wrong mode stop the script before the model loads, so nothing is silently ignored (review, 25 October 2026).
$evaluationMode=($Mode -eq 'bench' -or $Mode -eq 'holdout')
if ($evaluationMode -and $PSBoundParameters.ContainsKey('Cycles')) { Fail "-Cycles does not apply to $Mode; use -CyclesPerMarket" }
if (-not $evaluationMode -and ($PSBoundParameters.ContainsKey('CyclesPerMarket') -or $PSBoundParameters.ContainsKey('PromptsRun') -or $PSBoundParameters.ContainsKey('PromptsCandidate'))) { Fail "-CyclesPerMarket, -PromptsRun and -PromptsCandidate apply to bench and holdout only" }
if (($PromptsRun -eq '') -ne ($PromptsCandidate -eq -1)) { Fail 'give -PromptsRun and -PromptsCandidate together, or neither' }
if (-not (Get-Command lms -ErrorAction SilentlyContinue)) { Fail 'the lms command is not on PATH (LM Studio / Bionic CLI)' }
if (-not (Test-Path $python)) { Fail "engine environment missing: $python" }
if (Test-Path (Join-Path $root 'state\engine\STOP')) { Fail 'state\engine\STOP exists; remove it before a new run' }

# 1. Memory before the load.
$free=Free-GiB
Write-Host "free memory before load: $free GiB (floor $floorGiB GiB)"
if ($free -lt $floorGiB) { Fail "free memory $free GiB is under the floor before the model is loaded" }

# 2. On-demand loading must be off (the app reads its own copy of the server settings).
$serverConfig=Join-Path $env:USERPROFILE '.lmstudio\apps\bionic\.internal\http-server-config.json'
if (Test-Path $serverConfig) {
    $settings=Get-Content $serverConfig -Raw | ConvertFrom-Json
    if ($settings.justInTimeModelLoading -ne $false) { Fail "on-demand model loading is on in $serverConfig; turn it off (the owner's setting of 24 October 2026) and restart the server" }
} else { Write-Host "note: server settings file not found at $serverConfig; on-demand loading not checked" }

# 3. Server.
$status=(lms status 2>&1 | Out-String)
if ($status -notmatch 'ON') {
    Write-Host "starting the model server on port $Port"
    lms server start --port $Port 2>&1 | Select-Object -Last 1 | Write-Host
    Start-Sleep -Seconds 3
}

# 4. Model.
# One prediction slot by default. The server was loaded with 4 slots until 25 October 2026 (the lms default), and memory fell by about 12 GiB during practice run 11.
$loaded=(lms ps 2>&1 | Out-String)
$ownLoad=$false
if ($loaded -match [regex]::Escape($Model)) {
    $line=($loaded -split "`n" | Where-Object { $_ -match [regex]::Escape($Model) } | Select-Object -First 1)
    $fields=($line -split '\s+') | Where-Object { $_ -ne '' }
    $unit=[array]::IndexOf($fields,'GB')
    if ($unit -ge 0 -and $fields.Count -gt ($unit+2) -and $fields[$unit+2] -ne "$Parallel") {
        Write-Host "$Model is loaded with $($fields[$unit+2]) prediction slots; reloading with $Parallel"
        lms unload $Model 2>&1 | Out-Null
        Start-Sleep -Seconds 3
        $loaded=(lms ps 2>&1 | Out-String)
    }
}
if ($loaded -notmatch [regex]::Escape($Model)) {
    Write-Host "loading $Model with its saved settings and $Parallel prediction slot(s)"
    lms load $Model --gpu max --context-length $ContextLength --parallel $Parallel -y 2>&1 | Select-Object -Last 1 | Write-Host
    $ownLoad=$true
    Start-Sleep -Seconds 5
    $loaded=(lms ps 2>&1 | Out-String)
    if ($loaded -notmatch [regex]::Escape($Model)) { Fail "$Model did not load" }
} else { Write-Host "$Model is already loaded" }
$free=Free-GiB
Write-Host "free memory after load: $free GiB"
if ($free -lt $floorGiB) {
    if ($ownLoad -and -not $KeepLoaded) { lms unload $Model 2>&1 | Out-Null }
    Fail "free memory $free GiB is under the floor with the model loaded; the engine would refuse"
}

$exit=2
$sampler=$null
try {
    # A memory record, one line every 30 seconds: free host memory and the model server's own memory. It shows what grows during a run.
    $memoryLog=Join-Path $root (".cache\test-runs\practice-$Mode-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+"-memory.csv")
    "time,free_gib,model_server_gib" | Set-Content $memoryLog
    $sampler=Start-Job -ArgumentList $memoryLog -ScriptBlock {
        param($path)
        while ($true) {
            $os=Get-CimInstance Win32_OperatingSystem
            $server=(Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum
            ('{0},{1:N1},{2:N1}' -f (Get-Date -Format 'HH:mm:ss'),($os.FreePhysicalMemory/1MB),($server/1GB)) | Add-Content $path
            Start-Sleep -Seconds 30
        }
    }
    Write-Host "memory record: $memoryLog"
    # 5. The engine's own listing check.
    $report=(& $python -m compertum.ai.engine.practice --project . models 2>&1 | Out-String)
    if ($report -notmatch '"all_listed": true') { Write-Host $report; Fail "the server does not list the model named in config\models.toml for every role" }

    # 6. The run.
    $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
    $record=Join-Path $root ".cache\test-runs\practice-$Mode-$stamp-record.json"
    $arguments=@('-m','compertum.ai.engine.practice','--project','.',$Mode,'--requests',"$Requests",'--note',$Note)
    $evaluation=($Mode -eq 'bench' -or $Mode -eq 'holdout')
    if ($evaluation) {
        $arguments+=@('--cycles-per-market',"$CyclesPerMarket")
        if ($Hours -gt 0) { $arguments+=@('--hours',"$Hours") }
        if ($PromptsRun -ne '') { $arguments+=@('--prompts-run',$PromptsRun,'--prompts-candidate',"$PromptsCandidate") }
        Write-Host "starting $Mode ($CyclesPerMarket cycles per market, hours $Hours, requests $Requests): $Note"
    } else {
        if ($Hours -gt 0) { $arguments+=@('--hours',"$Hours") } else { $arguments+=@('--cycles',"$Cycles") }
        Write-Host "starting $Mode (cycles $Cycles, hours $Hours, requests $Requests): $Note"
    }
    Write-Host "record: $record"
    & $python @arguments 2>&1 | Tee-Object -FilePath $record
    $exit=$LASTEXITCODE
    Write-Host "practice command exit code $exit"
} finally {
    if ($sampler) { Stop-Job $sampler -ErrorAction SilentlyContinue; Remove-Job $sampler -Force -ErrorAction SilentlyContinue }
    # 7. Memory back.
    if (-not $KeepLoaded) {
        Write-Host "unloading $Model"
        lms unload $Model 2>&1 | Select-Object -Last 1 | Write-Host
    }
}
exit $exit
