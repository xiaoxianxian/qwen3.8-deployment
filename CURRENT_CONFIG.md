---
permalink: /config/
title: 当前配置与验证
---

# Qwen3.8-27B 本地部署配置快照

> **✅ 2026-11-03 实测状态（先看这里）**：**Ollama 0.40.13 + `qwen3.8:27b-mlx` 正常可用**。M5 Pro 48GB 上实测 100% GPU、上下文 **262144**（模型上限；先 32768 → 65536 因 Hermes ≥64K 硬门槛，但 64K 在真实 agent 长会话下仍溢出截断，11:11 进一步开到最大 262144 才稳定）、GPU 共享内存常驻 ~27 GiB、**decode 26.5–39 tok/s / prefill ~224 tok/s**（两个指标，见下方「实测速度定论」、别混读）、冷启动 2.5–6 s。不需要任何第三方引擎顶替。环境变量四件套（q8_0 / KEEP_ALIVE=30m / NUM_BATCH=2048 / FLASH_ATTENTION=1）经 `launchctl` 落地；MTP 自适应投机解码**确认生效**（`drafted=341 acceptance=0.71`）。
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
| `OLLAMA_KEEP_ALIVE` | `30m` | 模型驻留 30 分钟免重载（冷启动 2.5–6 s 只在 30 分钟无调用后才发生）。**2026-11-03 老板最终裁定 30m**（原话纠正：不是 60 秒、也不是 -1，是 30 分钟，与公众号文章 `OLLAMA_KEEP_ALIVE 30m` 一致）；-1 会永久占 25 GB 显存 idle 不释放，30m 是省显存与免冷启的折中。⚠️ 从 -1 改回 30m 时有个坑：改 plist 文件 ≠ 更新运行时环境，`launchctl setenv` 的旧 `-1` 会残留（重启 Ollama 仍显示 `Forever`），需 `launchctl unload`+`load` 或本人终端重新 `setenv`（见 `TROUBLESHOOTING.md` §6） |
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
| `OLLAMA_KEEP_ALIVE` | 已设 **`30m`**（2026-11-03 老板最终裁定，与公众号文章一致；原话纠正「不是 60 秒、不是 -1，是 30 分钟」）。`ollama ps` 的 `UNTIL` 列会显示 `until <30分钟后的时刻>` 而非 `Forever`；若显示 `Forever` 说明读到的是旧 `-1`，需 `launchctl unload`+`load` 或重新 `setenv`（不只是重启 Ollama，见 `TROUBLESHOOTING.md` §6） |
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

> 🔴 **先读这段，否则下面两个数字会被混读**：**decode 和 prefill 是两件不同的事，别当一个"速度"看。**
> - **decode（写回答）**：模型**逐字生成回答**的速度，受内存带宽限制，**慢**（本机 20–35 tok/s）。你等生成时间主要看这个。
> - **prefill（读提示词）**：模型**一次性消化你的输入**的速度，大批量并行、GPU 算力吃满，**快**（本机 ~224 tok/s）。你等"反应"主要看这个。
> - 两者差 ~7 倍是 GPU 并行 vs 串行的**正常物理结果**，不是配置错、不是 bug。
> - 实测里"23–35 tok/s"指 **decode**；"200+ tok/s"指 **prefill**。之前文档把两个数放同一页没标清楚，是歧义来源，已修正。
> - 类比：prefill = 读书速度（快，读完一次就好）；decode = 写字速度（慢，逐字来）。

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

