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

& $Python ".\finance_radar.py" run --config $Config --send-dify --send-telegram *> $LogFile
& $Python ".\export_github_pages.py" *>> $LogFile

git add docs\earnings.json *>> $LogFile
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "Update earnings dashboard data" *>> $LogFile
    git push *>> $LogFile
} else {
    "GitHub Pages dashboard already up to date." | Out-File -FilePath $LogFile -Append -Encoding utf8
}
