@echo off
chcp 65001 >nul
cd /d "%~dp0"
title OfferCopilot - http://127.0.0.1:8500
echo ============================================================
echo   OfferCopilot  http://127.0.0.1:8500
echo   日志: workbench.log   停止: 在本窗口按 Ctrl+C
echo ============================================================
set PYTHONUNBUFFERED=1
start "" /min cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8500"
powershell -NoProfile -Command "python -m uvicorn app:app --host 127.0.0.1 --port 8500 2>&1 | Tee-Object -FilePath workbench.log"
