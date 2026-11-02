# 免费模型订阅 · 每日自动更新

每天 **北京时间 00:00**（UTC 16:00）自动全网检索最新发布的**免费模型**（LLM / 图像 / 语音 / 多模态），
过滤许可证后，产出一份**可订阅的 JSON**——订阅链接每天自动刷新，模式与「影视仓订阅接口」一致。

## 订阅链接（每天自动更新）

```
https://raw.githubusercontent.com/dearloyal/free-models/main/免费模型.json
```

> 部分订阅器对中文文件名敏感，等价 ASCII 形式：
> `https://raw.githubusercontent.com/dearloyal/free-models/main/%E5%85%8D%E8%B4%B9%E6%A8%A1%E5%9E%8B.json`

把它填进任何支持「订阅 / 接口 JSON」的客户端即可每日自动拉取最新免费模型清单。

## 数据格式（影视仓风格信封）

```json
{
  "name": "免费模型",
  "source": "dearloyal/CS",
  "count": 37,
  "updated_at": "2026-11-02T23:36:00+00:00",
  "sites": [
    {
      "key": "hf:meta-llama/Llama-3.1-8B",
      "name": "meta-llama/Llama-3.1-8B",
      "api": "https://huggingface.co/meta-llama/Llama-3.1-8B",
      "type": 1,
      "_license": "apache-2.0",
      "_category": "llm",
      "_source": "huggingface",
      "_tags": ["chat", "..."]
    }
  ]
}
```

每个 `sites` 项即一个免费模型；自定义字段 `_license` / `_category` / `_source` / `_tags` 便于筛选。

## 数据来源

| 来源 | 说明 |
|---|---|
| Hugging Face Models API | 按创建时间取最新，按 `license` 过滤 |
| GitHub Search API | 抓新发布的模型相关仓库（带 `GITHUB_TOKEN` 防限流） |
| RSS / Atom | Hugging Face 博客、免费清单仓库的更新流 |
| 现有免费清单 | 如 `free-llm-api-resources`（自动更新的免费 API 合集） |

## 本地运行

```bash
pip install requests pyyaml
python3 scripts/free_models.py      # 生成 免费模型.json / 免费模型.md 到仓库根
```

## 调参

编辑 `models_config.yaml`：修改 `days_lookback`（回溯天数）、许可证白/黑名单、RSS 源、GitHub 检索语句等，无需改代码。

## 重要提醒

- **「免费」≠「可商用」**：本仓库按 `models_config.yaml` 的许可证白/黑名单过滤，请按你的用途自行复核。
- **权重不存 GitHub**：模型权重走 Hugging Face Hub，运行时按需拉取。
- **免费档会变**：厂商可能随时取消免费模型，因此流程设计为「每天刷新」而非「一劳永逸」。
