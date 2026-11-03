#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免费模型一键导入 (直连云端版)

用法:
  python3 oneclick.py --key sk-or-v1-xxxx      # 导入 WorkBuddy（推荐，云端直连）
  python3 oneclick.py --key sk-or-v1-xxxx --dsh # 同时导入 DSH
  python3 oneclick.py --list                    # 只看真实免费模型，不导入

为什么需要 key:
  OpenRouter 的免费模型是云端服务，必须用一个免费 API key 才能调用。
  免费注册: https://openrouter.ai/keys  (无需信用卡, 1 分钟)
  拿到后设置环境变量 OPENROUTER_API_KEY, 或用 --key 传入。
  这是"能真正跑起来"的最省事方式: 不用显卡、不用装 Ollama/代理。

数据来源: 仓库里的 免费模型.json (OpenRouter 官方 API 抓的真实模型)
依赖: 仅 Python 标准库
幂等: 重跑不会重复
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
OLLAMA_URL = "http://localhost:11434/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def fetch():
    if LOCAL.exists():
        data = json.loads(LOCAL.read_text(encoding="utf-8"))
        src = "本地 免费模型.json"
    else:
        try:
            req = urllib.request.Request(SUB_URL, headers={"User-Agent": "free-models-oneclick"})
            data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
            src = "远程订阅"
        except Exception as e:
            print("✗ 无法获取订阅数据:", e)
            sys.exit(1)
    n = data.get("count", len(data.get("sites", [])))
    print(f"已加载订阅 ({src}): {n} 个模型")
    return data


def classify(s):
    """返回 (wb, dsh, provider, base_url, model)"""
    wb, dsh = s.get("_wb"), s.get("_dsh")
    prov = s.get("_provider") or ""
    base = s.get("_base_url") or ""
    model = s.get("_model") or ""
    if wb is None or dsh is None:
        src = s.get("_source", "")
        if src == "openrouter":
            return True, True, "openrouter", OPENROUTER_BASE, model
        if src == "huggingface" and "huggingface.co/" in s.get("api", ""):
            return True, True, "ollama", OLLAMA_URL, ""
        return False, False, "", "", ""
    return bool(wb), bool(dsh), prov, base, model


# ----------------------------- WorkBuddy -----------------------------
def import_workbuddy(data, key):
    entries, n_or = [], 0
    for s in data.get("sites", []):
        wb, _, prov, base, model = classify(s)
        if not wb:
            continue
        name = s.get("name", "")
        if prov == "openrouter":
            mid = f"openrouter/{model}"
            url, api_key, tool = OPENROUTER_BASE, key or "", True
            n_or += 1
        elif prov == "ollama":
            hf = s.get("api", "").split("huggingface.co/")[-1].strip("/")
            mid = f"ollama/{hf.split('/')[-1]}"
            url, api_key, tool = OLLAMA_URL, "ollama", False
        else:
            continue
        entries.append({
            "id": mid, "name": f"{name} (free)", "vendor": "Custom",
            "url": url, "apiKey": api_key, "supportsToolCall": tool,
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
    print(f"✓ WorkBuddy 写入 {len(entries)} 条 → {target}")
    if n_or and not key:
        print("  ⚠ 未提供 OpenRouter key，这些模型暂时调不通。")
        print("    去 https://openrouter.ai/keys 免费创建，然后重跑:")
        print("    python3 oneclick.py --key sk-or-v1-xxxx")
    return len(entries)


# ----------------------------- DSH -----------------------------
def _inject_dsh_provider(key, display, api, base_url, api_key_env, models, marker):
    dsh_home = os.environ.get("DSH_HOME", os.path.expanduser("~/.dsh"))
    settings = os.path.join(dsh_home, "settings.yaml")
    os.makedirs(dsh_home, exist_ok=True)
    lines = [f"    # >>> {marker} >>>", f"    {key}:", f"      displayName: {display}",
             f"      api: {api}", f"      baseURL: {base_url}", f"      apiKeyEnv: {api_key_env}",
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
    or_models = []
    for s in data.get("sites", []):
        _, dsh, prov, base, model = classify(s)
        if dsh and prov == "openrouter" and model:
            or_models.append((model, f"{model} (free)", s.get("_context_length") or 131072, 32768))
    if not or_models:
        print("  (订阅里暂无 OpenRouter 免费模型，DSH 跳过)")
        return {}
    status = _inject_dsh_provider(
        "free-models", "Free Models (OpenRouter)", "openai", OPENROUTER_BASE,
        "OPENROUTER_API_KEY", or_models, "free-models-provider")
    print(f"✓ DSH provider {'已注入' if status == 'injected' else '已存在(跳过)'}"
          f" → ~/.dsh/settings.yaml (key=free-models)")
    print("  提示: DSH 从环境变量 OPENROUTER_API_KEY 读 key，请先 export 好。")
    return {"dsh": status}


# ----------------------------- 入口 -----------------------------
def parse_key(args):
    for i, a in enumerate(args):
        if a == "--key" and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--key="):
            return a.split("=", 1)[1]
    return os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_KEY")


def main():
    args = sys.argv[1:]
    mode = "wb"
    if "--dsh" in args:
        mode = "dsh"
    if "--both" in args:
        mode = "both"
    if "--list" in args:
        mode = "list"
    key = parse_key(args)
    data = fetch()

    if mode == "list":
        ors = [s for s in data.get("sites", []) if classify(s)[2] == "openrouter"]
        hfs = [s for s in data.get("sites", []) if classify(s)[2] == "ollama"]
        print(f"\nOpenRouter 真实免费模型: {len(ors)} 个（云端直连，需免费 key）")
        for s in ors:
            print("  •", s.get("_model"), f"| ctx {s.get('_context_length') or '?'}")
        if hfs:
            print(f"\nHugging Face 模型: {len(hfs)} 个（需本地 Ollama）")
            for s in hfs[:8]:
                print("  •", s.get("name"))
        return

    if mode in ("wb", "both"):
        import_workbuddy(data, key)
    if mode in ("dsh", "both"):
        import_dsh(data)
    print("\n完成。重跑幂等，不会重复写入。")


if __name__ == "__main__":
    main()
