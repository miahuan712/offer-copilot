@echo off
chcp 65001 >nul
cd /d "%~dp0"
title OfferCopilot - http://127.0.0.1:8500
echo ============================================================
echo   OfferCopilot  秋招工作台
echo   访问地址: http://127.0.0.1:8500
echo   停止: 在本窗口按 Ctrl+C
echo ============================================================
echo.

REM ===== 1. 检查 Python =====
python --version >nul 2>&1
if errorlevel 1 (
  echo [错误] 未检测到 Python 命令。
  echo   请安装 Python 3.10 或更高版本，安装时勾选 "Add python.exe to PATH"。
  echo   下载地址: https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

REM ===== 2. 检查并自动安装依赖（首次运行会自动安装）=====
python -c "import uvicorn, fastapi, pydantic, reportlab" >nul 2>&1
if errorlevel 1 (
  echo [提示] 首次运行，正在安装依赖（可能需要几分钟，请稍候）...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败，请检查网络后重试，或手动执行：
    echo   python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
  )
  echo [完成] 依赖安装完成。
  echo.
)

REM ===== 3. 启动服务 =====
echo 正在启动服务，浏览器将自动打开 http://127.0.0.1:8500 ...
start "" /min cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8500"
set PYTHONUNBUFFERED=1
python -m uvicorn app:app --host 127.0.0.1 --port 8500

echo.
echo [提示] 服务已退出。若为启动失败，常见原因：
echo   - 端口 8500 被占用（关闭占用它的程序后重试）
echo   - 依赖缺失（重新运行本脚本会自动补装）
echo.
pause