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
  6. The practice command runs (run or gepa) with the limits you give it; its JSON record is saved and printed.
  7. The model is unloaded at the end unless -KeepLoaded is given, so the memory comes back.
The kill switch is unchanged: New-Item state\engine\STOP in a second window.

.EXAMPLE
tools\practice.ps1 -Requests 80 -Note "practice run 9"
tools\practice.ps1 -Mode gepa -Cycles 8 -Requests 300 -Note "GEPA run 2"
#>
param(
    [ValidateSet('run','gepa')][string]$Mode='run',
    [int]$Cycles=1,
    [double]$Hours=0,
    [Parameter(Mandatory=$true)][int]$Requests,
    [Parameter(Mandatory=$true)][string]$Note,
    [string]$Model='flint@q4_k_m',
    [int]$Port=1234,
    [int]$ContextLength=16384,
    [switch]$KeepLoaded
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location $root
$python=Join-Path $root '.cache\engine-env\Scripts\python.exe'
$floorGiB=16

function Free-GiB { $os=Get-CimInstance Win32_OperatingSystem; [math]::Round($os.FreePhysicalMemory/1MB,1) }
function Fail($message) { Write-Host "STOP: $message"; exit 2 }

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
$loaded=(lms ps 2>&1 | Out-String)
$ownLoad=$false
if ($loaded -notmatch [regex]::Escape($Model)) {
    Write-Host "loading $Model with its saved settings"
    lms load $Model --gpu max --context-length $ContextLength -y 2>&1 | Select-Object -Last 1 | Write-Host
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
try {
    # 5. The engine's own listing check.
    $report=(& $python -m compertum.ai.engine.practice --project . models 2>&1 | Out-String)
    if ($report -notmatch '"all_listed": true') { Write-Host $report; Fail "the server does not list the model named in config\models.toml for every role" }

    # 6. The run.
    $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
    $record=Join-Path $root ".cache\test-runs\practice-$Mode-$stamp-record.json"
    $arguments=@('-m','compertum.ai.engine.practice','--project','.',$Mode,'--requests',"$Requests",'--note',$Note)
    if ($Hours -gt 0) { $arguments+=@('--hours',"$Hours") } else { $arguments+=@('--cycles',"$Cycles") }
    Write-Host "starting $Mode (cycles $Cycles, hours $Hours, requests $Requests): $Note"
    Write-Host "record: $record"
    & $python @arguments 2>&1 | Tee-Object -FilePath $record
    $exit=$LASTEXITCODE
    Write-Host "practice command exit code $exit"
} finally {
    # 7. Memory back.
    if (-not $KeepLoaded) {
        Write-Host "unloading $Model"
        lms unload $Model 2>&1 | Select-Object -Last 1 | Write-Host
    }
}
exit $exit
