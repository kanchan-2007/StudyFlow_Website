@echo off
title Smart Study Planner
cd /d "%~dp0"
echo ==========================================
echo   Smart Study Planner - Local Web App
echo ==========================================
where py >nul 2>nul
if %errorlevel%==0 (
  set PYTHON=py
) else (
  set PYTHON=python
)
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Could not install dependencies. Check that Python and internet access are available.
  pause
  exit /b 1
)
echo.
echo Starting website at http://127.0.0.1:5000
echo Keep this window open while using the website.
%PYTHON% app.py
pause