> ✅ **2026-11-03 干净状态复核（无并发争抢时）**：代码生成（冒泡排序 / 任务队列类）**39.0 / 32.8 tok/s**、开放式长文（递归解释 350 token）**26.7 tok/s**，与 37.8 峰值同档。这组数字是在**清空并发会话后**实测的，对应 MTP 自适应投机解码生效（server.log `drafted=341 accepted=241 acceptance=0.71`）。⚠️ 之前有次测到 28.3 tok/s 是被一个 93K token 的并发大请求抢占资源所致——**测 decode 速度前务必确认没有别的会话在同时调模型**，否则测出来的是"排队 + 争抢"的脏数字。

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
2. **不要手动加 `draft_num_predict`**：0.40.13 的 MLX runner **已默认自适应投机解码**，官方标签原样最快。本机对拍：官方标签 34.9 tok/s vs 手动加 `draft_num_predict 3` 只有 28.0 tok/s。此项仅对 GGUF 路线仍需显式开启（见 `TROUBLESHOOTING.md` §5）。**2026-11-03 复核确认**：当前模型 `ollama show --parameters` 里**没有** `draft_num_predict`，但实测代码生成 39.0 tok/s、server.log 出现 `speculative decode stats ... drafted=341 accepted=241 acceptance=0.71`——证明 MLX 0.40+ 确实自适应投机解码、无需手动开。
3. **`iogpu.disable_wired_collector=1` 重启失效**：治「空闲后首个请求要重新从 swap 页入权重」，开机需重跑一次 `sudo sysctl iogpu.disable_wired_collector=1`。
4. **使用 127.0.0.1 而非 localhost**：避免代理与 IPv6 路由问题。
5. **跨版本测试 Ollama 必须隔离模型目录**：旧版二进制启动 GC 会清空新版模型库，见 `TROUBLESHOOTING.md` §11。
6. **🔴 修正（2026-11-03 复核，作废 11-02 的旧说法）**：早前写"`qwen3.8:27b-mlx` 官方 tag 不含 MTP、要靠仓库 Modelfile 的 `draft_num_predict 3` 固化"是**0.33 时代的遗留说法，在 0.40+ 的 MLX 上已过时**。事实是：MLX 原生版**自带** `RENDERER qwen3.8` + `CAPABILITY vision/tools/thinking`，即使 `TEMPLATE` 是裸 `{{ .Prompt }}`，多模态也能正常工作（靠 RENDERER 不靠 TEMPLATE）；MTP 投机解码也是 **runner 级自适应**，无需 Modelfile 手动加 `draft_num_predict`（手动加反而 -20%，见注意事项第 2 条）。**当前正确状态**：`ollama show --parameters` 里**没有** `draft_num_predict` 是**正常的**，不代表 MTP 没开。**正确验法**：① server.log 出现 `speculative decode stats ... drafted=N`（N>0 即 MTP 生效，本机 00:29 实测 `drafted=341 accepted=241 acceptance=0.71`）；② 实测代码生成 ≥32 tok/s（裸速只有 ~9.7）。**别用 `ollama show` 找 `draft_num_predict`**——那字段根本不显示，会误判成"MTP 丢了"。

---

## 📋 复用检查清单（部署 Qwen4-27B 或其他新模型时对照跑一遍）

> 这是 Qwen3.8 整套踩坑经验的**可复用骨架**。换模型时**不必重走弯路**——把下面每一项的"值"替换成新模型/新配置，但**顺序和判断逻辑照搬**。每项都标了"为什么"和"验法"，照着做即可。
>
> ⚠️ **Qwen4-27B 特别提醒**：以下值（262144 / q8_0 / NUM_BATCH=2048 / 26.5 tok/s 等）是 **Qwen3.8 在 M5 Pro 48GB 上实测**的。Qwen4 的模型上限、MLX 是否支持、最优量化档、最优窗口**都要重新实测**，本清单只是"该测什么、按什么顺序、怎么判定"的方法，不是可直接抄的数值。

### 第 0 步：硬件与环境（不变）

| 项 | Qwen3.8 实况 | 换模型时 |
|---|---|---|
| 芯片 | M5 Pro / 48GB 统一内存 | 不变，沿用 |
| Ollama | 0.40.13（GUI 托管） | 确认 GUI 版本，跨版本测试要隔离模型目录 |
| MLX residency 修复 | `sudo sysctl iogpu.disable_wired_collector=1`（**每次开机重跑**） | 不变 |
| 访问端点 | `127.0.0.1`（别用 localhost，避代理/IPv6） | 不变 |

