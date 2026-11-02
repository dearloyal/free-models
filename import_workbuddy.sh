#!/bin/sh
# 幂等导入 free-models 到 WorkBuddy：只增删本脚本 owned 的条目(buddyBridgeOwner=free-models)
set -eu
TARGET="${BUDDY_MODELS_FILE:-${WORKBUDDY_CONFIG_DIR:-$HOME/.workbuddy}/models.json}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 - "$SCRIPT_DIR/workbuddy_models.json" "$TARGET" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
new = json.load(open(src))
owned = {m["id"] for m in new["models"]}
if dst.endswith(".json") and __import__("os").path.exists(dst):
    old = json.load(open(dst))
    arr = old["models"] if isinstance(old, dict) and "models" in old else (old if isinstance(old, list) else [])
    kept = [m for m in arr if m.get("buddyBridgeOwner") != "free-models" and m.get("id") not in owned]
else:
    kept = []
merged = kept + new["models"]
doc = {"models": merged, "availableModels": [m["id"] for m in merged]}
import os
os.makedirs(os.path.dirname(dst), exist_ok=True)
json.dump(doc, open(dst, "w"), ensure_ascii=False, indent=2)
print(f"已写入 {len(new['models'])} 条 free-models 到 {dst}（保留其他 {len(kept)} 条）")
PY
