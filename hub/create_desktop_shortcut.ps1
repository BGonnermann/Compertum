$ErrorActionPreference='Stop'
$projectFolder=Split-Path -Parent $PSScriptRoot
$launcher=Join-Path $PSScriptRoot 'launch.py'
$python=(Get-Command python -ErrorAction Stop).Source
$desktopFolder=[Environment]::GetFolderPath('Desktop')
$shortcutPath=Join-Path $desktopFolder 'Compertum Hub.lnk'
$shell=New-Object -ComObject WScript.Shell
$arguments='-B "{0}"' -f $launcher
if (Test-Path -LiteralPath $shortcutPath) {
    $existing=$shell.CreateShortcut($shortcutPath)
    if ($existing.TargetPath -ne $python -or $existing.Arguments -ne $arguments) {
        throw 'A different desktop shortcut already uses this name. It was preserved.'
    }
}
$shortcut=$shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath=$python
$shortcut.Arguments=$arguments
$shortcut.WorkingDirectory=$projectFolder
$shortcut.Description='Open the local read-only Compertum Hub.'
$shortcut.WindowStyle=7
$shortcut.Save()
$saved=$shell.CreateShortcut($shortcutPath)
if ($saved.TargetPath -ne $python -or $saved.Arguments -ne $arguments -or $saved.WorkingDirectory -ne $projectFolder) {
    throw 'The saved desktop shortcut did not match its intended target.'
}
[pscustomobject]@{Path=$shortcutPath;Target=$saved.TargetPath;Arguments=$saved.Arguments;WorkingDirectory=$saved.WorkingDirectory}
