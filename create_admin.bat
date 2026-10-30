@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3 and enable Add Python to PATH.
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Could not install dependencies. Check your internet connection or install requirements manually.
  pause
  exit /b 1
)
python create_admin.py
pause
