@echo off
setlocal
cd /d "%~dp0"
python export_github_pages.py
if errorlevel 1 (
  echo Failed to export GitHub Pages dashboard.
  pause
  exit /b 1
)
echo.
echo docs\index.html and docs\earnings.json are ready for GitHub Pages.
echo Commit and push the docs folder, then enable GitHub Pages from the docs folder.
pause
