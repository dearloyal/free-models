#!/bin/sh
# 幂等注入 free-models provider 块到 ~/.dsh/settings.yaml
set -eu
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
SETTINGS="$DSH_HOME/settings.yaml"
mkdir -p "$DSH_HOME"
MARKER="free-models-provider"
if [ -f "$SETTINGS" ] && grep -q "$MARKER" "$SETTINGS"; then
  echo "[skip] provider 块已存在"
  exit 0
fi
BLOCK_FILE="$(mktemp)"
python3 - "$SCRIPT_DIR/dsh_provider.yaml" "$BLOCK_FILE" <<'PY'
import sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
open(sys.argv[2], "w").write("\n".join(lines) + "\n")
PY
if [ ! -f "$SETTINGS" ] || ! grep -q "^llm-pi-ai:" "$SETTINGS"; then
  { [ -f "$SETTINGS" ] && cat "$SETTINGS"; printf '\nllm-pi-ai:\n  providers:\n'; cat "$BLOCK_FILE"; } > "$SETTINGS.tmp"
else
  awk -v bf="$BLOCK_FILE" '
    /^llm-pi-ai:/ { in_llm=1 }
    in_llm && /^  providers:/ && !done { print; while ((getline l < bf) > 0) print l; close(bf); done=1; next }
    { print }' "$SETTINGS" > "$SETTINGS.tmp"
fi
mv "$SETTINGS.tmp" "$SETTINGS"
rm -f "$BLOCK_FILE"
echo "[ok] 已注入 free-models provider 到 $SETTINGS"
