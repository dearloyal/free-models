# 免费模型 · 每日自动更新 + 一键导入

每天自动从 **OpenRouter 官方 API** 拉取**真实存在**的免费模型（`pricing=0` 或 `:free`），
产出可订阅的 JSON；再用一条命令把这些模型**直连导入 WorkBuddy / DSH**，点一下就能用。

## 一句话用法

```bash
# 1) 拿一个免费 key（1 分钟，无需信用卡）: https://openrouter.ai/keys
# 2) 一键导入 WorkBuddy
python3 oneclick.py --key sk-or-v1-你的key
```

> **为什么需要 key？** OpenRouter 的免费模型是**云端服务**，必须用免费 API key 才能调用。
> 好处是：不用显卡、不用装 Ollama / 本地代理，填个 key 就能跑。这是"真正能用"的最省事方式。

## 订阅链接（每天自动刷新）

```
https://raw.githubusercontent.com/dearloyal/free-models/main/免费模型.json
```

## 命令一览

| 命令 | 作用 |
|---|---|
| `python3 oneclick.py --key sk-or-v1-xxx` | 导入全部免费模型到 **WorkBuddy** |
| `python3 oneclick.py --key sk-or-v1-xxx --dsh` | 导入到 **DSH**（写入 `~/.dsh/settings.yaml`） |
| `python3 oneclick.py --key sk-or-v1-xxx --both` | 两个都导 |
| `python3 oneclick.py --list` | 只看有哪些真实免费模型，不写入 |

也可用环境变量代替 `--key`：`export OPENROUTER_API_KEY=sk-or-v1-xxx` 后直接 `python3 oneclick.py`。

## 一键安装（可选）

macOS / Linux：
```bash
curl -fsSL https://raw.githubusercontent.com/dearloyal/free-models/main/install.sh | bash -s -- --key sk-or-v1-xxx
```
Windows PowerShell：
```powershell
irm https://raw.githubusercontent.com/dearloyal/free-models/main/install.ps1 | iex
# 然后进入目录: cd $HOME\free-models; python oneclick.py --key sk-or-v1-xxx
```

## 它到底做了什么

1. `scripts/free_models.py` 调 `https://openrouter.ai/api/v1/models`，筛出 `pricing.prompt=0` 的**真实模型**（当前约 17 个），写入 `免费模型.json`。
2. `oneclick.py` 读取该 JSON，把每个模型的 `base_url = https://openrouter.ai/api/v1` + 你的 key，写进：
   - WorkBuddy：`~/.workbuddy/models.json`（`vendor:Custom` 条目，带 `buddyBridgeOwner` 标记）
   - DSH：`~/.dsh/settings.yaml` 的 `free-models` provider（`apiKeyEnv: OPENROUTER_API_KEY`）
3. 幂等：重跑只更新自己的条目，不会重复、不动你手动配的模型。

## 数据来源（为什么现在是可信的）

| 来源 | 说明 |
|---|---|
| **OpenRouter `/api/v1/models`** | 官方模型目录，返回真实模型 ID 与价格；筛 `pricing=0` 得真免费模型 |

> 早期版本曾用正则从某 README 抓链接文本当模型名，导致出现 `deepseek-v4-flash` 等**并不存在的假模型**——已彻底移除，现只信官方 API。

## 本地生成 / 调参

```bash
pip install requests pyyaml
python3 scripts/free_models.py        # 重新生成 免费模型.json / 免费模型.md
```

编辑 `models_config.yaml` 可调回溯天数、许可证白/黑名单、HF 源等。

## 重要提醒

- **免费模型也会限流**：OpenRouter 免费档有速率限制，报 429 属正常，稍等或换模型。
- **key 别提交到仓库**：`oneclick.py` 只在本地写进你的 harness 配置，不会上传。
- **模型会变**：免费清单每天刷新，跑一次 `git pull` + `oneclick.py` 即可同步最新。
