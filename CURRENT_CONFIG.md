---
permalink: /config/
title: 当前配置与验证
---

# Qwen3.8-27B 本地部署配置快照

> **✅ 2026-11-02 实测状态（先看这里）**：**Ollama 0.40.13 + `qwen3.8:27b-mlx` 正常可用**。M5 Pro 48GB 上实测 100% GPU、上下文 **262144**（模型上限；先 32768 → 65536 因 Hermes ≥64K 硬门槛，但 64K 在真实 agent 长会话下仍溢出截断，11:11 进一步开到最大 262144 才稳定）、GPU 共享内存常驻 ~27 GiB、解码 23–35 tok/s、冷启动 2.5–6 s。不需要任何第三方引擎顶替。
>
> ⚠️ **本页 11-01 版本写的是「Ollama MLX runner 病态，主用 MTPLX 顶替」，该结论已于 11-02 推翻并被本页删除。** 真正原因是三件事叠加：① 上下文被设成 262144（不是 Modelfile 的 131072）；② 两个 27B 引擎同时驻留，48 GB 装不下；③ 单轮 prompt 高达 7.8 万 token。完整判定链与推翻过程见 `TROUBLESHOOTING.md` §10。
>
> ⚠️ **48 GB 机器的一条硬边界**：上下文窗口能设多大，不等于能干活。本机预填充实测 348–383 tok/s，所以 32K token 的 prompt 光读入就要 88 秒。**窗口已开到模型上限 262144 给长会话留缓冲，但单轮输入仍建议压在 1 万 token 以内**——否则一次 prefill 就要几十秒甚至分钟级，跟窗口大小无关。别按 262K 宣传值去塞长 prompt。

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
| 本机当前值 | **262144**（Ollama.app 上下文开关开到最大，即模型上限。先 32768→65536 因 Hermes ≥64K 硬门槛，但 64K 在真实 agent 长会话下仍溢出截断，最终开到 262144 才稳定。Hermes 有 `MINIMUM_CONTEXT_LENGTH=64000` 硬下限，低于它建 agent 直接 `ValueError`；262144 在 48GB 单模型实跑正常，MLX KV 动态分配不预占满窗，idle 仅 ~18–31 GB） |
| 查看命令 | `sqlite3 "file:$HOME/Library/Application Support/Ollama/db.sqlite?mode=ro" "select context_length from settings;"` |
| 修改前提 | 必须先**完全退出 Ollama.app**（只 `pkill ollama serve` 不够，GUI 会写回旧值；本机 `osascript quit` 遇 TCC 权限违例，用 `pkill -f "/Applications/Ollama.app"`） |
| 校验 | `ollama ps` 的 `CONTEXT` 列 / `curl -s localhost:11434/api/ps \| grep context_length`，应与上面的值一致 |

> ⚠️ **修正此前误判（两处，均来自 11-01 争用场景的误读，已在 11-02 末次复核作废）**：本页早前写"262144 在 48 GB 必然 evict"——那是对一次**争用场景**日志的误读（当时同时驻留多引擎 + 已被 swap 挤占）。单模型开到 262144 正常（`/api/ps` 显示 vram ~27 GiB、未 evict）。**"262144 预占 36 GB→swap 抖动→7 分钟超时"也是误诊断**：36 GB 数字来自 11-02 上午 MTPLX 还占 40 GB 时的 `evicting` 日志，非单跑 262144 实况（262144 idle 仅 ~18–31 GB，MLX KV 动态分配不预占满窗）；7 分钟超时是一个 156K token 超大单轮 prompt 占满 Ollama 单并发槽位所致，是 prompt 过大不是窗口过大——262144 正把这 156K 请求正常返回 200。本机最终定值 **262144**（见下方「为什么是 262144」）。

### 为什么是 262144（不是 64K / 128K，也不是 32768）（2026-11-02 老板裁定）

**Hermes 从 64K 起步**：`agent/model_metadata.py:274 MINIMUM_CONTEXT_LENGTH = 64_000`，低于此值在建 agent 阶段直接 `ValueError`，重试无效。所以只要这台机要接 Hermes，32768 就不可用。

