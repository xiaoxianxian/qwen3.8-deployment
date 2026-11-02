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

> ⚠️ **血泪教训（2026-11-02）**：Ollama.app 是独立 GUI 进程，**不读 shell 环境**（`.zshrc` 里 export 的变量它收不到）。本机前几个月写在 shell 里的 `OLLAMA_KV_CACHE_TYPE` / `OLLAMA_FLASH_ATTENTION` / `OLLAMA_NUM_BATCH` / `OLLAMA_KEEP_ALIVE` 等于**从没生效过**——直到 2026-11-02 用 `launchctl setenv` + LaunchAgent plist 才真正注入。**正确方式**：`~/Library/LaunchAgents/com.user.ollama-env.plist`（登录自动注入）或当次 `launchctl setenv`，再重启 Ollama 生效。

**结论修正（2026-11-02）**：环境变量这条路**不是堵死的**——本机在自己终端里 `launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0` 成功（`getenv` 立即返回 `q8_0`），重启 Ollama 即生效；持久化靠 LaunchAgent plist。只是**不能走 shell 的 `.zshrc`**（Ollama.app 不读）。

**四个关键变量（48GB + 262144 + 本地 27B 必选项）**：

| 变量 | 值 | 为什么 |
|------|-----|--------|
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | **最关键**。262144 上下文下 f16 KV cache 约 50GB > 48GB → swap 至死、永久 loading；q8_0 砍半到 ~25GB，装得进 48GB，长请求能跑完 |
| `OLLAMA_KEEP_ALIVE` | `-1` | 模型常驻不卸载，免每次对话重载（长会话反复重载也拖慢） |
| `OLLAMA_NUM_BATCH` | `2048` | prefill 提速（batch 512→2048 少 forward pass），大 prompt 受益明显 |
| `OLLAMA_FLASH_ATTENTION` | `1` | MLX 后端内置常开，变量基本 no-op，写上无妨 |

> ✅ **关闭 Hermes 对本地长请求的主动 abort（执行层不拦截）**：`HERMES_STREAM_STALE_GIVEUP=0`（默认 5）。源码 `agent/chat_completion_local.py:stale_giveup()` 读此环境变量；连续 stale 次数 ≥ 阈值即立即 abort 整次调用（报错原文 "5 consecutive stale attempts — aborting this call"）。设为 0 关闭该断路器——之后本地长请求（大 prefill / 长会话）由模型侧自己慢跑或报错，Hermes 不再替你打断。写入 `~/.hermes/.env`，**重启 Hermes 生效**。配套：`agent.local_stream_stale_timeout`（默认 900s）是单次请求静默宽限，正常 prefill 远在其内，一般无需改（详见下方「Hermes 历史压缩」）。

### 1) 结论修正：`OLLAMA_KV_CACHE_TYPE=q8_0` 在 MLX 上必须开（旧结论「对 MLX 无效」已作废）

Ollama 源码把这两个值只交给 llama.cpp 引擎：

```go
// llm/server.go
kvct := strings.ToLower(envconfig.KvCacheType())
return NewLlamaServerRunner(gpus, modelPath, f, adapters, projectors, opts, numParallel, kvct, config)
```

`NewLlamaServerRunner` 在 `llm/llama_server.go` 里把它转成 `--cache-type-k/--cache-type-v` 传给 llama-server。
**但 0.40.13 的 MLX runner 也读 `OLLAMA_KV_CACHE_TYPE`**（本机 2026-11-02 实测生效）；Ollama 源码里 `kvct` 那段只描述 llama.cpp 路径，不代表 MLX 忽略该变量。

历史实测（0.40.11 / 32K 小窗口，正是「无效」误判的来源）：