### 第 1 步：选量化档（先比体积 vs 速度 vs 质量）

- **Qwen3.8 选了 MLX 原生 nvfp4（4-bit，~18GB）**，decode 29.9 tok/s 碾压 GSQ/Q5 混合精度。
- 换 Qwen4：先 `ollama pull` 它的**原生 MLX 标签**（若有），跑一次 A/B（12 题 decode + prefill，方法见 `A_B实测对比报告.md`），**别预设** 3.8 的最优档在 4 上也最优。
- **验法**：`A_B实测对比报告.md` 里的方法——同一套 12 题、`num_predict=4096`、`num_ctx` 拉满、串行跑完即卸载，取 Ollama `/api/ps` 的 `eval_count/eval_duration`（decode）与 `prompt_eval_count/prompt_eval_duration`（prefill）。

### 第 2 步：定上下文窗口（GUI 是权威，不是 Modelfile）

- **最易踩**：窗口开关在 `~/Library/Application Support/Ollama/db.sqlite` → `settings.context_length`（Ollama.app「设置」），**优先级高于 Modelfile 的 `num_ctx`**。改 Modelfile 不生效，先改这里。
- Qwen3.8 最终开满 **262144**（模型上限）。**换 Qwen4 时**：
  1. `ollama show <新模型>` 看它**内置上下文上限**（可能是新值，别照抄 262144）；
  2. 按你的客户端（Hermes `MINIMUM_CONTEXT_LENGTH=64000` 硬门槛）+ 真实会话体量，**开满上限**给长会话缓冲；
  3. 但**单轮输入仍压 ~1 万 token**，否则 prefill 分钟级。
- **验法**：`sqlite3 "file:$HOME/Library/Application Support/Ollama/db.sqlite?mode=ro" "select context_length from settings;"` + `ollama ps` 的 `CONTEXT` 列，两者必须一致。

### 第 3 步：开四个环境变量（48GB + 大窗口 + 本地 27B 必开）

| 变量 | Qwen3.8 值 | 作用 | 换模型时 |
|---|---|---|---|
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | 大窗口下 KV 砍半不 swap（**最关键**） | 必开，但确认 Qwen4 的 MLX 是否同样吃 q8_0 |
| `OLLAMA_KEEP_ALIVE` | `30m` | 驻留 30 分钟免重载（老板裁定 30m，非 -1、非 60 秒） | 必开，值按你的取舍定 |
| `OLLAMA_NUM_BATCH` | `2048` | prefill 提速 | 必开 |
| `OLLAMA_FLASH_ATTENTION` | `1` | MLX 内置常开，no-op | 写上无妨 |

- 🔴 **写入方式**：Ollama.app 是独立 GUI 进程，**不读 `.zshrc`**！必须 `launchctl setenv`（本人终端）或 `~/Library/LaunchAgents/com.user.ollama-env.plist`（持久），再**重启 Ollama**。
- 🔴 **改值时的坑**：`launchctl setenv` 的值会**残留在登录会话运行时环境**里，改 plist 文件**不会自动更新运行时**。从 `-1` 改回 `30m` 后，重启 Ollama 仍读旧 `-1`（`ollama ps` 显示 `Forever`）。必须 `launchctl unload`+`load` plist 或本人终端重新 `setenv`（详见 `TROUBLESHOOTING.md` §6）。
- 🔴 **`launchctl setenv` 只能本人终端跑**：macOS GUI 登录会话域边界，**agent / WorkBuddy 沙箱进程连 `dangerouslyDisableSandbox` 都报 `Not privileged to set domain environment`**——这不是沙箱开关能绕过的，必须用户本人终端执行。
- **验法**：`launchctl getenv OLLAMA_KV_CACHE_TYPE` 立即回显 `q8_0`；重启后看 `server.log` 启动段有 `OLLAMA_KV_CACHE_TYPE:q8_0`；`ollama ps` 的 `UNTIL` 列显示 `until <30分钟后时刻>`（而非 `Forever`）即 KEEP_ALIVE=30m 生效。

