# 把免费模型订阅导入你的 harness

订阅链接（每天自动更新）：

```
https://raw.githubusercontent.com/dearloyal/free-models/main/免费模型.json
```

本仓库提供 `to_harness.py`，一键把订阅转成 harness 可直接消费的文件：

```bash
python3 to_harness.py
# 生成:
#   ollama_pull.sh          -> 本地 Ollama 拉取 HF 模型
#   litellm_model_list.yaml -> LiteLLM / OpenAI 兼容 harness 配置模板
```

## 路线 A：本地跑（Ollama / vLLM）

1. 运行 `bash ollama_pull.sh` 把清单里的 Hugging Face 模型拉到本地。
2. Ollama 自带 OpenAI 兼容接口（`http://localhost:11434/v1`），你的 harness 直接指向它即可。
3. 或在 `ollama_pull.sh` 基础上用 `vLLM` 起服务，暴露同样的 OpenAI 接口。

## 路线 B：免费 API（OpenAI 兼容 harness，含 DeepSeek 类）

清单里 `_source=freelist` 的条目是 OpenRouter / Groq / Together 等**免费档**，均为 OpenAI 兼容。

1. 打开 `litellm_model_list.yaml` 里对应的提供方链接，拿到 `base_url` 与 API Key。
2. 补全 `api_base` 与 `api_key`（建议用环境变量）。
3. 把该 yaml 作为 LiteLLM 配置启动，或并入你现有 harness 的 model_list。

> 任何声称兼容 OpenAI API 的 harness（LiteLLM、vLLM、Ollama OpenAI 服务、以及基于 DeepSeek/OpenAI SDK 自搭的 agent harness）都走同一条路：把免费模型的 `base_url + key` 配进去即可。

## 路线 C：WorkBuddy 内直接使用

- **当知识源**：把订阅链接加入 WorkBuddy「资料库」，随时问"今天有哪些免费模型"。
- **当技能**：本仓库配套 WorkBuddy Skill `free-models`，一句话拉取并筛选最新清单。
- **当模型后端**：把 freelist 里的 OpenAI 兼容免费 API 按 WorkBuddy「自定义模型 / OpenAI 兼容端点」配置，即可直接调用。
