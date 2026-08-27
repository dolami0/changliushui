#!/bin/bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

PORT="${DEPLOY_RUN_PORT:-5000}"

# 使用 serve 提供静态文件服务
exec npx serve dist -l "tcp://0.0.0.0:$PORT" -n -s