**64K / 128K 在真实 agent 长会话下会溢出截断，不够用。** 系统提示 4–8K + 工具 schema + 多轮历史，128K 窗口在长会话里照样被撑爆、尾部被截。老板实测把开关开到模型上限 **262144** 才稳定不截断。

**262144 在 48GB 单模型实跑正常，不会抖。** MLX 的 KV 缓存是**动态分配**（按实际用量增长，不预占满窗），262144 idle 仅占 ~18–31 GB；之前"预占 36 GB→swap 抖动"是对 MTPLX 同驻争用日志的误读。262144 装得下 156K token 的单轮请求并正常返回 200。

> ✅ **Hermes 不会写回上下文**：经源码核验（`agent/model_metadata.py:2222` 的 `get_model_context_length` 对合法正整数直接 `return`、从不回写 `config.yaml`；`gateway/run.py:2363` 每请求重读 `config.yaml`），Hermes 的 `model.context_length` / `model.ollama_num_ctx` / `ollama.context_length` 三处设成什么就保持什么，**重启动不会变回 262144**。早期文档写的"复发红线：Hermes 重启同步回 262144"是误读，已作废。客户端三处与服务端 GUI `settings.context_length` **都设 262144** 即一致，无需每次重启后手动核对。

配套的客户端侧配置（Hermes，三处必须一致）：

```yaml
model:
  context_length: 262144      # 决定压缩器窗口，也是地板检查的实际输入；与服务端 GUI 一致取模型上限
  ollama_num_ctx: 262144      # 一并抬高，避免两者不一致
ollama:
  context_length: 262144
```

⚠️ 关键：**服务端窗口由 GUI 的 `settings.context_length` 决定**（见上表「权威来源」），客户端 `ollama_num_ctx` 是请求级上限。两者**都**要改到 262144，只改一边不生效。

> 「单轮 ≤1 万 token」的硬规则**不变**：即使开到 131072，预填充物理上限仍是 348–383 tok/s（27B 稠密模型的算力墙），10K token 约 29 秒、32K 约 88 秒、128K 约 5–6 分钟。**控制单轮输入才是正解**——Hermes 的 `file_read_max_chars` / `tool_output.max_bytes` 已下调（见 `TROUBLESHOOTING.md` §12），但仍可能由多轮历史累出 5 万+ token 请求；超长文档/代码库任务优先走云端 `agnes-3.0-flash`（Hermes 已配好的 provider），本地只做隐私敏感部分。

## 环境变量配置

本机实测（2026-11-02）：`OLLAMA_CONTEXT_LENGTH` / `OLLAMA_FLASH_ATTENTION` / `OLLAMA_KV_CACHE_TYPE` / `OLLAMA_KEEP_ALIVE` 经 `launchctl getenv` **全为空**，即当前完全没靠环境变量，配置由 GUI 设置 + 模型自带默认值驱动。

> ✅ **关闭 Hermes 对本地长请求的主动 abort（执行层不拦截）**：`HERMES_STREAM_STALE_GIVEUP=0`（默认 5）。源码 `agent/chat_completion_local.py:stale_giveup()` 读此环境变量；连续 stale 次数 ≥ 阈值即立即 abort 整次调用（报错原文 "5 consecutive stale attempts — aborting this call"）。设为 0 关闭该断路器——之后本地长请求（大 prefill / 长会话）由模型侧自己慢跑或报错，Hermes 不再替你打断。写入 `~/.hermes/.env`，**重启 Hermes 生效**。配套：`agent.local_stream_stale_timeout`（默认 900s）是单次请求静默宽限，56K/156K 的 prefill（3–7 分钟）远在其内，一般无需改；只有单请求可能超过 15 分钟才需要抬高它。

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
| 内存 | ≥ 32 GB 可跑（上下文 16K～32K 短对话）；**本机 48 GB 实测 262144 稳定**（MLX KV 动态分配，不预占满窗）；多引擎同驻时才需下调 |
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
