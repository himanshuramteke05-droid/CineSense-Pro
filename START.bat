@echo off
cd /d "%~dp0"
title CineSense launcher

REM 1) Python environment: reuse C:\movie-venv if it exists, otherwise create one inside this folder
if exist "C:\movie-venv\Scripts\activate.bat" (
  call "C:\movie-venv\Scripts\activate.bat"
) else (
  if not exist venv python -m venv venv
  call venv\Scripts\activate.bat
)

REM 2) Packages (quick if already installed)
python -m pip install -q -r requirements.txt || echo Could not check packages (offline?). Continuing...

REM 3) One-time setup: keys + movie index
python first_run.py
if errorlevel 1 (
  pause
  exit /b 1
)

REM 4) AI service (separate window), then wait until it is ready
start "CineSense AI service" cmd /k python -m uvicorn ai_service:app --port 8001
echo Loading the AI model, please wait...
set /a tries=0
:wait
curl -s -o nul http://127.0.0.1:8001/health
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% geq 60 (
  echo The AI service did not start. Look at the "CineSense AI service" window for the error.
  pause
  exit /b 1
)
timeout /t 3 >nul
goto wait

:ready
REM 5) Website
start "" http://127.0.0.1:8000
python -m uvicorn server:app --port 8000
pause
