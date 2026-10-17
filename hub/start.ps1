param([ValidateRange(1,65535)][int]$Port=8767)
$ErrorActionPreference='Stop'
$projectFolder=Split-Path -Parent $PSScriptRoot
$pythonCommand=Get-Command python -ErrorAction Stop
Write-Host "Open http://127.0.0.1:$Port in your browser."
Write-Host 'Keep this terminal open. Press Ctrl+C here to stop the Hub.'
& $pythonCommand.Source -B (Join-Path $PSScriptRoot 'server.py') --project-root $projectFolder --port $Port --open-browser
exit $LASTEXITCODE