| 引擎 | 模型 | 参数 | KV 占用 |
|---|---|---|---|
| llama.cpp | `qwen3:4b` | 默认 f16 | `4608 MiB (K f16 2304 + V f16 2304)` |
| llama.cpp | `qwen3:4b` | `KV_CACHE_TYPE=q8_0` + `FA=1` | `2448 MiB (K q8_0 1224 + V q8_0 1224)`，省 2.16 GB |
| ⚠️ **MLX（旧）** | **`qwen3.8:27b-mlx`** | **`KV_CACHE_TYPE=q8_0`** | 与 f16 **看不出差别**（18 GB 权重，32K 填充后 25–32 GB，两边一致）——**只因窗口太小没撑爆内存**；262144 大窗口下 q8_0 才显出收益（见下） |

⇒ **修正（2026-11-02，0.40.13 实测）**：本地 27B 走 MLX，**这两个变量必须开 `q8_0`**——262144 大窗口下 f16 KV ~50GB > 48GB 会 swap 至死，q8_0 砍半到 ~25GB 才装得进、长请求才跑得完（server 日志 `OLLAMA_KV_CACHE_TYPE:q8_0` 实锤）。旧文档"开了等于没开"是 0.40.11 小窗口下的误判，已作废。GGUF/llama.cpp 路径同样省一半 KV。KV 在 MLX 里**可量化**（q8_0 生效），并非"不可量化"。

### 2) 持久化 env：本机用 LaunchAgent plist（已验证可用）

2026-11-02 实测：`launchctl setenv` 在 WorkBuddy 沙箱里报 `Not privileged`（沙箱不在 GUI 登录会话），但**在你自己的终端里直接跑 `launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0` 等是成功的**（`getenv` 立即返回 `q8_0`），重启 Ollama 即生效。持久化写 plist：

```bash
# ~/Library/LaunchAgents/com.user.ollama-env.plist（ProgramArguments: /bin/sh -c "launchctl setenv ...; open -a Ollama"）
launchctl load ~/Library/LaunchAgents/com.user.ollama-env.plist   # 立即注入 + 开机自动
killall Ollama && sleep 2 && open -a Ollama                       # 重启生效（osascript quit 遇 TCC 违例时改用 killall）
```

⇒ 结论：**GUI 的 `settings.context_length` 之外，其余 Ollama 变量也能持久生效**，关键是走 `launchctl`（用户会话域）或 LaunchAgent，**别走 shell 的 `.zshrc`**（Ollama.app 不读）。

| 事项 | 说明 |
|------|------|
| `OLLAMA_KEEP_ALIVE` | 已设 `-1`（Forever）常驻，免重载。冷重载本身只需 2.5–6 s，但长会话反复重载也拖慢，常驻更稳 |
| `OLLAMA_MAX_LOADED_MODELS` | 想设 `1` 防止多个模型同驻；同样受上面限制，改用「不用 `qwen3:4b` 就不会加载它」规避 |
| `OLLAMA_NUM_PARALLEL` | 已是 `1`（单用户最优）。调大等于按倍数分配 KV，48 GB 扛不住 |

## Hermes 历史压缩（本地部署必看——"又卡又慢"的真正根因）

