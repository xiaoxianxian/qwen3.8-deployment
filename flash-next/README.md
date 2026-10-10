# Qwen3.8-Flash-Next 本地部署（Sushi 引擎）

在 Apple Silicon Mac 上用 [Sushi](https://github.com/beamivalice/sushi) 引擎跑 Qwen3.8-Flash-Next（2bpw 量化）的技术文档。面向想在本地获得比 Qwen3.8-27B 更快的 agentic coding / 工具调用速度的开发者。

> 本文是纯技术教程。部署经验与踩坑故事见公众号文章（仓库根目录不收公众号文章，详见 `GITHUB_REPO_GUIDE.md`）。12 题 A/B 原始脚本与数据在 `../bench/`。

---

## 一、适用环境

| 项 | 要求 |
|----|------|
| 芯片 | Apple Silicon（M1–M5），Intel / Windows 不支持 |
| 内存 | **≥ 48GB** 才能 2bpw 全驻留（约 37GB 常驻）；32GB 只能专家流式，不推荐 |
| 系统 | macOS 26.2+（Sushi 最低要求） |
| 引擎 | Sushi ≥ 1.0.4（`sushi serve` 暴露 OpenAI 兼容接口） |
| 磁盘 | 预留 ≥ 70GB（权重约 65GB） |

配套对照：Qwen3.8-27B（Ollama，NVFP4 约 18GB，≥24GB 即可）见仓库根 README。

---

## 二、快速开始

### 1. 安装 Sushi

优先用 Homebrew：

```bash
brew install beamivalice/tap/sushi
```

若你的环境无法写入 Homebrew 信任标记（部分沙箱会拦截），改用官方编译好的二进制包：从 [Sushi 的 GitHub Releases](https://github.com/beamivalice/sushi) 下载 `sushi-bin-macos-arm64.tar.gz`，解压后把里面的 `sushi` 可执行文件软链到 `/opt/homebrew/bin/sushi`。注意软链必须指向包顶层目录里的 `sushi` 二进制（顶层是带版本号的目录，如 `sushi-macos-arm64/`）。

验证：

```bash
sushi --version
# 期望输出含 sushi 1.2.1 与 nax on (M5 neural accelerators)
```

### 2. 下载权重

```bash
sushi pull qwen3.8-flash-next:2bpw
# 解析为 beamster/Qwen3.8-Flash-Next-Sushi-2bpw，共 212 个文件、约 65GB
```

> **重要**：`sushi pull` 在网络中断时会**静默退出且退出码为 0**，不会报错。判断真假的唯一办法是数文件数：完整应是 212 个文件、磁盘占用 ≥ 64GB。若不足，重新运行 `sushi pull`（自带断点续传，会跳过已完成的文件）直到补齐。仓库里的 `deploy.sh` 内置了自愈循环，推荐直接用。

### 3. 启动服务

```bash
sushi serve \
  --model ~/.sushi/models/beamster/Qwen3.8-Flash-Next-Sushi-2bpw \
  --host 127.0.0.1 --port 12345 \
  --skip-mem-preflight
```

两个参数含义：

- `--skip-mem-preflight`：48GB 机器上预检要求约 37GB 连续空闲，但系统实际可用常只有约 29GB（其他进程占用），预检会失败导致服务起不来。跳过它，让运行时自行调度。
- **保持默认 8-bit KV 缓存**：不要加 `--kv-quant 4`。48GB 上 4-bit KV 过于激进，一个 314 token 的 prompt 会直接报 HTTP 400（GPU 余量不足）。

服务默认开启 MTP 投机解码、KV8、视觉塔，监听 `127.0.0.1:12345`，暴露 OpenAI 兼容接口（同时兼容 Anthropic `/v1/messages` 与 Responses 格式）。

### 4. 验证

```bash
bash verify.sh
# 或手动：
curl -s http://127.0.0.1:12345/v1/models
curl -s http://127.0.0.1:12345/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"beamster/Qwen3.8-Flash-Next-Sushi-2bpw","messages":[{"role":"user","content":"2+3=?"}],"max_tokens":64}'
```

> 若 curl 返回 502，是系统透明代理劫持了本地请求。所有本地请求前清掉代理变量：`env -u http_proxy -u https_proxy curl ...`。

---

## 三、接入 Agent 工具

端点 `http://127.0.0.1:12345/v1`，本地免 API Key。

**WorkBuddy**（`~/.workbuddy/models.json` 新增一条）：

```json
{
  "id": "qwen3.8-flash-next:2bpw",
  "name": "qwen3.8-flash-next:2bpw",
  "vendor": "Custom",
  "url": "http://127.0.0.1:12345/v1",
  "supportsToolCall": true,
  "supportsImages": true,
  "supportsReasoning": true
}
```

**Hermes Agent**（`~/.hermes/config.yaml` 的 `providers` 段新增）：

```yaml
sushi:
  base_url: http://127.0.0.1:12345/v1
  discover_models: true
  model: beamster/Qwen3.8-Flash-Next-Sushi-2bpw
  models:
    beamster/Qwen3.8-Flash-Next-Sushi-2bpw: {}
  name: Sushi Qwen3.8-Flash-Next (Local 12345)
```

---

## 四、性能数据（12 题 A/B vs 27B）

同套 12 题（代码生成 / 数学 / 知识 / 长上下文 / 结构化 / 中文写作），temperature=0，本机 M5 Pro / 48GB 实测。完整脚本与逐题输出在 `../bench/`（`ab_run_unified.py`、`validate.py`、`ab_results/`）。

| 维度 | 27B（Ollama NVFP4） | Flash-Next（Sushi 2bpw） |
|------|--------------------|--------------------------|
| 全样本平均 decode | 约 26 tok/s | 约 25 tok/s（被冷启动拖累） |
| 热态平均（重启后稳定题） | — | 约 45 tok/s（约为 27B 的 1.7 倍） |
| 冷态（首题 / 长上下文） | 无冷启动 | 约 1–12 tok/s，长上下文题可跌到约 1 |
| 质量抽样（JSON / 数学 / 知识题） | 正确 | 同判，未现可观测降智 |

**关键结论**：Flash-Next 热态明显快于 27B，但每次重启服务后的首题与长上下文题会因 KV 缓存累积而速度塌方。生产用法是**每道题重启一次服务清缓存**，因此它适合批量 / 温态任务，不适合「一个常驻服务被多人轮流问」。

---

## 五、共存约束

Flash-Next 常驻约 37GB，Qwen3.8-27B 约 18GB，MiniMax H3 视频模型另占约 10GB 往上。**三者不能同驻** 48GB 机器，两两开即可。用 Flash-Next 前先停 27B：

```bash
ollama stop qwen3.8:27b-mlx
```

跑 H3 基准前同理先停 27B。128GB 以上机器不受此限。

---

## 六、常见问题

| 现象 | 原因与解决 |
|------|-----------|
| `sushi pull` 报完成但服务报模型不完整 | 网络中断静默退出。数 `~/.sushi/models/beamster/...` 文件数，不足 212 就重跑直到补齐 |
| 启动报内存不足 | 加 `--skip-mem-preflight`；确认 27B / H3 已停 |
| 长 prompt 报 HTTP 400 | 误加了 `--kv-quant 4`，去掉恢复默认 8-bit |
| 本地 curl 返回 502 | 透明代理劫持本地请求，清掉代理变量再 curl |
| 首题特别慢 | KV 缓存冷启动，重启服务清缓存后再问 |
| 回复为空 | 默认开思考模式，把 `max_tokens` 设到 2000 或传参关掉思考 |
