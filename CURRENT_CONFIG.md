---
permalink: /config/
title: 当前配置与验证
---

# Qwen3.8-27B 本地部署配置快照

> **✅ 2026-11-02 实测状态（先看这里）**：**Ollama 0.40.13 + `qwen3.8:27b-mlx` 正常可用**。M5 Pro 48GB 上实测 100% GPU、上下文 **65536**（10:40 由 32768 抬起，因 Hermes 要求 ≥64K）、常驻 20–22 GB、解码 23–35 tok/s、冷启动 2.5–6 s。不需要任何第三方引擎顶替。
>
> ⚠️ **本页 11-01 版本写的是「Ollama MLX runner 病态，主用 MTPLX 顶替」，该结论已于 11-02 推翻并被本页删除。** 真正原因是三件事叠加：① 上下文被设成 262144（不是 Modelfile 的 131072）；② 两个 27B 引擎同时驻留，48 GB 装不下；③ 单轮 prompt 高达 7.8 万 token。完整判定链与推翻过程见 `TROUBLESHOOTING.md` §10。
>
> ⚠️ **48 GB 机器的一条硬边界**：上下文窗口能设多大，不等于能干活。本机预填充实测 348–383 tok/s，所以 32K token 的 prompt 光读入就要 88 秒。**窗口虽已抬到 65536，日常会话仍建议压在 32768 以内、单轮输入控制在 1 万 token 以内**，别按 262K 宣传值去塞。

## 模型信息

| 属性 | 值 |
|------|-----|
| 模型名称 | qwen3.8:27b-mlx |
| 类型 | MLX 原生格式，量化 nvfp4（4-bit） |
| 体积 | ~18 GB（运行时常驻 20–22 GB） |
| 参数量 | 27.8B / 架构 qwen3_5 / 模型内置上下文上限 262144 |
| 能力 | tools + vision + thinking |
| 下载源 | https://ollama.com/library/qwen3.8:27b-mlx |
| 国内镜像 | `HF_ENDPOINT=https://hf-mirror.com ollama pull qwen3.8:27b-mlx` |

## 上下文由谁决定（最容易踩的一处）

| 项 | 说明 |
|----|------|
| **权威来源** | `~/Library/Application Support/Ollama/db.sqlite` → `settings.context_length`（即 Ollama.app「设置」里的上下文长度） |
| **优先级** | GUI 设置 **高于** Modelfile 的 `num_ctx`。改了 Modelfile 不生效，先查这里 |
| 本机当前值 | **65536**（2026-11-02 10:40 由 32768 抬起，见下方说明） |
| 查看命令 | `sqlite3 "file:$HOME/Library/Application Support/Ollama/db.sqlite?mode=ro" "select context_length from settings;"` |
| 修改前提 | 必须先**完全退出 Ollama.app**（只 `pkill ollama serve` 不够，GUI 会写回旧值；本机 `osascript quit` 遇 TCC 权限违例，用 `pkill -f "/Applications/Ollama.app"`） |
| 校验 | `ollama ps` 的 `CONTEXT` 列 / `curl -s localhost:11434/api/ps \| grep context_length`，应与上面的值一致 |

> 262144 在 48 GB 机器上必然失败。日志判据：`predicted="24.8 GiB" predicted_num_ctx=262144 available="11.9 GiB" system_limited=true` → `evicting`，表现为「点了没反应 / 模型加载不上」。

### 为什么是 65536 而不是 32768（2026-11-02 变更）

**Hermes 从 64K 起步**：`agent/model_metadata.py:274 MINIMUM_CONTEXT_LENGTH = 64_000`，低于此值在建 agent 阶段直接 `ValueError`，重试无效。所以只要这台机要接 Hermes，32768 就不可用——报错与排查过程见 `TROUBLESHOOTING.md` §12。

配套的客户端侧配置（Hermes）：

```yaml
model:
  context_length: 65536      # 决定压缩器窗口，也是地板检查的实际输入
  ollama_num_ctx: 65536      # 一并抬高，避免两者不一致
```

⚠️ 关键：**`/v1` 端点忽略请求级 `num_ctx`**（实测请求写 65536、`/api/ps` 仍报 32768）。因此客户端改配置只解决报错，服务端窗口必须靠上面的 GUI 值——两者**都**要改。

> 本页性能表与「单轮 ≤1 万 token」的硬规则**不变**：抬到 64K 只是让客户端肯启动，不改变预填充 348–383 tok/s 的物理上限。32K 仍是你该主动控制的日常水位。

## 环境变量配置

本机实测（2026-11-02）：`OLLAMA_CONTEXT_LENGTH` / `OLLAMA_FLASH_ATTENTION` / `OLLAMA_KV_CACHE_TYPE` / `OLLAMA_KEEP_ALIVE` 经 `launchctl getenv` **全为空**，即当前完全没靠环境变量，配置由 GUI 设置 + 模型自带默认值驱动。

**先说结论：这台机器上，环境变量这条路是堵死的，而且有两个变量本来就没用。**

### 1) `OLLAMA_FLASH_ATTENTION` / `OLLAMA_KV_CACHE_TYPE` 对 MLX 后端无效

Ollama 源码把这两个值只交给 llama.cpp 引擎：

```go
// llm/server.go
kvct := strings.ToLower(envconfig.KvCacheType())
return NewLlamaServerRunner(gpus, modelPath, f, adapters, projectors, opts, numParallel, kvct, config)
```

`NewLlamaServerRunner` 在 `llm/llama_server.go` 里把它转成 `--cache-type-k/--cache-type-v` 传给 llama-server。
**MLX runner 是另一条路径，根本不接收这个参数**，它自己管理 KV。

本机实测印证（2026-11-02，同一台机、两套配置对比启动日志）：

