$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "Dify Finance Radar"
$ScriptPath = Join-Path $ProjectDir "run_scheduled_update.ps1"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -ProjectDir `"$ProjectDir`""

$Trigger1020 = New-ScheduledTaskTrigger -Daily -At "10:20"
$Trigger1545 = New-ScheduledTaskTrigger -Daily -At "15:45"
$Trigger2100 = New-ScheduledTaskTrigger -Daily -At "21:00"
$Triggers = @($Trigger1020, $Trigger1545, $Trigger2100)

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
Write-Host "Schedule: 10:20, 15:45, 21:00 daily"
