#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「每日免费模型」订阅，转成 WorkBuddy / DeepSeek Harness(DSH) 的原生导入文件。

设计参考（已在 GitHub 上验证可行的方案）：
  - ow-bridge        : 把模型写进 ~/.workbuddy/models.json（vendor=Custom + url + apiKey）
  - dsh-free-models  : 往 ~/.dsh/settings.yaml 注入一个 provider 块（FCC 本地代理，openai-responses）

本脚本只负责「生成两种 harness 的原生配置文件 + 幂等安装脚本」，
传输层复用成熟的本地聚合代理（WorkBuddy 侧建议 OpenCode，DSH 侧建议 Free Claude Code）。

用法: python3 to_harness.py
依赖: 仅标准库
"""
import json
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/dearloyal/free-models/main/%E5%85%8D%E8%B4%B9%E6%A8%A1%E5%9E%8B.json"

# DSH 侧复用 Free Claude Code(FCC) 本地代理的固定 schema（来源 dsh-free-models，已验证）
FCC_PORT = 8082
FCC_PROVIDER = "free-models"
FCC_TOKEN_ENV = "FCC_DSH_API_KEY"

# WorkBuddy 侧：HF 模型走本地 Ollama 的 OpenAI 兼容端点；API 类免费模型走可配置代理
OLLAMA_URL = "http://localhost:11434/v1"
PROXY_URL_ENV = "${WORKBUDDY_PROXY_URL:-http://127.0.0.1:%d/v1}" % FCC_PORT

# DSH 默认已知可用的免费 provider（与 dsh-free-models 对齐；订阅里若发现新的会追加）
DEFAULT_DSH_MODELS = [
    ("gemini/models/gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite (free)", 1048576, 65536),
    ("open_router/openrouter/free", "OpenRouter Free (free)", 262144, 65536),
    ("github_models/openai/gpt-4.1", "GitHub Models GPT-4.1 (free)", 262144, 65536),
    ("groq/llama-3.3-70b-versatile", "Groq Llama 3.3 70B (free)", 131072, 32768),
    ("nvidia_nim/nvidia/nemotron-3-super-120b-a12b", "NVIDIA NIM Nemotron 3 Super (free)", 200000, 65536),
    ("zai_api/glm-4.7-flash", "GLM-4.7-Flash (free, 200K ctx)", 200000, 32768),
]


def fetch():
    with urllib.request.urlopen(URL, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def slugify(s: str) -> str:
    out = []
    for ch in s.lower():
        out.append(ch if ch.isalnum() else "-")
    return "-".join("".join(out).split("-"))


def build_workbuddy(sites):
    """生成 WorkBuddy 原生 models.json（含 availableModels）。"""
    models = []
    for s in sites:
        src = s.get("_source", "")
        name = s.get("name", "")
        lic = s.get("_license", "") or ""
        if src == "huggingface" and "huggingface.co/" in s["api"]:
            hf_id = s["api"].split("huggingface.co/")[-1].strip("/")
            mid = f"ollama/{hf_id.split('/')[-1]}"
            models.append({
                "id": mid, "name": f"{name} (free-models·hf)",
                "vendor": "Custom", "url": OLLAMA_URL, "apiKey": "ollama",
                "supportsToolCall": False, "supportsImages": False,
                "buddyBridgeOwner": "free-models",
            })
        elif src == "freelist":
            mid = f"proxy/{slugify(name)}"
            models.append({
                "id": mid, "name": f"{name} (free-models·api)",
                "vendor": "Custom", "url": PROXY_URL_ENV, "apiKey": "freecc",
                "supportsToolCall": True, "supportsImages": False,
                "buddyBridgeOwner": "free-models",
            })
    return {"models": models, "availableModels": [m["id"] for m in models]}


WB_INSTALL = r'''#!/bin/sh
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
'''


def build_dsh(sites):
    """生成 DSH 的 provider 块（FCC 代理 schema）。订阅里发现的新免费 provider 会追加。"""
    models = list(DEFAULT_DSH_MODELS)
    seen = {m[0] for m in models}
    for s in sites:
        if s.get("_source") == "freelist":
            mid = f"freeapi/{slugify(s['name'])}"
            if mid not in seen:
                seen.add(mid)
                models.append((mid, f"{s['name']} (free-models)", 200000, 32768))
    block = [f"    # >>> free-models-provider >>>",
             f"    {FCC_PROVIDER}:",
             f"      displayName: Free Models (daily)",
             f"      api: openai-responses",
             f"      baseURL: http://127.0.0.1:{FCC_PORT}/v1",
             f"      apiKeyEnv: {FCC_TOKEN_ENV}",
             f"      retryPolicy:",
             f"        mode: normal",
             f"        maxRetries: 0",
             f"      models:"]
    for mid, name, ctx, mtok in models:
        block.append(f"        - id: {mid}")
        block.append(f"          name: {name}")
        block.append(f"          contextWindow: {ctx}")
        block.append(f"          maxTokens: {mtok}")
    block.append(f"    # <<< free-models-provider <<<")
    return "\n".join(block), len(models)


DSH_INSTALL = r'''#!/bin/sh
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
'''


def main():
    data = fetch()
    sites = data.get("sites", [])
    out = Path(".")

    wb = build_workbuddy(sites)
    (out / "workbuddy_models.json").write_text(json.dumps(wb, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "import_workbuddy.sh").write_text(WB_INSTALL, encoding="utf-8")

    dsh_block, n = build_dsh(sites)
    (out / "dsh_provider.yaml").write_text(
        "# Free Models provider block for DeepSeek Harness (dsh-llm-pi-ai)\n"
        "# 由 to_harness.py 从每日订阅自动生成；配合 Free Claude Code 本地代理(:%d)使用\n\n" % FCC_PORT
        + dsh_block + "\n", encoding="utf-8")
    (out / "import_dsh.sh").write_text(DSH_INSTALL, encoding="utf-8")

    # 保留原有 Ollama 拉取脚本
    ollama = [s for s in sites if s.get("_source") == "huggingface" and "huggingface.co/" in s["api"]]
    with open(out / "ollama_pull.sh", "w", encoding="utf-8") as f:
        f.write("# 本地 Ollama 拉取免费模型（HF 源）\n# 用法: bash ollama_pull.sh\n\n")
        for s in ollama:
            hf_id = s["api"].split("huggingface.co/")[-1].strip("/")
            f.write(f"# {s['name']}  ({s.get('_license')})\nollama pull {hf_id}\n\n")

    print(f"已生成: workbuddy_models.json({len(wb['models'])}条) | dsh_provider.yaml({n}条) | ollama_pull.sh({len(ollama)}条)")
    print("导入: bash import_workbuddy.sh  /  bash import_dsh.sh")


if __name__ == "__main__":
    main()
