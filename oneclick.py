#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免费模型一键导入 (OW Bridge 风格极简版)

用法 (任选其一):
  python3 oneclick.py            # 把当天所有可用免费模型一键导入 WorkBuddy
  python3 oneclick.py --dsh      # 导入到 DeepSeek Harness (DSH)
  python3 oneclick.py --both     # WorkBuddy + DSH 都导入
  python3 oneclick.py --list     # 只看分类，不导入

数据来源: 优先用仓库里的 免费模型.json, 没有就联网拉最新订阅
依赖: 仅 Python 标准库 (WorkBuddy 路径零依赖; DSH 路径也是纯文本注入)
幂等: 重跑不会重复, 只动本工具标记的条目
"""
import sys
import os
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "免费模型.json"
SUB_URL = "https://raw.githubusercontent.com/dearloyal/free-models/main/%E5%85%8D%E8%B4%B9%E6%A8%A1%E5%9E%8B.json"

OWNER = "free-models-importer"
FCC_PORT = 8082
OLLAMA_URL = "http://localhost:11434/v1"
PROXY_URL = f"http://127.0.0.1:{FCC_PORT}/v1"


# ----------------------------- 数据 -----------------------------
def fetch():
    if LOCAL.exists():
        data = json.loads(LOCAL.read_text(encoding="utf-8"))
        src = "本地 免费模型.json"
    else:
        try:
            req = urllib.request.Request(SUB_URL, headers={"User-Agent": "free-models-oneclick"})
            data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
            src = "远程订阅最新版"
        except Exception as e:
            print("✗ 无法获取订阅数据:", e)
            sys.exit(1)
    n = data.get("count", len(data.get("sites", [])))
    print(f"已加载订阅 ({src}): {n} 个模型")
    return data


def slugify(s):
    return "-".join("".join(c if c.isalnum() else "-" for c in s.lower()).split("-"))


def classify(s):
    wb, dsh = s.get("_wb"), s.get("_dsh")
    if wb is None or dsh is None:
        src = s.get("_source", "")
        if src == "huggingface" and "huggingface.co/" in s.get("api", ""):
            wb, dsh = True, True
        elif src == "freelist":
            wb, dsh = True, True
        else:
            wb, dsh = False, False
    return bool(wb), bool(dsh)


# ----------------------------- WorkBuddy -----------------------------
def import_workbuddy(data):
    entries = []
    for s in data.get("sites", []):
        wb, _ = classify(s)
        if not wb:
            continue
        src = s.get("_source", "")
        name = s.get("name", "")
        if src == "huggingface" and "huggingface.co/" in s.get("api", ""):
            hf = s["api"].split("huggingface.co/")[-1].strip("/")
            mid = f"ollama/{hf.split('/')[-1]}"
            url, key, tool = OLLAMA_URL, "ollama", False
        elif src == "freelist":
            mid = f"proxy/{slugify(name)}"
            url, key, tool = PROXY_URL, "freecc", True
        else:
            continue
        entries.append({
            "id": mid, "name": f"{name} (free-models)", "vendor": "Custom",
            "url": url, "apiKey": key, "supportsToolCall": tool,
            "supportsImages": False, "buddyBridgeOwner": OWNER,
        })
    target = os.environ.get("BUDDY_MODELS_FILE") or os.path.join(
        os.environ.get("WORKBUDDY_CONFIG_DIR", os.path.expanduser("~/.workbuddy")), "models.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    owned = {e["id"] for e in entries}
    if os.path.exists(target):
        old = json.loads(Path(target).read_text(encoding="utf-8"))
        arr = old["models"] if isinstance(old, dict) and "models" in old else (old if isinstance(old, list) else [])
        kept = [m for m in arr if m.get("buddyBridgeOwner") != OWNER and m.get("id") not in owned]
    else:
        kept = []
    merged = kept + entries
    Path(target).write_text(json.dumps(
        {"models": merged, "availableModels": [m["id"] for m in merged]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ WorkBuddy 导入 {len(entries)} 条 → {target}")
    return len(entries)


# ----------------------------- DSH -----------------------------
def _default_fcc_models(data):
    models = [
        ("gemini/models/gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite (free)", 1048576, 65536),
        ("open_router/openrouter/free", "OpenRouter Free (free)", 262144, 65536),
        ("github_models/openai/gpt-4.1", "GitHub Models GPT-4.1 (free)", 262144, 65536),
        ("groq/llama-3.3-70b-versatile", "Groq Llama 3.3 70B (free)", 131072, 32768),
        ("nvidia_nim/nvidia/nemotron-3-super-120b-a12b", "NVIDIA NIM Nemotron 3 Super (free)", 200000, 65536),
        ("zai_api/glm-4.7-flash", "GLM-4.7-Flash (free, 200K ctx)", 200000, 32768),
    ]
    seen = {m[0] for m in models}
    for s in data.get("sites", []):
        if s.get("_source") == "freelist":
            mid = f"freeapi/{slugify(s['name'])}"
            if mid not in seen:
                seen.add(mid)
                models.append((mid, f"{s['name']} (free-models)", 200000, 32768))
    return models


def _inject_dsh_provider(key, display, api, base_url, models, marker):
    dsh_home = os.environ.get("DSH_HOME", os.path.expanduser("~/.dsh"))
    settings = os.path.join(dsh_home, "settings.yaml")
    os.makedirs(dsh_home, exist_ok=True)
    lines = [f"    # >>> {marker} >>>", f"    {key}:", f"      displayName: {display}",
             f"      api: {api}", f"      baseURL: {base_url}", "      apiKeyEnv: FCC_DSH_API_KEY",
             "      retryPolicy:", "        mode: normal", "        maxRetries: 0", "      models:"]
    for mid, name, ctx, mtok in models:
        lines += [f"        - id: {mid}", f"          name: {name}",
                  f"          contextWindow: {ctx}", f"          maxTokens: {mtok}"]
    lines.append(f"    # <<< {marker} <<<")
    block = "\n".join(lines)
    content = Path(settings).read_text(encoding="utf-8") if os.path.exists(settings) else ""
    if marker in content:
        return "skipped"
    if "llm-pi-ai:" not in content:
        Path(settings + ".tmp").write_text(
            content + "\nllm-pi-ai:\n  providers:\n" + block + "\n", encoding="utf-8")
    else:
        out, done = [], False
        for line in content.splitlines():
            out.append(line)
            if line.startswith("  providers:") and not done:
                out += block.splitlines()
                done = True
        Path(settings + ".tmp").write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(settings + ".tmp", settings)
    return "injected"


def import_dsh(data):
    res = {}
    res["fcc"] = _inject_dsh_provider(
        "free-models", "Free Models (daily, API)", "openai-responses",
        f"http://127.0.0.1:{FCC_PORT}/v1", _default_fcc_models(data), "free-models-provider")
    hf = [s for s in data.get("sites", [])
          if s.get("_source") == "huggingface" and "huggingface.co/" in s.get("api", "")]
    if hf:
        ollama_models = [(f"ollama/{s['name'].split('/')[-1]}", f"{s['name']} (HF·Ollama)", 128000, 4096) for s in hf]
        res["ollama"] = _inject_dsh_provider(
            "free-models-ollama", "Free Models (HF via Ollama)", "openai",
            OLLAMA_URL, ollama_models, "free-models-ollama-provider")
    return res


# ----------------------------- 入口 -----------------------------
def main():
    args = sys.argv[1:]
    mode = "wb"
    if "--dsh" in args:
        mode = "dsh"
    if "--both" in args:
        mode = "both"
    if "--list" in args:
        mode = "list"
    data = fetch()
    if mode == "list":
        wb = [s for s in data.get("sites", []) if classify(s)[0]]
        dsh = [s for s in data.get("sites", []) if classify(s)[1]]
        print(f"\nWorkBuddy 可用: {len(wb)} 个")
        for s in wb[:8]:
            print("  •", s.get("name"), "|", s.get("_license") or "未知")
        print(f"\nDSH 可用: {len(dsh)} 个")
        for s in dsh[:8]:
            print("  •", s.get("name"), "|", s.get("_license") or "未知")
        return
    if mode in ("wb", "both"):
        n = import_workbuddy(data)
        print(f"  WorkBuddy 模型选择器现在会出现 {n} 个 free-models 模型")
    if mode in ("dsh", "both"):
        r = import_dsh(data)
        fcc = "已注入" if r.get("fcc") == "injected" else "已存在(跳过)"
        oll = ""
        if "ollama" in r:
            oll = "，Ollama " + ("已注入" if r["ollama"] == "injected" else "已存在(跳过)")
        print(f"✓ DSH provider {fcc}{oll} → ~/.dsh/settings.yaml (key=free-models)")
    print("\n完成。重跑幂等，不会重复写入。")


if __name__ == "__main__":
    main()