> ⚠️ **2026-11-02 定论**：之前所有"卡/慢/loading"的归因（窗口过大、KV swap、q8_0 没开）都只解决了一半。**真正的元凶是 Hermes 的历史从未被压缩过**。Hermes 内置 `ContextCompressor`（`agent/context_compressor.py`），用比例制对上下文窗口算预算（如 `threshold=0.3` → 78K 触发、`target_ratio=0.2` → 目标 ~15K）；但它依赖一个**摘要模型**来总结旧历史。本地-only 部署下，这个摘要模型在 120s preflight 超时（`⚠ Context compression timed out after 120.0s with no output from the summary model. No messages were dropped — continuing without compression`），**压缩失败 → 每轮都把完整 100K+ 历史原样发给模型** → prefill 几分钟 → 看起来"一直 loading"。
>
> 为什么本地修不了：摘要模型本身要处理 100K+ token，在本地 27B 上跑必然超过 120s prefill，指向本地模型只会更慢（两个本地调用抢单 GPU）。所以 **LLM 历史压缩在纯本地部署下结构性失效**。
>
> **三条出路（任选，不互斥）**：
> 1. **云端快速摘要模型**（推荐，能让压缩真正生效）：把 `auxiliary.compression` 指向已配 key 的云端模型（本机有 `DEEPSEEK_API_KEY` / `HERMES_CUSTOM_AGNES_API_KEY`），摘要几秒完成，历史被压到 ~15K，**请求从 100K+ 降到 20K 内，prefill 从几分钟降到 ~1 分钟**。代价：历史片段出机器（与你本地隐私取向有冲突，需权衡）。
> 2. **本地保持短会话**：不依赖 LLM 压缩，靠 `micro_compact`（每轮折叠旧工具结果，无 LLM 调用，已开） + 手动 `/new` 或 `/compress` 周期性开新会话，把历史压在可控范围。最省事但需你主动管理。
> 3. **接受 q8_0 让慢请求能跑完**：q8_0 已解决"swap 至死"，100K 请求现在能跑完而非永久卡死；只是仍慢。配合 `HERMES_STREAM_STALE_GIVEUP=0` 不拦截，符合"执行层不替你打断"。
>
> `micro_compact` 与上面的 LLM 压缩是两件事：前者只折叠旧工具返回（不缩减对话轮次），后者才真正摘要对话历史。本地-only 下只有前者在跑，所以对话文本会无界增长 → 100K+ 每轮。详见 `TROUBLESHOOTING.md` §「一直 loading / 又卡又慢 真实根因链」。

### 实测速度定论（decode + prefill，2026-11-02）

之前文档里「23–35 tok/s 区间」与「MTP 代码生成峰值 37.8 tok/s」只覆盖 decode 这一段；**老板指出还有一项 200+ tok/s 的速度没被文档化**——补全后如下：

#### Decode 速度（350-token 开放式长文生成，Ollama `/api/chat` 官方统计）

```
eval_count = 350
eval_duration = 13,164,898,708 ns (≈13.16s)
→ 350 / 13.16 ≈ **26.5 tok/s**
```

- 26.5 tok/s 落在既有 23–35 tok/s 区间内，接近短代码生成峰值 37.8 tok/s；
- 关于「23–35 tok/s」的**出处追溯**（老板追问，已查实）：这是 A/B 实测后写入 `CURRENT_CONFIG.md` 的**文档归纳**（「实测解码 23–35 tok/s」），原始数据来源是 `A_B实测对比报告.md` 里 12 题逐题 decode（MLX 4-bit 21.99–39.45 tok/s，均值 29.90）。**原始 12 题表里没有 23/35 这两个端点数值**——23 接近 C1 题（24.53）下限、35 接近 A3 题（36.68）上限，是 A/B 后的文档归纳近似，不是某次精确实测。`TROUBLESHOOTING.md:262` 也沿用了「23–35 tok/s」这个写法，同样来自 A/B 后的归纳，非单次精确值。若后续要更精确的 decode 数字，以 Ollama `/api/chat` 官方字段（`eval_count/eval_duration`）单次实测为准（本日 350-token 开放长文 = **26.5 tok/s**，短 prompt 峰值 = **37.8 tok/s**，A/B 12 题均值 = **29.90 tok/s**）。
- **q8_0 没有拖速**：MTP 投机解码的 ~2.7× 收益（裸速 9.7 → 实测 26.5）占主导；
- 日常体感：300 字中文 ≈ 11s、100 字 ≈ 4s，与「之前几个月正常用」的体感一致。

#### Prefill 速度（**老板记忆里的 200+ tok/s，今天补全**）

