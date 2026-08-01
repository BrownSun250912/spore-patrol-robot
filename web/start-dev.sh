#!/usr/bin/env bash
# 启动开发服务器（Ubuntu）
# 用法：./start-dev.sh    —— 前台运行，Ctrl+C 停止
# 首次使用前先执行 npm install
set -e
cd "$(dirname "$0")"
if [ ! -d node_modules ]; then
  echo "未找到 node_modules，先执行 npm install ..."
  npm install --no-audit --no-fund
fi
echo "启动开发服务器: http://localhost:3000"
exec npm run dev
