#!/bin/zsh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$APP_DIR/.venv/bin/python"
LOCAL_DATA_DIR="$APP_DIR/.local-demo"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "未找到项目虚拟环境：$PYTHON_BIN"
  echo "首次使用请先在此目录执行：python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  read -r "REPLY?按回车键关闭窗口。"
  exit 1
fi

mkdir -p "$LOCAL_DATA_DIR/private"
export POCKETBAY_PRIVATE_DIR="$LOCAL_DATA_DIR/private"

PORT="$("$PYTHON_BIN" -c 'import socket; sock = socket.socket(); sock.bind(("127.0.0.1", 0)); print(sock.getsockname()[1]); sock.close()')"
APP_URL="http://127.0.0.1:$PORT"

cd "$APP_DIR"
"$PYTHON_BIN" dashboard_server.py \
  --db "$LOCAL_DATA_DIR/data.sqlite3" \
  --token-db "$LOCAL_DATA_DIR/token.sqlite3" \
  --port "$PORT" &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

attempt=0
while (( attempt < 40 )); do
  if /usr/bin/curl -fsS "$APP_URL/api/auth/me" >/dev/null 2>&1; then
    /usr/bin/open "$APP_URL/workspace.html"
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    wait "$SERVER_PID"
    exit 1
  fi
  sleep 0.25
  (( attempt += 1 ))
done

if (( attempt == 40 )); then
  echo "服务未能在预期时间内启动。"
  exit 1
fi

echo "服务运行中：$APP_URL"
echo "按 Control+C 停止服务。"
wait "$SERVER_PID"
