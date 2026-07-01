$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "Dify Finance Radar"
$ScriptPath = Join-Path $ProjectDir "run_scheduled_update.ps1"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -ProjectDir `"$ProjectDir`""

$Trigger1020 = New-ScheduledTaskTrigger -Daily -At "10:20"
$Trigger1300 = New-ScheduledTaskTrigger -Daily -At "13:00"
$Trigger1600 = New-ScheduledTaskTrigger -Daily -At "16:00"
$Triggers = @($Trigger1020, $Trigger1300, $Trigger1600)

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Triggers `
    -Settings $Settings `
    -Description "Collect market/news data, run Dify workflow, and send Telegram report." `
    -Force

Write-Host "Registered task: $TaskName"
Write-Host "Schedule: 10:20, 13:00, 16:00 daily"
