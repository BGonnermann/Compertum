<#
.SYNOPSIS
Start tools\practice.ps1 as a process of its own, so the run outlives the window or session that started it.

.DESCRIPTION
Owner-started only, one run per call; nothing here repeats or schedules. The process is created through the Windows
process service, outside the caller's job, so closing the caller does not end the run. The process starts with a hidden window
(owner, 29 October 2026: the blank terminal tab was the run itself; closing it killed nothing yet, but could). Console output goes to a log
file next to the run record. The kill switch is unchanged: New-Item state\engine\STOP.

.EXAMPLE
tools\start_run.ps1 -Models deepseek -Model deepseek-flash -Mode bench -BenchSet bench-3 -CyclesPerMarket 4 -Requests 2000 -Note "bench-3 flash baseline"
#>
param([switch]$Show,[Parameter(ValueFromRemainingArguments=$true)][string[]]$PracticeArguments)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if (-not $PracticeArguments) { Write-Host 'STOP: give the practice.ps1 arguments'; exit 2 }
if ($PracticeArguments -contains '-Pick') { Write-Host 'STOP: -Pick needs a console; give -Model instead'; exit 2 }
if ($PracticeArguments | Where-Object { $_ -match '["\r\n]' }) { Write-Host 'STOP: an argument holds a double quote or a line break'; exit 2 }
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$log=Join-Path $root ".cache\test-runs\practice-detached-$stamp.log"
$quoted=($PracticeArguments | ForEach-Object { if ($_ -match '^-[A-Za-z]') { $_ } else { "'"+$_.Replace("'","''")+"'" } }) -join ' '
$script=Join-Path $root 'tools\practice.ps1'
$command="& '$script' $quoted *>&1 | Out-File -FilePath '$log' -Encoding utf8"
$pwsh=(Get-Process -Id $PID).Path
$line="`"$pwsh`" -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command `"$command`""
if ($Show) { Write-Host $line; exit 0 }
$startup=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
$result=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$line;CurrentDirectory=$root;ProcessStartupInformation=$startup}
if ($result.ReturnValue -ne 0) { Write-Host "STOP: process creation returned $($result.ReturnValue)"; exit 2 }
Write-Host "started process $($result.ProcessId); console output: $log"
Write-Host 'stop: New-Item state\engine\STOP'
