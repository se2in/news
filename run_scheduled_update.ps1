param(
    [string]$ProjectDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $ProjectDir

$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$Config = Join-Path $ProjectDir "config.json"
if (-not (Test-Path -LiteralPath $Config)) {
    $Config = Join-Path $ProjectDir "config.example.json"
}

$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "finance_radar_$Stamp.log"

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python ".\finance_radar.py" run --config $Config --send-dify --send-telegram *> $LogFile
$RunExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
if ($RunExitCode -ne 0) {
    throw "finance_radar.py failed with exit code $RunExitCode. See log: $LogFile"
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python ".\export_github_pages.py" *>> $LogFile
$ExportExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
if ($ExportExitCode -ne 0) {
    throw "export_github_pages.py failed with exit code $ExportExitCode. See log: $LogFile"
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
git add docs\earnings.json docs\news.json *>> $LogFile
$GitAddExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
if ($GitAddExitCode -ne 0) {
    throw "git add failed with exit code $GitAddExitCode. See log: $LogFile"
}

git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    git commit -m "Update earnings dashboard data" *>> $LogFile
    $GitCommitExitCode = $LASTEXITCODE
    git push *>> $LogFile
    $GitPushExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousErrorActionPreference
    if ($GitCommitExitCode -ne 0) {
        throw "git commit failed with exit code $GitCommitExitCode. See log: $LogFile"
    }
    if ($GitPushExitCode -ne 0) {
        throw "git push failed with exit code $GitPushExitCode. See log: $LogFile"
    }
} else {
    "GitHub Pages dashboard already up to date." | Out-File -FilePath $LogFile -Append -Encoding utf8
}
