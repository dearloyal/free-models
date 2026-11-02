#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把免费模型订阅转成 harness 可直接消费的格式。
用法: python3 to_harness.py
依赖: 仅标准库

产出（当前目录）:
  - ollama_pull.sh          : 本地 Ollama 一键拉取 Hugging Face 模型
  - litellm_model_list.yaml : LiteLLM / 任意 OpenAI 兼容 harness 的模型清单模板
"""
import json
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/dearloyal/free-models/main/%E5%85%8D%E8%B4%B9%E6%A8%A1%E5%9E%8B.json"


def fetch():
    with urllib.request.urlopen(URL, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    data = fetch()
    sites = data.get("sites", [])
    out = Path(".")

    # ---- Ollama：仅取 Hugging Face 源的模型 ----
    ollama = [s for s in sites if s.get("_source") == "huggingface" and "huggingface.co/" in s["api"]]
    with open(out / "ollama_pull.sh", "w", encoding="utf-8") as f:
        f.write("# 本地 Ollama 拉取免费模型（HF 源）\n")
        f.write("# 用法: bash ollama_pull.sh\n\n")
        for s in ollama:
            hf_id = s["api"].split("huggingface.co/")[-1]
            f.write(f"# {s['name']}  ({s.get('_license')})\n")
            f.write(f"ollama pull {hf_id}\n\n")

    # ---- LiteLLM：免费 API 提供方（freelist 源）模板 ----
    providers = {}
    for s in sites:
        if s.get("_source") == "freelist":
            providers[s["name"]] = s["api"]
    with open(out / "litellm_model_list.yaml", "w", encoding="utf-8") as f:
        f.write("# LiteLLM / OpenAI 兼容 harness 模型清单模板\n")
        f.write("# 把 base_url + api_key 补全后，harness 即可调用这些免费模型\n")
        f.write("model_list:\n")
        for name, link in list(providers.items())[:30]:
            f.write(f"  # {name}  -> 免费档说明: {link}\n")
            f.write(f"  - model_name: {name}\n")
            f.write(f"    litellm_params:\n")
            f.write(f"      model: openai/<该提供方上的模型名>\n")
            f.write(f"      api_base: <填该提供方的 OpenAI 兼容 base_url>\n")
            f.write(f"      api_key: os.environ/{name.upper().replace(' ', '_')}_KEY\n\n")

    print(f"已生成 ollama_pull.sh（{len(ollama)} 条 HF 模型）与 litellm_model_list.yaml（{len(providers)} 个免费 API 提供方）")


if __name__ == "__main__":
    main()
