#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
free-models-importer —— 类 ow-bridge 的一键导入器（本地 Web 版）

启动: python3 app.py
打开: http://localhost:8088

功能:
  - 自动拉取每日订阅(免费模型.json)
  - 模型卡片: 许可证/类型/来源标签 + 勾选
  - 一键导入 WorkBuddy(~/.workbuddy/models.json) 或 DSH(~/.dsh/settings.yaml)
  - 可配置代理/Ollama 地址, 幂等导入(只动本工具标记条目)
参考: ow-bridge(写 models.json) / dsh-free-models(注入 provider 块)
"""
import json
import os
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, request, Response

app = Flask(__name__)

SUB_URL = "https://raw.githubusercontent.com/dearloyal/free-models/main/%E5%85%8D%E8%B4%B9%E6%A8%A1%E5%9E%8B.json"
PORT = int(os.environ.get("PORT", "8088"))
HERE = Path(__file__).resolve().parent
CACHE = HERE / "subscription_cache.json"
CONFIG_FILE = HERE / "importer_config.json"

DEFAULTS = {
    "proxy_url": "http://127.0.0.1:8082/v1",   # API 类免费模型走 FCC 等本地代理
    "ollama_url": "http://localhost:11434/v1",  # HF 模型走本地 Ollama
    "owner": "free-models-importer",
    "dsh_port": 8082,
}

CATEGORIES = {"llm": "语言", "image": "图像", "audio": "语音", "video": "视频", "multimodal": "多模态"}


# ----------------------------- 数据层 -----------------------------
def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    return cfg


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_subscription(force=False):
    if not force and CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    with urllib.request.urlopen(SUB_URL, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def slugify(s):
    out = []
    for ch in s.lower():
        out.append(ch if ch.isalnum() else "-")
    return "-".join("".join(out).split("-"))


def models_list():
    data = fetch_subscription()
    out = []
    for s in data.get("sites", []):
        out.append({
            "id": s["key"],
            "name": s.get("name", ""),
            "license": s.get("_license") or "未知",
            "category": s.get("_category", "llm"),
            "category_cn": CATEGORIES.get(s.get("_category", "llm"), s.get("_category", "")),
            "source": s.get("_source", ""),
            "tags": s.get("_tags", []),
            "description": (s.get("_description") or "")[:160],
            "endpoint": s.get("api", ""),
            "importable": s.get("_source") in ("huggingface", "freelist"),
        })
    return out


# ----------------------------- 导入逻辑 -----------------------------
def import_workbuddy(ids, cfg):
    data = fetch_subscription()
    chosen = {s["key"]: s for s in data.get("sites", []) if s["key"] in set(ids)}
    entries = []
    for s in chosen.values():
        src = s.get("_source", "")
        name = s.get("name", "")
        if src == "huggingface" and "huggingface.co/" in s["api"]:
            hf = s["api"].split("huggingface.co/")[-1].strip("/")
            mid = f"ollama/{hf.split('/')[-1]}"
            url, key, tool = cfg["ollama_url"], "ollama", False
        elif src == "freelist":
            mid = f"proxy/{slugify(name)}"
            url, key, tool = cfg["proxy_url"], "freecc", True
        else:
            continue
        entries.append({
            "id": mid, "name": f"{name} (free-models)", "vendor": "Custom",
            "url": url, "apiKey": key, "supportsToolCall": tool,
            "supportsImages": False, "buddyBridgeOwner": cfg["owner"],
        })
    target = os.environ.get("BUDDY_MODELS_FILE") or os.path.join(
        os.environ.get("WORKBUDDY_CONFIG_DIR", os.path.expanduser("~/.workbuddy")), "models.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    owned = {e["id"] for e in entries}
    if os.path.exists(target):
        old = json.loads(Path(target).read_text(encoding="utf-8"))
        arr = old["models"] if isinstance(old, dict) and "models" in old else (old if isinstance(old, list) else [])
        kept = [m for m in arr if m.get("buddyBridgeOwner") != cfg["owner"] and m.get("id") not in owned]
    else:
        kept = []
    merged = kept + entries
    Path(target).write_text(json.dumps({"models": merged, "availableModels": [m["id"] for m in merged]},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    return {"added": len(entries), "kept_other": len(kept), "path": target}


def import_dsh(cfg):
    """注入 free-models provider 块(FCC 代理 schema), 含订阅里发现的新免费 provider。"""
    data = fetch_subscription()
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
    lines = [
        "    # >>> free-models-provider >>>",
        "    free-models:",
        "      displayName: Free Models (daily)",
        "      api: openai-responses",
        f"      baseURL: http://127.0.0.1:{cfg['dsh_port']}/v1",
        "      apiKeyEnv: FCC_DSH_API_KEY",
        "      retryPolicy:",
        "        mode: normal",
        "        maxRetries: 0",
        "      models:",
    ]
    for mid, name, ctx, mtok in models:
        lines += [f"        - id: {mid}", f"          name: {name}",
                  f"          contextWindow: {ctx}", f"          maxTokens: {mtok}"]
    lines.append("    # <<< free-models-provider <<<")
    block = "\n".join(lines)

    dsh_home = os.environ.get("DSH_HOME", os.path.expanduser("~/.dsh"))
    settings = os.path.join(dsh_home, "settings.yaml")
    os.makedirs(dsh_home, exist_ok=True)
    marker = "free-models-provider"
    if os.path.exists(settings) and marker in Path(settings).read_text(encoding="utf-8"):
        return {"status": "skipped", "path": settings, "models": len(models)}
    bf = HERE / ".dsh_block.tmp"
    bf.write_text(block + "\n", encoding="utf-8")
    if not os.path.exists(settings) or "llm-pi-ai:" not in Path(settings).read_text(encoding="utf-8"):
        head = Path(settings).read_text(encoding="utf-8") if os.path.exists(settings) else ""
        Path(settings + ".tmp").write_text(head + "\nllm-pi-ai:\n  providers:\n" + block + "\n", encoding="utf-8")
    else:
        src = Path(settings).read_text(encoding="utf-8")
        out, done, ins = [], False, False
        for line in src.splitlines():
            out.append(line)
            if line.startswith("  providers:") and not done:
                out += block.splitlines()
                done = True
        Path(settings + ".tmp").write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(settings + ".tmp", settings)
    bf.unlink(missing_ok=True)
    return {"status": "injected", "path": settings, "models": len(models)}


# ----------------------------- 路由 -----------------------------
@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")


@app.route("/api/models")
def api_models():
    try:
        return jsonify({"ok": True, "models": models_list()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    try:
        data = fetch_subscription(force=True)
        return jsonify({"ok": True, "count": len(data.get("sites", []))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/config")
def api_config():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def api_config_set():
    cfg = load_config()
    cfg.update(request.json or {})
    save_config(cfg)
    return jsonify(cfg)


@app.route("/api/import", methods=["POST"])
def api_import():
    body = request.json or {}
    target = body.get("target")
    ids = body.get("ids", [])
    cfg = load_config()
    try:
        if target == "workbuddy":
            res = import_workbuddy(ids, cfg)
            return jsonify({"ok": True, "target": target, **res})
        elif target == "dsh":
            res = import_dsh(cfg)
            return jsonify({"ok": True, "target": target, **res})
        return jsonify({"ok": False, "error": "unknown target"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


INDEX_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>免费模型一键导入器</title>
<style>
:root{--bg:#0b1220;--card:#16233b;--line:#2a3a55;--accent:#38bdf8;--ok:#34d399;--warn:#fbbf24;--text:#e6edf6;--muted:#9fb0c3}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text)}
header{padding:18px 22px;display:flex;align-items:center;gap:14px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
h1{font-size:18px;margin:0} .spacer{flex:1}
button{cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--text);padding:8px 14px;border-radius:9px;font-size:14px}
button.primary{background:var(--accent);color:#04263a;border-color:var(--accent);font-weight:600}
button:hover{filter:brightness(1.1)} button:disabled{opacity:.5;cursor:not-allowed}
.bar{padding:12px 22px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--line)}
select,input[type=text]{background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;padding:18px 22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px;display:flex;flex-direction:column;gap:8px}
.card.sel{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.top{display:flex;gap:8px;align-items:flex-start}
.cb{margin-top:3px;width:16px;height:16px}
.name{font-weight:600;font-size:14px;line-height:1.35}
.badges{display:flex;gap:6px;flex-wrap:wrap}
.b{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);color:var(--muted)}
.b.lic{color:var(--ok);border-color:#1d5b46}
.b.cat{color:var(--accent);border-color:#1d4f63}
.desc{font-size:12px;color:var(--muted);line-height:1.5;max-height:54px;overflow:hidden}
.tags{font-size:11px;color:#7e8ea3}
.act{margin-top:auto;display:flex;gap:8px}
.act button{flex:1;padding:6px 0;font-size:12px}
#toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#0f2237;border:1px solid var(--ok);color:var(--text);padding:11px 18px;border-radius:11px;opacity:0;transition:.25s;pointer-events:none;z-index:9;max-width:80vw}
#toast.show{opacity:1}
a{color:var(--accent)}
</style></head>
<body>
<header><h1>免费模型一键导入器</h1><span class="spacer"></span>
<button id="refresh">↻ 刷新订阅</button></header>
<div class="bar">
<select id="filterCat"><option value="">全部类型</option><option value="llm">语言</option><option value="image">图像</option><option value="audio">语音</option><option value="video">视频</option><option value="multimodal">多模态</option></select>
<input type="text" id="search" placeholder="搜索名称 / 标签…" style="min-width:200px">
<label style="font-size:13px;color:var(--muted)"><input type="checkbox" id="onlyImportable"> 仅可导入</label>
<span class="spacer"></span>
<span id="count" style="font-size:13px;color:var(--muted)"></span>
<button id="selAll">全选</button>
<button id="importWB" class="primary">导入选中 → WorkBuddy</button>
<button id="importDSH" class="primary">安装 → DSH</button>
</div>
<div class="grid" id="grid"></div>
<div id="toast"></div>
<script>
let MODELS=[];
const $=s=>document.querySelector(s);
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),3200);}
function render(){
  const cat=$('#filterCat').value, q=$('#search').value.toLowerCase(), only=$('#onlyImportable').checked;
  const list=MODELS.filter(m=>(!cat||m.category===cat)&&(!only||m.importable)&&(!q||(m.name+' '+m.tags.join(' ')).toLowerCase().includes(q)));
  $('#count').textContent=`${list.length} / ${MODELS.length} 个模型`;
  $('#grid').innerHTML=list.map(m=>`
  <div class="card ${m._sel?'sel':''}" data-id="${m.id}">
    <div class="top"><input type="checkbox" class="cb" ${m._sel?'checked':''} data-id="${m.id}">
      <div class="name">${m.name}</div></div>
    <div class="badges"><span class="b lic">${m.license}</span><span class="b cat">${m.category_cn}</span><span class="b">${m.source}</span>${m.importable?'':'<span class="b">不可直接导入</span>'}</div>
    <div class="desc">${m.description||'—'}</div>
    <div class="tags">#${m.tags.slice(0,5).join(' #')||'—'}</div>
  </div>`).join('');
  document.querySelectorAll('.cb').forEach(c=>c.onchange=e=>{const m=MODELS.find(x=>x.id===e.target.dataset.id);m._sel=e.target.checked;e.target.closest('.card').classList.toggle('sel',m._sel);});
}
async function load(){try{const r=await fetch('/api/models');const d=await r.json();MODELS=(d.models||[]).map(m=>Object.assign(m,{_sel:false}));render();}catch(e){toast('加载失败: '+e);}}
$('#refresh').onclick=async()=>{toast('刷新中…');const r=await fetch('/api/refresh',{method:'POST'});const d=await r.json();toast(d.ok?`已刷新，共 ${d.count} 个`:'刷新失败');if(d.ok)load();};
$('#filterCat').onchange=render;$('#search').oninput=render;$('#onlyImportable').onchange=render;
$('#selAll').onclick=()=>{const cat=$('#filterCat').value,q=$('#search').value.toLowerCase(),only=$('#onlyImportable').checked;
  MODELS.forEach(m=>{if((!cat||m.category===cat)&&(!only||m.importable)&&(!q||(m.name+' '+m.tags.join(' ')).toLowerCase().includes(q)))m._sel=true;});render();};
$('#importWB').onclick=async()=>{const ids=MODELS.filter(m=>m._sel&&m.importable).map(m=>m.id);if(!ids.length){toast('请先勾选可导入的模型');return;}
  $('#importWB').disabled=true;const r=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:'workbuddy',ids})});const d=await r.json();
  $('#importWB').disabled=false;toast(d.ok?`已写入 WorkBuddy：${d.added} 条（保留其他 ${d.kept_other} 条）`:'导入失败: '+d.error);};
$('#importDSH').onclick=async()=>{const r=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:'dsh'})});const d=await r.json();
  toast(d.ok?(d.status==='skipped'?'DSH provider 已存在':'已注入 DSH provider，'+d.models+' 个模型'):'导入失败: '+d.error);};
load();
</script></body></html>
"""


if __name__ == "__main__":
    print(f"免费模型一键导入器 → http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