| 引擎 | 模型 | 参数 | KV 占用 |
|---|---|---|---|
| llama.cpp | `qwen3:4b` | 默认 f16 | `4608 MiB (K f16 2304 + V f16 2304)` |
| llama.cpp | `qwen3:4b` | `KV_CACHE_TYPE=q8_0` + `FA=1` | `2448 MiB (K q8_0 1224 + V q8_0 1224)`，省 2.16 GB |
| **MLX** | **`qwen3.8:27b-mlx`** | **`KV_CACHE_TYPE=q8_0`** | **与 f16 无差别**（18 GB 权重，32K 填充后 25–32 GB，两边一致） |

⇒ **本机跑 27B 走 MLX，这两个变量开了等于没开**。想给 27B 省内存，唯一旋钮是**降低上下文**（KV 在 MLX 里是 f16 且不可量化）。
⇒ 反过来，如果哪天跑的是 GGUF 模型（`qwen3:4b`、`*-q5` 等 llama.cpp 路径），这两个变量是**实打实省一半 KV**。

### 2) 想持久化 env：本机三条路全被系统阻断

2026-11-02 逐条实测：

| 方式 | 结果 |
|---|---|
| `launchctl setenv` | `Not privileged to set domain environment`（macOS 27 收紧） |
| `launchctl bootstrap` / `load -w` | `Bootstrap failed: 5: Input/output error`（连最小 `/bin/echo` plist 都失败，与 plist 内容无关） |
| `launchctl submit` | 静默失败，job 不进域 |
| `open -a Ollama --env VAR=...` | App 进程收到，但 server 子进程不继承（server 的 env 由它自己重建） |

⇒ 结论：**能持久生效的只有 GUI 的 `settings.context_length`**。其余变量只能手动 `env ... ollama serve` 起一次、当次有效。
⇒ 副作用：Ollama.app 一打开就会杀掉手动起的 serve、换回自己的（实测 pid 从 1383 变 6420），所以手动起的那套只适合「不开 GUI」的用法。

| 事项 | 说明 |
|------|------|
| `OLLAMA_KEEP_ALIVE` | 本机冷重载实测只需 2.5–6 s，5 分钟默认值够用，不值得为它换掉 GUI |
| `OLLAMA_MAX_LOADED_MODELS` | 想设 `1` 防止多个模型同驻；同样受上面限制，改用「不用 `qwen3:4b` 就不会加载它」规避 |
| `OLLAMA_NUM_PARALLEL` | 已是 `1`（单用户最优）。调大等于按倍数分配 KV，48 GB 扛不住 |

## 硬件需求

| 配置项 | 要求 |
|--------|------|
| 内存 | ≥ 32 GB 可跑（上下文 16K～32K）；**≥ 64 GB 才建议把 num_ctx 提到 131072** |
| 芯片 | Apple Silicon（M 系列） |
| 磁盘空间 | 建议 30 GB+（含 Ollama 运行时） |

## 性能基准（M5 Pro 48GB / Ollama 0.40.11 / macOS 27.2 实测）

| 指标 | 实测值 |
|------|--------|
| 解码（200 token 代码生成） | 34.9 tok/s |
| 解码（20–30 token 短答） | 23–24 tok/s |
| 预填充 | 348–383 tok/s（已压到 M5 Pro GPU 算力上限） |
| 冷启动加载 | 2.5–6 s（keep_alive 存续期内热态 0 s） |
| 常驻内存 | 20–22 GB，100% GPU |
| 空闲 60 s 后首请求 | 0.46 s（`iogpu.disable_wired_collector=1` 时） |
| 工具调用 | `finish_reason: tool_calls`，参数正确 |
| 视觉 | 正常（单张图约 100–130 prompt token） |

**上下文成本（按 360 tok/s 预填充折算，这是选窗口大小的唯一依据）**

| 单轮 prompt | 光读入耗时 | 能否干活 |
|---|---|---|
| 2 K | ~6 s | 顺畅 |
| 4 K | ~14 s | 可以 |
| 10 K | ~29 s | 勉强 |
| 32 K（吃满 32768 窗口） | ~88 s | 不能 |
| 78 K | ~217 s | 物理上不行 |

## 已安装工具

| 工具 | 状态 | 版本 |
|------|------|------|
| Ollama（Ollama.app 托管，GUI 拉起 server） | ✅ 运行中 | 0.40.11 |
| Python | ✅ | 3.11.x |
| pip | ✅ | 24.x |

> 本机**不要**再装第二个 27B 引擎（MTPLX / 其他）与 Ollama 同跑：48 GB 装不下两份，会直接把两个都拖成 swap。MTPLX 已于 2026-11-02 彻底卸载。

## 注意事项

1. **MLX 不识别 GGUF**：必须用原生 MLX 格式（`ollama pull qwen3.8:27b-mlx`）。
2. **不要手动加 `draft_num_predict`**：0.40.11 的 MLX runner **已默认自适应投机解码**，官方标签原样最快。本机对拍：官方标签 34.9 tok/s vs 手动加 `draft_num_predict 3` 只有 28.0 tok/s。此项仅对 GGUF 路线仍需显式开启（见 `TROUBLESHOOTING.md` §5）。
3. **`iogpu.disable_wired_collector=1` 重启失效**：治「空闲后首个请求要重新从 swap 页入权重」，开机需重跑一次 `sudo sysctl iogpu.disable_wired_collector=1`。
4. **使用 127.0.0.1 而非 localhost**：避免代理与 IPv6 路由问题。
5. **跨版本测试 Ollama 必须隔离模型目录**：旧版二进制启动 GC 会清空新版模型库，见 `TROUBLESHOOTING.md` §11。
