<#
.SYNOPSIS
One owner command for a practice run: start the model server, load the model, run the engine, unload the model.

.DESCRIPTION
Owner-started only (section 19: the owner starts each run). Nothing here runs on its own or on a schedule.
Steps, in order, each one checked before the next:
  1. Free host memory must be at least the start floor (8 GiB since 26 October 2026; it was 16 GiB) before the model loads.
  2. The server settings must have on-demand model loading off; otherwise the script stops and says so.
  3. The LM Studio server (Bionic) starts on the port if it is not running. No window is needed.
  4. The model loads with its saved per-model settings if it is not loaded, then must be listed by the server.
  5. The engine's own `models` check must report all four roles listed.
  6. The practice command runs (run, gepa, bench or holdout) with the limits you give it; its JSON record is saved and printed.
     bench and holdout measure the prompts on the fixed markets of src\compertum\ai\engine\bench.py. They take -CyclesPerMarket,
     not -Cycles. A holdout run is counted before its first cycle; the holdout retires after its allowed uses.
  7. The model is unloaded at the end unless -KeepLoaded is given, so the memory comes back.
-Models NAME (owner standard, 26 October 2026: any local model, API key or sign-in) uses config\models-NAME.toml instead of the
LM Studio file config\models.toml. A named file whose addresses are all loopback is local too (30 October 2026: a thinking local model
needs a file with max_tokens), and LM Studio loads -Model as usual. A file with a remote address skips steps 2, 3, 4 and 7: LM Studio is not started or loaded. Remote addresses in that file must
belong to a provider in config\providers.toml; the engine reads the provider's key from the user environment variable named there and
refuses at step 5 if it is missing. The key is never printed. Example: -Models deepseek (authorized 26 October 2026).
-ReflectModels NAME and -ReflectModel ID (gepa only) send GEPA's reflection calls to another model file, for example -ReflectModels deepseek
-ReflectModel deepseek-flash while the four roles run on the local model. The reflection requests count against the same request limit.
The kill switch is unchanged: New-Item state\engine\STOP in a second window.

.EXAMPLE
tools\practice.ps1 -Requests 80 -Note "practice run 9"
tools\practice.ps1 -Mode gepa -Cycles 8 -Requests 300 -Note "GEPA run 2"
tools\practice.ps1 -Mode bench -Requests 450 -Note "bench baseline 1"
tools\practice.ps1 -Mode holdout -Requests 450 -PromptsRun run-20261026-0123abcd -PromptsCandidate 2 -Note "holdout check of GEPA run 3"
tools\practice.ps1 -Models deepseek -Model deepseek-v4-pro -Mode bench -CyclesPerMarket 4 -Requests 450 -Note "DeepSeek bench baseline 1"
tools\practice.ps1 -Pick -Mode bench -CyclesPerMarket 4 -Requests 450 -Note "bench run"
tools\practice.ps1 -Models deepseek -Model deepseek-flash -Mode bench -BenchSet bench-3 -CyclesPerMarket 4 -Requests 2000 -Note "bench-3 flash baseline"

.NOTES
Choosing the model at run time (owner direction, 26 October 2026: pick the model, then run, with no file edits):
  -Model ID  one model for every role, for this run only. For local runs it is also the LM Studio model that is loaded.
             Without -Model, the model file's own IDs are used.
  -Pick      a menu: first the model file (local, or each config\models-NAME.toml), then the models that provider lists now.
