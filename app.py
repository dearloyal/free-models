#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
free-models-importer —— 一键导入器（本地 Web 版）

启动: python3 app.py
打开: http://localhost:8088

功能:
  - 每天自动刷新的免费模型订阅(免费模型.json)
  - 每个模型标明: WorkBuddy 能否用 / DSH 能否用 + 走哪种本地传输
  - 卡片上直接「导入到 WorkBuddy / 导入到 DSH」一键导入
  - 可按平台筛选 / 勾选批量导入, 幂等(只动本工具标记条目)
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
    "openrouter_key": "",                        # OpenRouter 免费模型云端直连 key
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
    local = HERE / "免费模型.json"
    if not force and local.exists():
        try:
            return json.loads(local.read_text(encoding="utf-8"))
        except Exception:
            pass
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
        wb, dsh = s.get("_wb"), s.get("_dsh")
        if wb is None or dsh is None:  # 旧订阅未带分类字段时回退推算
            src, url = s.get("_source", ""), s.get("api", "")
            if src == "huggingface" and "huggingface.co/" in url:
                wb, dsh, wbv, dshv = True, True, "Ollama", "Ollama"
            elif src == "freelist":
                wb, dsh, wbv, dshv = True, True, "本地代理", "FCC 代理"
            else:
                wb, dsh, wbv, dshv = False, False, "", ""
        else:
            wb, dsh = bool(wb), bool(dsh)
            wbv, dshv = s.get("_wb_via", ""), s.get("_dsh_via", "")
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
            "wb": wb, "dsh": dsh,
            "wb_via": wbv, "dsh_via": dshv,
            "importable": wb or dsh,
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
        if src == "openrouter":
            mid = f"openrouter/{s.get('_model') or name}"
            url, key, tool = "https://openrouter.ai/api/v1", cfg.get("openrouter_key", ""), True
        elif src == "huggingface" and "huggingface.co/" in s["api"]:
            hf = s["api"].split("huggingface.co/")[-1].strip("/")
            mid = f"ollama/{hf.split('/')[-1]}"
            url, key, tool = cfg["ollama_url"], "ollama", False
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


def _inject_dsh_provider(cfg, key, display, api, base_url, api_key_env, models, marker):
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
    if os.path.exists(settings) and marker in Path(settings).read_text(encoding="utf-8"):
        return "skipped"
    bf = HERE / f".dsh_{abs(hash(marker))}.tmp"
    bf.write_text(block + "\n", encoding="utf-8")
    if not os.path.exists(settings) or "llm-pi-ai:" not in Path(settings).read_text(encoding="utf-8"):
        head = Path(settings).read_text(encoding="utf-8") if os.path.exists(settings) else ""
        Path(settings + ".tmp").write_text(head + "\nllm-pi-ai:\n  providers:\n" + block + "\n", encoding="utf-8")
    else:
        src = Path(settings).read_text(encoding="utf-8")
        out, done = [], False
        for line in src.splitlines():
            out.append(line)
            if line.startswith("  providers:") and not done:
                out += block.splitlines()
                done = True
        Path(settings + ".tmp").write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(settings + ".tmp", settings)
    bf.unlink(missing_ok=True)
    return "injected"


