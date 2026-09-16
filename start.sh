#!/usr/bin/env bash
# OfferCopilot 启动脚本（macOS / Linux）
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  OfferCopilot  秋招工作台"
echo "  访问地址: http://127.0.0.1:8500"
echo "  停止: 按 Ctrl+C"
echo "============================================================"
echo

# 1. 检查 Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "[错误] 未检测到 python3，请先安装 Python 3.10+。"
  exit 1
fi

# 2. 检查并自动安装依赖（首次运行会自动安装）
if ! python3 -c "import uvicorn, fastapi, pydantic, reportlab" >/dev/null 2>&1; then
  echo "[提示] 首次运行，正在安装依赖（可能需要几分钟）..."
  python3 -m pip install -r requirements.txt
  echo "[完成] 依赖安装完成。"
  echo
fi

# 3. 启动服务并打开浏览器
echo "正在启动服务，浏览器将自动打开 http://127.0.0.1:8500 ..."
( sleep 3; python3 -c "import webbrowser; webbrowser.open('http://127.0.0.1:8500')" >/dev/null 2>&1 ) &
python3 -m uvicorn app:app --host 127.0.0.1 --port 8500