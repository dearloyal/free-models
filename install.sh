#!/usr/bin/env bash
# 一键拉取并运行「每日免费模型」导入器 (macOS / Linux)
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/dearloyal/free-models/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --both     # 传参给 oneclick.py
set -euo pipefail
REPO="https://github.com/dearloyal/free-models.git"
DIR="${FREE_MODELS_DIR:-$HOME/free-models}"

if [ -d "$DIR/.git" ]; then
  echo "→ 更新已有仓库: $DIR"
  git -C "$DIR" pull --ff-only
else
  echo "→ 克隆到: $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi

cd "$DIR"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "✗ 未找到 Python，请先安装 Python 3 (https://www.python.org/downloads/)"
  exit 1
fi
echo "→ 运行一键导入"
exec "$PY" oneclick.py "$@"
