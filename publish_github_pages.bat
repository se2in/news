@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" "%~dp0export_github_pages.py"
if errorlevel 1 (
  echo Failed to export GitHub Pages dashboard.
  pause
  exit /b 1
)

git add docs\earnings.json docs\news.json
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Update earnings dashboard data"
  git push
  if errorlevel 1 (
    echo Failed to push GitHub Pages dashboard.
    pause
    exit /b 1
  )
) else (
  echo GitHub Pages dashboard already up to date.
)

echo.
echo GitHub Pages dashboard is updated.
pause