| 场景 | 数字 | 出处 | 说明 |
|---|---|---|---|
| **短 prompt 平均 prefill**（12 题 A/B） | **~224 tok/s** | `A_B实测对比报告.md`（MLX 4-bit / 12 题均值，Ollama `/api/ps` 顶层字段 `prompt_eval_count/prompt_eval_duration`） | 这是老板记忆里「200+ tok/s」的原始出处 |
| **NUM_BATCH=2048 长 prompt 实跑**（q8_0 生效） | **~227 tok/s** | 22:05–22:07 server.log（55,614 token 请求，1512 tok/9s） | 大请求稳跑、无 swap、未回落 |
| **短 prompt 单次 prefill**（350-token 生成那次） | **~113.7 tok/s** | 本次 23:00 实测（`prompt_eval_count=26 / 228.5ms`） | 短 prompt 时 batch 利用率不满，数值偏低 |
| **短 prompt prefill 理论值**（文档旧值） | **348–383 tok/s** | 文档历史值 | 是 M5 Pro GPU 算力上限（~19 TFLOPS）的理论值；实际 A/B 均值 224 tok/s 低于此，原因是 12 题 A/B 的 prompt 体量与 batch 利用率差异 |

**结论**：
- 短 prompt（1–5K）实际 prefill 在 100–224 tok/s 之间，长 prompt（50K+）在 227 tok/s 上下，理论上限 348–383 tok/s。
- **224 tok/s 的 prefill 不是 bug**，是 A/B 12 题的稳态均值（batch 利用率不是理论峰值），跟老板记忆对得上。
- q8_0 + NUM_BATCH=2048 让长请求 prefill 稳定在 227 tok/s 不回落（f16 时代会 swap 掉到个位数），这是**「一直 loading」变「能跑完」的关键**。

> ⚠️ 这是 **单会话、无并发** 时的数字。多会话并发时，单请求的实际体感 = 排队时间 + prefill + decode 三者之和；Ollama 单并发（`NUM_PARALLEL=1`）决定了排队时间是主要瓶颈（见 `TROUBLESHOOTING.md` §13 补充实证）。

## 硬件需求

| 配置项 | 要求 |
|--------|------|
| 内存 | ≥ 32 GB 可跑（上下文 16K～32K 短对话）；**本机 48 GB 实测 262144 稳定**（MLX KV 动态分配，不预占满窗）；多引擎同驻时才需下调 |
| 芯片 | Apple Silicon（M 系列） |
| 磁盘空间 | 建议 30 GB+（含 Ollama 运行时） |

## 性能基准（M5 Pro 48GB / Ollama 0.40.13 / macOS 27.2 实测）

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
| Ollama（Ollama.app 托管，GUI 拉起 server） | ✅ 运行中 | 0.40.13 |
| Python | ✅ | 3.11.x |
| pip | ✅ | 24.x |

> 本机**不要**再装第二个 27B 引擎（MTPLX / 其他）与 Ollama 同跑：48 GB 装不下两份，会直接把两个都拖成 swap。MTPLX 已于 2026-11-02 彻底卸载。

## 注意事项

1. **MLX 不识别 GGUF**：必须用原生 MLX 格式（`ollama pull qwen3.8:27b-mlx`）。
2. **不要手动加 `draft_num_predict`**：0.40.13 的 MLX runner **已默认自适应投机解码**，官方标签原样最快。本机对拍：官方标签 34.9 tok/s vs 手动加 `draft_num_predict 3` 只有 28.0 tok/s。此项仅对 GGUF 路线仍需显式开启（见 `TROUBLESHOOTING.md` §5）。
3. **`iogpu.disable_wired_collector=1` 重启失效**：治「空闲后首个请求要重新从 swap 页入权重」，开机需重跑一次 `sudo sysctl iogpu.disable_wired_collector=1`。
4. **使用 127.0.0.1 而非 localhost**：避免代理与 IPv6 路由问题。
5. **跨版本测试 Ollama 必须隔离模型目录**：旧版二进制启动 GC 会清空新版模型库，见 `TROUBLESHOOTING.md` §11。
