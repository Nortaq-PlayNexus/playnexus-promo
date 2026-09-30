# PlayNexus promo pipeline — run `python -m playnexus run` every 15 minutes.
#
#   powershell -ExecutionPolicy Bypass -File .\schedule.ps1 -Install
#   powershell -ExecutionPolicy Bypass -File .\schedule.ps1 -Uninstall
#   powershell -ExecutionPolicy Bypass -File .\schedule.ps1 -Status
#
# `run` is safe to invoke unattended: it only publishes posts whose channel is in
# `auto` mode, only inside that channel's configured hours, and only within its
# daily cap. Community channels are never touched here.

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [int]$Minutes = 15
)

$ErrorActionPreference = 'Stop'
$TaskName = 'PlayNexus-Promo'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { throw 'python not found on PATH' }
$Logs = Join-Path $ProjectDir 'data'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$RunCmd = "-NoProfile -Command `"& '$Python' -m playnexus run *>> '$Logs\run.log'`""

if ($Status) {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue |
        Select-Object TaskName, State, TaskPath | Format-List
    if (Test-Path (Join-Path $Logs 'run.log')) {
        Write-Host "`n--- last 20 lines of run.log ---" -ForegroundColor DarkGray
        Get-Content (Join-Path $Logs 'run.log') -Tail 20
    }
    return
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'." -ForegroundColor Yellow
    return
}

if ($Install) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $RunCmd -WorkingDirectory $ProjectDir
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
        -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Description 'PlayNexus promo pipeline: publish due auto-mode posts' `
        -Force | Out-Null
    Write-Host "Installed '$TaskName': runs every $Minutes minute(s) in $ProjectDir" -ForegroundColor Green
    Write-Host "Logs: $(Join-Path $Logs 'run.log')" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Reminder: community channels are approval-gated, so this task will" -ForegroundColor Yellow
    Write-Host "never post to Reddit/HN on its own. Review with: python -m playnexus review" -ForegroundColor Yellow
    return
}

Write-Host "Usage: .\schedule.ps1 [-Install|-Uninstall|-Status] [-Minutes 15]" -ForegroundColor Cyan