### 第 4 步：测速（分清 decode 与 prefill，别混读）

- **decode**：Ollama `/api/chat` 官方字段 `eval_count/eval_duration`（Qwen3.8 开放长文 26.5 / 短代码峰值 37.8 / A/B 均值 29.9）。
- **prefill**：`prompt_eval_count/prompt_eval_duration`（Qwen3.8 短 prompt 均值 224 / 长 prompt 实跑 227 / 理论上限 348–383）。
- 🔴 **两个指标差 ~7 倍是正常的**（GPU 并行 vs 串行），不是配置错。
- 🔴 **测速前先确认无并发**：`ollama ps` 确认没有别的会话/进程在同时调模型，否则测出来的是"排队 + 争抢"的脏数字。本机 11-03 就踩过：被一个 93K token 并发大请求抢占时测到 28.3 tok/s，清空后同一模型测到 39.0 tok/s。
- 换 Qwen4：同样跑一遍，**记录两个数**，和 3.8 对比判断"是否更好用"——**比的是同场景 decode+prefill，不是只看一个数**。

### 第 5 步：客户端对齐（接 Hermes 等 agent）

- `~/.hermes/config.yaml` 三处上下文（`model.context_length` / `model.ollama_num_ctx` / `ollama.context_length`）要和 GUI 的 `context_length` **一致**（Qwen3.8 都是 262144）。只改一边不生效。
- Hermes 的 `HERMES_STREAM_STALE_GIVEUP=0`（写 `~/.hermes/.env`）：执行层不主动打断长请求，慢就慢、错就错，反馈权在模型侧。
- **验法**：`grep -nE "context_length|ollama_num_ctx" ~/.hermes/config.yaml` 三处一致；重启 Hermes 后读 gateway 进程环境确认。

### 第 6 步：警惕"并发风暴"（多会话场景）

- Ollama `NUM_PARALLEL=1` **单并发**。多个老会话各带几十 K 历史并发 → 排队 → 超 900s stale → 重试 5 次 → **无限重发堵死槽**。
- **单会话正常用**，别并发开多个老会话；要清就 `hermes sessions list` → `pause` → `gateway stop --yes` → `resume`。
- **验法（本机 11-03 实测）**：`hermes status` 看 `Jobs: N active`（N>1 即并发风暴）；`lsof -nP -i TCP:11434 | grep -c ESTABLISHED` 看连接数；`tail ~/.ollama/logs/server.log` 看有没有 `Prompt processing progress ... total=93510` 这类超大单轮请求（一个会话带 9 万+ token 历史原样发出）。本机 11-03 就抓到 `Jobs 4 active` + 一条 93510 token 的请求把单并发槽占满、把测速请求全堵超时。

### 第 7 步：历史压缩（可选，有代价）

- 纯本地做不了"保留语义的 LLM 摘要"（摘要模型本身要读 100K+，抢单 GPU）。
- 选项：**A 纯本地确定性兜底**（丢中间细节、零隐私代价）/ **B 云端摘要模型**（保语义、历史出机器）。
- ⚠️ **别调高 `context_timeout_seconds`**（会让每轮多一次 100K prefill，比不压缩还慢）。
- 默认**先不加**，试 q8_0 让慢请求能跑完，不够再拍板 A/B。

### 第 8 步：落地归档

- 新模型实测数据（decode / prefill / 内存 / 窗口）写回对应的 `CURRENT_CONFIG.md` + `A_B实测对比报告.md` + `TROUBLESHOOTING.md`，并 `git push` 到仓库，**别只留在本地**。

