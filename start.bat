@echo off
chcp 65001 >nul
cd /d "%~dp0"
title OfferCopilot - http://127.0.0.1:8500
echo ============================================================
echo   OfferCopilot  (Autumn Recruitment Workbench)
echo   URL: http://127.0.0.1:8500     Stop: press Ctrl+C
echo ============================================================
echo.

REM ---- choose a working Python ----
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.10+ and check "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)
echo Using Python: %PY%
echo.

REM ---- check dependencies (only prompt when actually missing) ----
%PY% -c "import uvicorn, fastapi, pydantic, reportlab" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Dependencies not found. This is only needed on first run.
  choice /C YN /T 10 /D Y /M "Install dependencies now? (10s default Y=install, N=skip) "
  if not errorlevel 2 (
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
      echo.
      echo [WARN] Dependency install failed. Check network. Still trying to start...
      echo.
    )
  )
)

echo.
echo Starting server, opening http://127.0.0.1:8500 ...
start "" /min cmd /c "timeout /t 6 >nul & start http://127.0.0.1:8500"
set PYTHONUNBUFFERED=1
%PY% -m uvicorn app:app --host 127.0.0.1 --port 8500

echo.
echo [INFO] Server stopped. If startup failed, check the error above (common: port 8500 in use).
echo.
pause