The run's START row records the model of every role.
#>
param(
    [ValidateSet('run','gepa','bench','holdout')][string]$Mode='run',
    [int]$Cycles=1,
    [int]$CyclesPerMarket=4,
    [ValidateSet('bench-1','bench-2','bench-3','bench-4')][string]$BenchSet='bench-1',
    [string[]]$MarketManifest=@(),
    [int]$Seed=12,
    [string]$PromptsRun='',
    [int]$PromptsCandidate=-1,
    [double]$Hours=0,
    [Parameter(Mandatory=$true)][int]$Requests,
    [Parameter(Mandatory=$true)][string]$Note,
    [string]$Model='flint@q4_k_m',
    [int]$Port=1234,
    [int]$ContextLength=16384,
    [int]$Parallel=1,
    [ValidatePattern('^[a-z0-9][a-z0-9-]{0,31}$')][string]$Models='local',
    [string]$ReflectModels='',
    [string]$ReflectModel='',
    [double]$SpeedWeight=-1,
    [string]$Goal='',
    [switch]$Pick,
    [switch]$KeepLoaded
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location $root
$python=Join-Path $root '.cache\engine-env\Scripts\python.exe'
$floorGiB=8

function Free-GiB { $os=Get-CimInstance Win32_OperatingSystem; [math]::Round($os.FreePhysicalMemory/1MB,1) }
function Fail($message) { Write-Host "STOP: $message"; exit 2 }

# Options for the wrong mode stop the script before the model loads, so nothing is silently ignored (review, 25 October 2026).
$evaluationMode=($Mode -eq 'bench' -or $Mode -eq 'holdout')
if ($evaluationMode -and $PSBoundParameters.ContainsKey('Cycles')) { Fail "-Cycles does not apply to $Mode; use -CyclesPerMarket" }
if (-not $evaluationMode -and ($PSBoundParameters.ContainsKey('CyclesPerMarket') -or $PSBoundParameters.ContainsKey('PromptsRun') -or $PSBoundParameters.ContainsKey('PromptsCandidate') -or $PSBoundParameters.ContainsKey('BenchSet'))) { Fail "-CyclesPerMarket, -BenchSet, -PromptsRun and -PromptsCandidate apply to bench and holdout only" }
if ($Mode -eq 'holdout' -and $PSBoundParameters.ContainsKey('BenchSet')) { Fail '-BenchSet applies to bench only; the holdout cannot be moved' }
if ($evaluationMode -and $MarketManifest.Count -gt 0) { Fail '-MarketManifest applies to run and gepa only; bench and holdout stay fixed' }
if ($Mode -ne 'run' -and $PSBoundParameters.ContainsKey('Seed')) { Fail '-Seed applies to run only; GEPA, bench and holdout markets are fixed' }
if (($PromptsRun -eq '') -ne ($PromptsCandidate -eq -1)) { Fail 'give -PromptsRun and -PromptsCandidate together, or neither' }
# GEPA needs a cycle limit: -Hours alone would load the model and then be refused (review, 26 October 2026).
if ($Mode -eq 'gepa' -and $Hours -gt 0 -and -not $PSBoundParameters.ContainsKey('Cycles')) { Fail 'gepa needs -Cycles; -Hours alone is not enough' }
function Choose($title,$items) {
    if (-not $items -or $items.Count -eq 0) { Fail "nothing to choose for: $title" }
    Write-Host $title
    for ($i=0; $i -lt $items.Count; $i++) { Write-Host ("  {0}. {1}" -f ($i+1),$items[$i]) }
    $answer=Read-Host 'Number'
    $n=0
    if (-not [int]::TryParse($answer,[ref]$n) -or $n -lt 1 -or $n -gt $items.Count) { Fail "no such choice: $answer" }
    return $items[$n-1]
}
$modelChosen=$PSBoundParameters.ContainsKey('Model')
if ($Pick) {
    if (-not (Test-Path $python)) { Fail "engine environment missing: $python" }
    $files=@('local')+@(Get-ChildItem (Join-Path $root 'config') -Filter 'models-*.toml' | ForEach-Object { $_.BaseName.Substring(7) } | Sort-Object)
    $Models=Choose 'Model source:' $files
    if ($Models -eq 'local') {
        # The language models downloaded in LM Studio, by their load key.
        $listed=@((lms ls --json | ConvertFrom-Json) | Where-Object { $_.type -eq 'llm' } | ForEach-Object { $_.modelKey })
    } else {
        $report=(& $python -m compertum.ai.engine.practice --project . --models $Models models 2>&1 | Out-String)
        try { $parsed=$report | ConvertFrom-Json } catch { Write-Host $report; Fail "could not list the models of $Models" }
        if ($parsed.refused) { Fail "listing the models of $Models was refused: $($parsed.refused)" }
        $listed=@($parsed.servers.PSObject.Properties | ForEach-Object { $_.Value.models } | Sort-Object -Unique)
    }
    $Model=Choose "Models of ${Models}:" $listed
    $modelChosen=$true
    Write-Host "chosen: $Models / $Model"
}
$modelArguments=@('--models',$Models)
if ($modelChosen) { $modelArguments+=@('--model',$Model) }
$modelFile=if ($Models -eq 'local') { Join-Path $root 'config\models.toml' } else { Join-Path $root "config\models-$Models.toml" }
if (-not (Test-Path $modelFile)) { Fail "model file not found: $modelFile" }
$addresses=@(Select-String -Path $modelFile -Pattern '^\s*base_url\s*=\s*"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value })
$remote=(@($addresses | Where-Object { $_ -notmatch '^http://(127\.0\.0\.1|localhost):' }).Count -gt 0)
if ($remote) {
    if (-not (Test-Path (Join-Path $root "config\models-$Models.toml"))) { Fail "model file config\models-$Models.toml not found" }
} elseif (-not (Get-Command lms -ErrorAction SilentlyContinue)) { Fail 'the lms command is not on PATH (LM Studio / Bionic CLI)' }
if (-not (Test-Path $python)) { Fail "engine environment missing: $python" }
if (Test-Path (Join-Path $root 'state\engine\STOP')) { Fail 'state\engine\STOP exists; remove it before a new run' }

# 1. Memory before the load.
$free=Free-GiB
Write-Host "free memory before load: $free GiB (floor $floorGiB GiB)"
if ($free -lt $floorGiB) { Fail "free memory $free GiB is under the floor before the model is loaded" }

$ownLoad=$false
if (-not $remote) {
    # 2. On-demand loading must be off (the app reads its own copy of the server settings).
    $serverConfig=Join-Path $env:USERPROFILE '.lmstudio\apps\bionic\.internal\http-server-config.json'
    if (Test-Path $serverConfig) {
        $settings=Get-Content $serverConfig -Raw | ConvertFrom-Json
        if ($settings.justInTimeModelLoading -ne $false) { Fail "on-demand model loading is on in $serverConfig; turn it off (the owner's setting of 24 October 2026) and restart the server" }
    } else { Write-Host "note: server settings file not found at $serverConfig; on-demand loading not checked" }

    # 3. Server.
    $status=(lms status 2>&1 | Out-String)
    # Case-sensitive and anchored to the status line, so words such as 'connection' never read as ON (review, 26 October 2026).
    if ($status -cnotmatch 'Server:\s+ON\b') {
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
}

$exit=2
$sampler=$null
try {
    # A memory record, one line every 30 seconds: free host memory and the model server's own memory. It shows what grows during a run.
    $memoryLog=Join-Path $root (".cache\test-runs\practice-$Mode-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+"-memory.csv")
    # gpu_used_gib (added 26 October 2026) shows how much of the GPU the offloaded expert layers use; empty when nvidia-smi is not available.
    "time,free_gib,model_server_gib,gpu_used_gib" | Set-Content $memoryLog
    $sampler=Start-Job -ArgumentList $memoryLog -ScriptBlock {
        param($path)
        while ($true) {
            $os=Get-CimInstance Win32_OperatingSystem
            $server=(Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum
            $gpu=''
            try { $mib=(& nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null | Select-Object -First 1); if ($mib) { $gpu='{0:F1}' -f ([double]$mib/1024) } } catch {}
            ('{0},{1:F1},{2:F1},{3}' -f (Get-Date -Format 'HH:mm:ss'),($os.FreePhysicalMemory/1MB),($server/1GB),$gpu) | Add-Content $path
            Start-Sleep -Seconds 30
        }
    }
    Write-Host "memory record: $memoryLog"
    # 5. The engine's own listing check.
    $report=(& $python -m compertum.ai.engine.practice --project . @modelArguments models 2>&1 | Out-String)
    if ($report -notmatch '"all_listed": true') { Write-Host $report; Fail "the server does not list the configured model for every role (models file: $Models)" }

    # 6. The run.
    $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
    $record=Join-Path $root ".cache\test-runs\practice-$Mode-$stamp-record.json"
    $arguments=@('-m','compertum.ai.engine.practice','--project','.')+$modelArguments+@($Mode,'--requests',"$Requests",'--note',$Note)
    $evaluation=($Mode -eq 'bench' -or $Mode -eq 'holdout')
    if ($evaluation) {
        $arguments+=@('--cycles-per-market',"$CyclesPerMarket")
        if ($Mode -eq 'bench') { $arguments+=@('--bench-set',$BenchSet) }
        if ($Hours -gt 0) { $arguments+=@('--hours',"$Hours") }
        if ($PromptsRun -ne '') { $arguments+=@('--prompts-run',$PromptsRun,'--prompts-candidate',"$PromptsCandidate") }
        Write-Host "starting $Mode ($CyclesPerMarket cycles per market, hours $Hours, requests $Requests): $Note"
    } else {
        # Both limits pass when both are given; the run stops at the first one (review, 26 October 2026: -Cycles was dropped when -Hours was given).
        if ($Hours -gt 0) { $arguments+=@('--hours',"$Hours") }
        if ($Hours -le 0 -or $PSBoundParameters.ContainsKey('Cycles')) { $arguments+=@('--cycles',"$Cycles") }
        if ($Mode -eq 'run' -and $PSBoundParameters.ContainsKey('Seed')) { $arguments+=@('--seed',"$Seed") }
        foreach ($manifest in $MarketManifest) { $arguments+=@('--market-manifest',$manifest) }
        if ($ReflectModels -ne '' -or $ReflectModel -ne '') {
            if ($Mode -ne 'gepa') { Fail '-ReflectModels and -ReflectModel apply to -Mode gepa only' }
            if ($ReflectModels -eq '') { $ReflectModels='local' }
            $arguments+=@('--reflect-models',$ReflectModels)
            if ($ReflectModel -ne '') { $arguments+=@('--reflect-model',$ReflectModel) }
        }
        if ($SpeedWeight -ge 0 -or $Goal -ne '') {
            if ($Mode -ne 'gepa') { Fail '-SpeedWeight and -Goal apply to -Mode gepa only' }
            if ($SpeedWeight -ge 0) { $arguments+=@('--speed-weight',"$SpeedWeight") }
            if ($Goal -ne '') { $arguments+=@('--goal',$Goal) }
        }
        Write-Host "starting $Mode (cycles $Cycles, hours $Hours, requests $Requests): $Note"
    }
    Write-Host "record: $record"
    & $python @arguments 2>&1 | Tee-Object -FilePath $record
    $exit=$LASTEXITCODE
    Write-Host "practice command exit code $exit"
    if ($exit -eq 0) { & $python (Join-Path $root 'tools\clean_test_runs.py') --engine-sandboxes --apply 2>&1 | Write-Host }
} finally {
    if ($sampler) { Stop-Job $sampler -ErrorAction SilentlyContinue; Remove-Job $sampler -Force -ErrorAction SilentlyContinue }
    # 7. Memory back. Only a model this run loaded is unloaded; a model that was already loaded may belong to another run.
    if ($ownLoad -and -not $KeepLoaded -and -not $remote) {
        Write-Host "unloading $Model"
        lms unload $Model 2>&1 | Select-Object -Last 1 | Write-Host
    }
}
exit $exit
