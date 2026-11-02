# 把免费模型订阅导入你的 harness

订阅链接（每天自动更新）：

```
https://raw.githubusercontent.com/dearloyal/free-models/main/免费模型.json
```

本仓库的 `to_harness.py` 参考 GitHub 上两个成熟方案的原生格式生成导入文件：
- **ow-bridge** → 把模型写进 `~/.workbuddy/models.json`（`vendor=Custom` + `url` + `apiKey`）
- **dsh-free-models** → 往 `~/.dsh/settings.yaml` 注入一个 provider 块（Free Claude Code 本地代理，OpenAI Responses 协议）

```bash
python3 to_harness.py
# 生成:
#   workbuddy_models.json  -> WorkBuddy 原生模型配置（含 availableModels）
#   import_workbuddy.sh    -> 幂等注入 ~/.workbuddy/models.json
#   dsh_provider.yaml      -> DSH 原生 provider 块（FCC 代理 schema）
#   import_dsh.sh          -> 幂等注入 ~/.dsh/settings.yaml
#   ollama_pull.sh         -> 本地 Ollama 拉取 HF 模型
```

## 路线 A：导入 WorkBuddy（原生格式）

传输层建议用本地聚合代理（与 ow-bridge 一致用 OpenCode，或用 FCC 的 OpenAI 兼容端点）。
HF 模型默认指向本地 Ollama（`http://localhost:11434/v1`），API 类免费模型指向 `WORKBUDDY_PROXY_URL`（缺省 `http://127.0.0.1:8082/v1`）。

```bash
bash import_workbuddy.sh
# 写入 ~/.workbuddy/models.json，仅增删本脚本 owned 的条目(buddyBridgeOwner=free-models)
# 重跑幂等：不会重复、不会动你手动配置的其他模型
```

导入后 WorkBuddy 的模型选择器即出现 `xxx (free-models·hf)` / `xxx (free-models·api)`。

## 路线 B：导入 DeepSeek Harness / DSH（原生格式）

传输层复用 **Free Claude Code (FCC)** 本地代理（与 dsh-free-models 完全一致，已验证）：
聚合 Gemini / OpenRouter / GitHub Models / Groq / NVIDIA NIM / Z.ai 等免费档，带故障转移。

```bash
# 1) 先装并启动 FCC 本地代理（见 dsh-free-models 的 install.sh，监听 127.0.0.1:8082）
# 2) 幂等注入 provider 块
bash import_dsh.sh
# 注入 ~/.dsh/settings.yaml 的 llm-pi-ai.providers 下，key=free-models（不与 dsh-free-models 冲突）
```

重跑 `to_harness.py` 后再次 `bash import_dsh.sh` 即可把订阅里新发现的免费 provider 同步进 DSH。

## 路线 C：本地 Ollama / vLLM

```bash
bash ollama_pull.sh      # 把清单里的 HF 模型拉到本地
# Ollama 自带 OpenAI 兼容接口 http://localhost:11434/v1，harness 直接指向它
```

## 路线 D：WorkBuddy 内当知识源 / 技能

- **知识源**：把订阅链接加入 WorkBuddy「资料库」，随时问"今天有哪些免费模型"。
- **技能**：本仓库配套 WorkBuddy Skill `free-models`，一句话实时拉取并筛选最新清单。