def import_dsh(ids, cfg):
    data = fetch_subscription()
    sites = {s["key"]: s for s in data.get("sites", [])}
    chosen = [sites[i] for i in ids if i in sites] or list(sites.values())
    or_models = []
    for s in chosen:
        if s.get("_source") == "openrouter" and s.get("_model"):
            or_models.append((s["_model"], f"{s['_model']} (free)",
                              s.get("_context_length") or 131072, 32768))
    if not or_models:
        return {"fcc": "skipped"}
    st = _inject_dsh_provider(cfg, "free-models", "Free Models (OpenRouter)", "openai",
                              "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                              or_models, "free-models-provider")
    return {"fcc": st}


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
            r = import_workbuddy(ids, cfg)
            return jsonify({"ok": True, "target": target, **r})
        elif target == "dsh":
            r = import_dsh(ids, cfg)
            return jsonify({"ok": True, "target": target, **r})
        return jsonify({"ok": False, "error": "unknown target"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


INDEX_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>免费模型一键导入器</title>
<style>
:root{--bg:#0b1220;--card:#16233b;--line:#2a3a55;--accent:#38bdf8;--ok:#34d399;--off:#5b6b80;--text:#e6edf6;--muted:#9fb0c3}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text)}
header{padding:18px 22px;display:flex;align-items:center;gap:14px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
h1{font-size:18px;margin:0} .spacer{flex:1}
button{cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--text);padding:8px 14px;border-radius:9px;font-size:14px}
button.primary{background:var(--accent);color:#04263a;border-color:var(--accent);font-weight:600}
button:hover{filter:brightness(1.1)} button:disabled{opacity:.4;cursor:not-allowed}
.bar{padding:12px 22px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--line)}
select,input[type=text]{background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px;padding:18px 22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px;display:flex;flex-direction:column;gap:8px}
.card.sel{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.top{display:flex;gap:8px;align-items:flex-start}
.cb{margin-top:3px;width:16px;height:16px}
.name{font-weight:600;font-size:14px;line-height:1.35}
.badges{display:flex;gap:6px;flex-wrap:wrap}
.b{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);color:var(--muted)}
.b.lic{color:var(--ok);border-color:#1d5b46}
.b.cat{color:var(--accent);border-color:#1d4f63}
.b.wb{color:var(--ok);border-color:#1d5b46}
.b.wb.off{color:var(--off);border-color:#33425a}
.b.dsh{color:#f0abfc;border-color:#5b2a63}
.b.dsh.off{color:var(--off);border-color:#33425a}
.desc{font-size:12px;color:var(--muted);line-height:1.5;max-height:54px;overflow:hidden}
.tags{font-size:11px;color:#7e8ea3}
.act{margin-top:auto;display:flex;gap:8px}
.act button{flex:1;padding:6px 0;font-size:12px}
#toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#0f2237;border:1px solid var(--ok);color:var(--text);padding:11px 18px;border-radius:11px;opacity:0;transition:.25s;pointer-events:none;z-index:9;max-width:80vw}
#toast.show{opacity:1}
</style></head>
<body>
<header><h1>免费模型一键导入器</h1><span class="spacer"></span>
<button id="refresh">↻ 刷新订阅</button></header>
<div class="bar">
<select id="filterPlat"><option value="">全部平台</option><option value="wb">仅 WorkBuddy 可用</option><option value="dsh">仅 DSH 可用</option></select>
<select id="filterCat"><option value="">全部类型</option><option value="llm">语言</option><option value="image">图像</option><option value="audio">语音</option><option value="video">视频</option><option value="multimodal">多模态</option></select>
<input type="text" id="search" placeholder="搜索名称 / 标签…" style="min-width:200px">
<span class="spacer"></span>
<span id="count" style="font-size:13px;color:var(--muted)"></span>
<button id="selAll">全选可见</button>
<button id="importWB" class="primary">导入选中 → WorkBuddy</button>
<button id="importDSH" class="primary">导入选中 → DSH</button>
</div>
<div class="grid" id="grid"></div>
<div id="toast"></div>
<script>
let MODELS=[];
const $=s=>document.querySelector(s);
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),3200);}
function render(){
  const plat=$('#filterPlat').value, cat=$('#filterCat').value, q=$('#search').value.toLowerCase();
  const list=MODELS.filter(m=>(!plat||(plat==='wb'&&m.wb)||(plat==='dsh'&&m.dsh))&&(!cat||m.category===cat)&&(!q||(m.name+' '+m.tags.join(' ')).toLowerCase().includes(q)));
  $('#count').textContent=`${list.length} / ${MODELS.length} 个`;
  $('#grid').innerHTML=list.map(m=>`
  <div class="card ${m._sel?'sel':''}" data-id="${m.id}">
    <div class="top"><input type="checkbox" class="cb" ${m._sel?'checked':''} data-id="${m.id}">
      <div class="name">${m.name}</div></div>
    <div class="badges"><span class="b lic">${m.license}</span><span class="b cat">${m.category_cn}</span>
      <span class="b wb ${m.wb?'':'off'}">WB${m.wb?' ✓':' ✗'}</span>
      <span class="b dsh ${m.dsh?'':'off'}">DSH${m.dsh?' ✓':' ✗'}</span></div>
    <div class="desc">${m.description||'—'}</div>
    <div class="tags">${m.wb&&m.wb_via?'WB走'+m.wb_via+' · ':''}${m.dsh&&m.dsh_via?'DSH走'+m.dsh_via:''}</div>
    <div class="act">
      <button data-id="${m.id}" data-target="workbuddy" ${m.wb?'':'disabled'}>导入 WB</button>
      <button data-id="${m.id}" data-target="dsh" ${m.dsh?'':'disabled'}>导入 DSH</button>
    </div>
  </div>`).join('');
  document.querySelectorAll('.cb').forEach(c=>c.onchange=e=>{const m=MODELS.find(x=>x.id===e.target.dataset.id);m._sel=e.target.checked;e.target.closest('.card').classList.toggle('sel',m._sel);});
  document.querySelectorAll('.act button').forEach(b=>b.onclick=e=>importOne(e.target.dataset.id,e.target.dataset.target));
}
async function load(){try{const r=await fetch('/api/models');const d=await r.json();MODELS=(d.models||[]).map(m=>Object.assign(m,{_sel:false}));render();}catch(e){toast('加载失败: '+e);}}
async function importOne(id,target){
  const btn=event.target; btn.disabled=true;
  const r=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target,ids:[id]})});
  const d=await r.json(); btn.disabled=false;
  if(target==='workbuddy') toast(d.ok?`已导入 WorkBuddy（${d.added} 条）`:'失败: '+d.error);
  else toast(d.ok?('DSH: '+(d.fcc==='skipped'?'FCC已存在':'FCC已注入')+(d.ollama?('，'+ (d.ollama==='skipped'?'Ollama已存在':'Ollama已注入')):'')):'失败: '+d.error);
}
$('#refresh').onclick=async()=>{toast('刷新中…');const r=await fetch('/api/refresh',{method:'POST'});const d=await r.json();toast(d.ok?`已刷新，共 ${d.count} 个`:'刷新失败');if(d.ok)load();};
$('#filterPlat').onchange=render;$('#filterCat').onchange=render;$('#search').oninput=render;
$('#selAll').onclick=()=>{MODELS.forEach(m=>m._sel=true);render();};
$('#importWB').onclick=async()=>{const ids=MODELS.filter(m=>m._sel&&m.wb).map(m=>m.id);if(!ids.length){toast('请先勾选 WorkBuddy 可用的模型');return;}
  $('#importWB').disabled=true;const r=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:'workbuddy',ids})});const d=await r.json();
  $('#importWB').disabled=false;toast(d.ok?`已写入 WorkBuddy：${d.added} 条（保留其他 ${d.kept_other} 条）`:'导入失败: '+d.error);};
$('#importDSH').onclick=async()=>{const ids=MODELS.filter(m=>m._sel&&m.dsh).map(m=>m.id);if(!ids.length){toast('请先勾选 DSH 可用的模型');return;}
  const r=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:'dsh',ids})});const d=await r.json();
  toast(d.ok?('DSH: '+(d.fcc==='skipped'?'FCC已存在':'FCC已注入')+(d.ollama?('，'+(d.ollama==='skipped'?'Ollama已存在':'Ollama已注入')):'')):'导入失败: '+d.error);};
load();
</script></body></html>
"""


if __name__ == "__main__":
    print(f"免费模型一键导入器 → http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
