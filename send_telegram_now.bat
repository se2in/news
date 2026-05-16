@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set "CONFIG_FILE=%~dp0config.json"
if not exist "%CONFIG_FILE%" set "CONFIG_FILE=%~dp0config.example.json"

"%PYTHON_EXE%" "%~dp0finance_radar.py" run --config "%CONFIG_FILE%" --send-telegram

if errorlevel 1 (
  echo.
  echo Failed to send Telegram report.
  pause
  exit /b 1
)

"%PYTHON_EXE%" "%~dp0export_github_pages.py"

if errorlevel 1 (
  echo.
  echo Telegram was sent, but GitHub Pages dashboard export failed.
  pause
  exit /b 1
)

git add docs\earnings.json docs\news.json
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Update earnings dashboard data"
  git push
  if errorlevel 1 (
    echo.
    echo Telegram was sent, but GitHub Pages dashboard push failed.
    pause
    exit /b 1
  )
) else (
  echo.
  echo GitHub Pages dashboard already up to date.
)

echo.
echo Telegram report sent and dashboard updated.
pause
