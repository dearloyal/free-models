#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日免费模型订阅生成器（影视仓风格订阅 JSON）。

用法：python3 scripts/free_models.py
输出：仓库根目录下的 免费模型.json（订阅链接）+ 免费模型.md（人读摘要）

设计目标：与 dearloyal/CS 现有「线路订阅」完全平行——
每天定时抓取最新免费模型，过滤许可证后，产出一份可订阅的 JSON，
订阅链接 = https://raw.githubusercontent.com/dearloyal/CS/main/免费模型.json
"""
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

try:
    import yaml
except ImportError:
    yaml = None

# ------------------------- 默认配置（可被 models_config.yaml 覆盖） -------------------------
CATEGORIES = {
    "llm":        {"hf": ["text-generation", "text-generation-inference"],
                  "kw": ["llm", "chat", "language-model", "gpt", "qwen", "llama", "deepseek"]},
    "image":      {"hf": ["text-to-image", "image-generation"],
                  "kw": ["diffusion", "image", "sdxl", "draw", "paint"]},
    "audio":      {"hf": ["automatic-speech-recognition", "text-to-speech"],
                  "kw": ["asr", "tts", "speech", "audio", "whisper"]},
    "multimodal": {"hf": ["image-text-to-text", "visual-question-answering"],
                  "kw": ["multimodal", "vl", "vision-language", "vlm"]},
}
LICENSE_ALLOW = ["apache-2.0", "mit", "bsd", "cc-by", "cc-by-4.0", "openrail", "other"]
LICENSE_BLOCK = ["cc-by-nc", "cc-by-nc-4.0", "cc-by-nc-sa", "non-commercial"]
DAYS_LOOKBACK = 2
MAX_PER_SOURCE = 80
RSS_FEEDS = [
    "https://huggingface.co/blog/feed.xml",
    "https://github.com/atomlong/free-llm-api-resources/commits/main.atom",
]
FREELIST_RAW = [
    "https://raw.githubusercontent.com/atomlong/free-llm-api-resources/main/README.md",
]
GITHUB_QUERY = 'LLM OR "large language model" OR diffusion OR "speech recognition" OR multimodal'

CFG_PATH = Path(__file__).resolve().parent.parent / "models_config.yaml"
if CFG_PATH.exists() and yaml:
    try:
        o = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}
        CATEGORIES = o.get("categories", CATEGORIES)
        LICENSE_ALLOW = o.get("license_allow", LICENSE_ALLOW)
        LICENSE_BLOCK = o.get("license_block", LICENSE_BLOCK)
        DAYS_LOOKBACK = o.get("days_lookback", DAYS_LOOKBACK)
        MAX_PER_SOURCE = o.get("max_per_source", MAX_PER_SOURCE)
        RSS_FEEDS = o.get("rss_feeds", RSS_FEEDS)
        FREELIST_RAW = o.get("freelist_raw", FREELIST_RAW)
        GITHUB_QUERY = o.get("github_query", GITHUB_QUERY)
    except Exception as e:
        print("配置加载警告，使用默认值:", e)

GH_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
UA = {"User-Agent": "free-model-radar/1.0"}


# ------------------------- 采集器 -------------------------
def _cat_for_tag(tag):
    for name, c in CATEGORIES.items():
        if tag in c.get("hf", []):
            return name
    return "other"


def _cat_for_text(text):
    t = (text or "").lower()
    for name, c in CATEGORIES.items():
        if any(k.lower() in t for k in c.get("kw", [])):
            return name
    return "other"


def collect_huggingface():
    out = []
    if not CATEGORIES:
        return out
    tags = list(dict.fromkeys(t for c in CATEGORIES.values() for t in c.get("hf", [])))
    for tag in tags:
        try:
            r = requests.get(
                "https://huggingface.co/api/models",
                params={"sort": "createdAt", "direction": "-1",
                        "limit": MAX_PER_SOURCE, "pipeline_tag": tag},
                timeout=20,
            )
            r.raise_for_status()
            for it in r.json():
                lic = None
                for t in (it.get("tags", []) or []):
                    if isinstance(t, str) and t.startswith("license:"):
                        lic = t.split(":", 1)[1]
                        break
                lic = lic or (it.get("cardData") or {}).get("license")
                out.append({
                    "id": "hf:" + it["id"], "name": it["id"], "source": "huggingface",
                    "url": "https://huggingface.co/" + it["id"],
                    "category": _cat_for_tag(tag), "license": lic,
                    "pipeline_tag": it.get("pipeline_tag"),
                    "created_at": it.get("createdAt"), "updated_at": it.get("lastModified"),
                    "likes": it.get("likes", 0) or 0, "downloads": it.get("downloads", 0) or 0,
                    "tags": it.get("tags", []) or [], "description": it.get("description"),
                })
        except Exception as e:
            print(f"[huggingface] {tag} 失败: {e}")
    return out


def collect_github():
    out = []
    since = (datetime.utcnow() - timedelta(days=DAYS_LOOKBACK)).strftime("%Y-%m-%d")
    query = f"{GITHUB_QUERY} stars:>20 created:>{since}"
    headers = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"
    try:
        r = requests.get("https://api.github.com/search/repositories",
                         params={"q": query, "sort": "updated", "order": "desc", "per_page": MAX_PER_SOURCE},
                         headers=headers, timeout=20)
        r.raise_for_status()
        for it in r.json().get("items", []):
            lic = (it.get("license") or {}).get("spdx_id")
            text = (it.get("name", "") + " " + (it.get("description") or "") + " " +
                    " ".join(it.get("topics", []) or []))
            out.append({
                "id": "gh:" + it["full_name"], "name": it["full_name"], "source": "github",
                "url": it["html_url"], "category": _cat_for_text(text), "license": lic,
                "created_at": it.get("created_at"), "updated_at": it.get("pushed_at"),
                "stars": it.get("stargazers_count", 0) or 0,
                "tags": it.get("topics", []) or [], "description": it.get("description"),
            })
    except Exception as e:
        print(f"[github] 失败: {e}")
    return out


def _xml_text(el, tag, ns=None):
    n = el.find(tag) or (el.find(tag.split(":")[-1]) if ns is None else None)
    if n is None and ns:
        n = el.find(tag, ns)
    return n.text.strip() if n is not None and n.text else None


def collect_rss():
    out = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for feed in RSS_FEEDS:
        try:
            r = requests.get(feed, timeout=20, headers=UA)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = root.findall(".//item") or root.findall(".//atom:entry", ns)
            for it in items[:MAX_PER_SOURCE]:
                title = _xml_text(it, "title")
                link = _xml_text(it, "link") or (it.find("atom:link", ns).get("href") if it.find("atom:link", ns) is not None else None)
                desc = _xml_text(it, "description") or _xml_text(it, "summary")
                pub = _xml_text(it, "pubDate") or _xml_text(it, "updated")
                if not title:
                    continue
                text = title + " " + (desc or "")
                out.append({
                    "id": "rss:" + (link or title), "name": title[:120], "source": "rss",
                    "url": link or feed, "category": _cat_for_text(text),
                    "created_at": pub, "description": (desc or "")[:300],
                })
        except Exception as e:
            print(f"[rss] {feed} 失败: {e}")
    return out


def collect_freelist():
    out = []
    for url in FREELIST_RAW:
        try:
            r = requests.get(url, timeout=20, headers=UA)
            r.raise_for_status()
            for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", r.text):
                name, link = m.group(1), m.group(2)
                if any(b in name.lower() for b in ("api", "model", "llm", "free", "gpt", "diffusion", "tts")):
                    out.append({
                        "id": "freelist:" + link, "name": name[:120], "source": "freelist",
                        "url": link, "category": _cat_for_text(name),
                        "description": "来自免费模型清单",
                    })
        except Exception as e:
            print(f"[freelist] {url} 失败: {e}")
    return out


# ------------------------- 过滤 + 评分 -------------------------
def _norm(lic):
    return lic.strip().lower() if lic else None


def passes(e):
    lic = _norm(e.get("license"))
    if lic is None:
        return True
    if any(b in lic for b in LICENSE_BLOCK):
        return False
    if LICENSE_ALLOW and not any(a in lic for a in LICENSE_ALLOW):
        return False
    return True


def score(e):
    s = 0.0
    s += min(e.get("likes", 0), 500) * 0.5
    s += min(e.get("stars", 0), 500) * 0.5
    s += min(e.get("downloads", 0), 50000) / 1000.0
    ca = e.get("created_at")
    if ca:
        try:
            dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
            s += max(0, 30 - (datetime.now(timezone.utc) - dt).days) * 2
        except Exception:
            pass
    return s


def filter_and_rank(entries):
    seen, cleaned = set(), []
    for e in entries:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        if passes(e):
            cleaned.append(e)
    cleaned.sort(key=score, reverse=True)
    return cleaned


# ------------------------- 产出（影视仓风格订阅信封） -------------------------
def build_subscription(entries):
    sites = []
    for e in entries:
        sites.append({
            "key": e["id"],
            "name": e["name"],
            "api": e["url"],
            "type": 1,
            "searchable": 0,
            "quickSearch": 0,
            "filterable": 0,
            "detail": e["url"],
            "_license": e.get("license") or "未知",
            "_category": e.get("category", "other"),
            "_source": e.get("source"),
            "_tags": (e.get("tags", []) or [])[:8],
            "_description": (e.get("description") or "")[:160],
        })
    return {
        "name": "免费模型",
        "source": "dearloyal/CS",
        "count": len(sites),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sites": sites,
    }


def build_markdown(sub):
    lines = [
        "# 免费模型订阅（每日自动更新）",
        "",
        f"> 生成时间：{sub['updated_at']} · 共 {sub['count']} 个免费模型",
        "",
        "订阅链接（影视仓风格，可每日自动刷新）：",
        "",
        "```",
        "https://raw.githubusercontent.com/dearloyal/CS/main/免费模型.json",
        "```",
        "",
        "## 列表",
        "",
        "| 名称 | 类型 | 许可证 | 来源 |",
        "| --- | --- | --- | --- |",
    ]
    for s in sub["sites"][:200]:
        lines.append(f"| {s['name']} | {s['_category']} | {s['_license']} | {s['_source']} |")
    return "\n".join(lines)


def main():
    all_e = []
    all_e += collect_huggingface()
    all_e += collect_github()
    all_e += collect_rss()
    all_e += collect_freelist()
    print(f"[collect] 原始 {len(all_e)} 条")

    ranked = filter_and_rank(all_e)
    print(f"[filter ] 过滤后 {len(ranked)} 条")

    sub = build_subscription(ranked)
    root = Path(__file__).resolve().parent.parent
    (root / "免费模型.json").write_text(json.dumps(sub, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "免费模型.md").write_text(build_markdown(sub), encoding="utf-8")
    print(f"[output ] 已生成 免费模型.json（{sub['count']} 条）-> {root}")


if __name__ == "__main__":
    main()
