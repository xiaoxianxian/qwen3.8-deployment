---
permalink: /troubleshooting/
title: 踩坑排查手册
---

# Qwen3.8 本地部署排查手册（TROUBLESHOOTING）

> 按现象索引的排查手册，内容来自 M5 Pro 48GB / macOS 实测踩坑记录（2026-09）。
> 每个问题包含：现象 → 根因 → 解决。

## 快速索引

| 现象 | 跳转 |
|------|------|
| 读长文档报 `context length exceeded`，或模型"记不住" | [1](#1-上下文长度默认只有-4096) |
| MLX 推理大上下文时报 500 + `context canceled` | [2](#2-mlx-超时-500-context-canceled) |
| 设了 `OLLAMA_LLM_LIBRARY=mlx` 想让 GGUF 走 MLX，没效果 | [3](#3-gguf-无法走-mlx-引擎) |
| 发图报 `400 ... No data iterator found for token: <|video_pad|>` | [4](#4-图片识别-400no-data-iterator) |
| 速度不达预期，日志显示 `specu: no` | [5](#5-mtp-投机解码gguf-手动开--mlx-040-已自适应) |
| 设了 keep_alive，每次调用仍要等冷启动 | [6](#6-keep_alive-对--v1-端点不生效) |
| `curl localhost:11434` 通，但程序连接失败 | [7](#7-localhost-代理与-ipv6-陷阱) |
| 调用成功但回复内容为空 | [8](#8-回复内容为空) |
| 响应慢（整句蹦出，一个字一个字往外挤变慢） | [9](#9-响应速度慢) |
| 系统更新后全挂（探针 0 字节 / 每请求 2-5 分钟 / 模型加载不上） | [10](#10-卡死--模型加载不上--每请求几分钟含-macos-27-后集中爆发的那次) |
| 模型突然从 `ollama list` 消失、权重凭空少了 18 GB | [11](#11-高危模型突然从-ollama-list-消失旧版二进制启动-gc-清库) |
| 第三方客户端（Hermes）切到本地模型就报错，界面只说"出了点问题" | [12](#12-第三方客户端报-context-window--below-64000hermes-实证) |

---

## 1. 上下文长度默认只有 4096

**现象**：读长文档时报 "context length exceeded"，或者模型表现得像"记不住东西"。

**根因**：模型支持 262K 上下文，但 Ollama 默认值只有 4096。超过部分被**静默截断**——不报错，只是模型"看不见"后面的内容。

**解决**：先分清「谁的设置说了算」：

| 谁设的 | 优先级 |
|---|---|
| Ollama.app GUI「设置」→ `db.sqlite` 的 `settings.context_length` | **最高**，会覆盖 Modelfile |
| Modelfile / 请求体里的 `num_ctx` | 次之 |
| `OLLAMA_CONTEXT_LENGTH` 环境变量 | 再之（且 `launchctl setenv` 重启即丢） |

```bash
# 1. 先看 GUI 里实际是多少（改它必须先完全退出 Ollama.app）
sqlite3 "file:$HOME/Library/Application Support/Ollama/db.sqlite?mode=ro" \
  "select context_length from settings;"

# 2. 选值：本机 48 GB 实测 262144 稳定（MLX KV 动态分配，idle ~18–31GB）
#    （早期"262144 必然 evict"是对争用日志的误读，已作废；多引擎同驻才需下调到 32768/65536）

# 3. 校验：CONTEXT 列应与设定一致
ollama ps
```

⚠️ **窗口是容量上限，不是速度**：本机预填充 348–383 tok/s，32K prompt 光读入就要 88 秒（见第 9 节换算表）。开到 262144 给长会话留缓冲是对的，但**单轮输入要压在 ~1 万 token 以内**，否则一次 prefill 几分钟、Ollama 单并发把后续请求全堵死。

---

## 2. MLX 超时 500 `context canceled`

**现象**：MLX runner 处理大上下文（32k+）时，推理中途进程被杀，报 `context canceled` 和 500 Internal Server Error。

**根因**：已知回归 bug，[GitHub Issue #16081](https://github.com/ollama/ollama/issues/16081)。机理：服务器每 10 秒对 runner 做一次健康检查，该检查排队在漫长的推理任务之后；大上下文推理忙起来时，检查等满 10 秒等不到响应，进程被判"失联"强杀。回归自 **v0.23.1/v0.23.2**（实测 0.22.1 正常）。

**解决**：升级 Ollama。修复为 [PR #16086](https://github.com/ollama/ollama/pull/16086)（commit `2b9e024`，2026-05-11 合入）——健康检查改为读缓存的内存快照，不再阻塞等待推理线程。**v0.30+ 已包含修复**；本项目实测 v0.33.3 正常。

---

## 3. GGUF 无法走 MLX 引擎

**现象**：设置了 `OLLAMA_LLM_LIBRARY=mlx` 想强制 GGUF 模型用 MLX 引擎提速，结果完全无效，模型仍走 Metal。

**根因**：MLX runner 不认 GGUF 格式权重。GGUF 只能用 llama.cpp（Metal 后端）。

**解决**：按格式选引擎，不要强设环境变量：

- GGUF 格式 → 走 Metal（`OLLAMA_LLM_LIBRARY` 保持默认）
- MLX 原生格式（如 `qwen3.8:27b-mlx`）→ 自动走 MLX 引擎，无需任何环境变量

> 注：早期结论"Ollama 的 MLX 引擎对该模型不可用"仅指 GGUF 强制走 MLX 这条路；MLX 原生格式走原生 MLX 引擎正常且更快（约 2×）。

---

## 4. 图片识别 400：No data iterator

**现象**：走 `/v1` 端点发图时报 `400 BadRequestError: No data iterator found for token: <|video_pad|>`。

**根因**：Qwen3.8 的 GGUF 版本不内嵌 chat template，Ollama 退回裸模板 `{{ .Prompt }}`，不懂图像 token 处理逻辑。

**解决**：在 Modelfile 中显式写入 Qwen 多模态模板。关键点：用 `{{ .Content }}` 让 Ollama 自动渲染多模态内容；**不能用 `{{ .Content[0] }}`**——Ollama 模板引擎不支持数组索引/切片。完整模板见仓库 [Modelfile](./Modelfile) 或部署文章。

MLX 原生版（`qwen3.8:27b-mlx`）自带视觉投影，无需此步骤。

---

## 5. MTP 投机解码（GGUF 手动开 / MLX 0.40+ 已自适应）

**现象**：速度不达预期。`ollama show` 或服务日志显示 `specu: no`。

**先看你在哪条路上，这两条路的结论相反：**

| 路线 | 结论 |
|------|------|
| **GGUF**（Q5 / GSQ IQ3，llama.cpp 引擎） | MTP **默认关**，需要手动开 `PARAMETER draft_num_predict 3` |
| **MLX 原生**（`qwen3.8:27b-mlx`，Ollama **0.40+**） | **已默认自适应投机解码，不要手动加** |

⚠️ **MLX 路线手动加 `draft_num_predict` 会变慢**。本机 0.40.11 对拍（同 prompt、200 token 代码生成）：

| 配置 | 解码速度 |
|---|---|
| 官方标签原样 | **34.9 tok/s** |
| 手动 `PARAMETER draft_num_predict 3` | 28.0 tok/s（−20%） |

原因：0.40 的 MLX runner 会自己调 draft 深度与接受率，从外部钉死反而干扰。旧 Modelfile 里那条 `draft_num_predict 3` 是 0.33 时代的遗留，**在 0.40+ 的 MLX 上已经过时**。

**GGUF 路线的做法**：Modelfile 中设置：

```dockerfile
PARAMETER draft_num_predict 3
```

- 实测（Q5 GGUF 基线）：代码生成 11.7 → 21.6 tok/s（+85%）；建议取值 3，>6 反而掉速
- 验证：日志出现 `specu: n_max=3`，draft acceptance 0.6~0.85
- 输出无损，属免费提速

**MLX 路线的正确验法（2026-11-03 复核，别用 `ollama show` 找 `draft_num_predict`）**：

`ollama show qwen3.8:27b-mlx --parameters` **不会显示** `draft_num_predict`（它是 runner 级投机参数，不是采样参数），所以"看 `ollama show` 有没有 `draft_num_predict`"这个验法是错的——看到没有会误判成"MTP 丢了"，其实 MTP 好好地自适应开着。正确验法两条：

1. **看 server.log 的投机解码统计**：`grep 'speculative decode stats' ~/.ollama/logs/server.log`，`drafted=N`（N>0）即 MTP 生效。本机 00:29 实测 `iterations=159 drafted=341 accepted=241 acceptance=0.71`。⚠️ 注意**短请求（迭代 <10 次）`drafted=0` 是正常的**——投机解码没机会启动，别拿一次 `ollama run "hi"` 的 `drafted=0` 当"MTP 关了"。
2. **实测速度**：代码生成 ≥32 tok/s（本机 39.0 / 32.8）即 MTP 在跑；裸速只有 ~9.7 tok/s。

---

## 6. keep_alive 对 /v1 端点不生效

**现象**：设置了 `OLLAMA_KEEP_ALIVE=30m`，但每次调用仍等约 6 秒冷启动（模型重新加载）。

**根因**：OpenAI 兼容端点 `/v1/chat/completions` **忽略请求里的 keep_alive 参数**；服务端环境变量对该端点的按请求控制同样不生效。keep_alive 默认 5 分钟，超时即卸载模型。

**解决**：

```bash
# 服务端全局基线（用户级，无需 sudo）
launchctl setenv OLLAMA_KEEP_ALIVE 30m
# 重启 Ollama 生效
```

- 需要按请求控制时，用 Ollama 原生 API `/api/chat`（支持 `keep_alive` 参数）
- /v1 端点依赖上面的全局环境变量

**🔴 新踩坑（2026-11-03）：改了 plist 文件内容 ≠ 运行时环境更新，`launchctl setenv` 的旧值会一直残留**

场景：先 `launchctl setenv OLLAMA_KEEP_ALIVE -1`（永久常驻），后来把 `com.user.ollama-env.plist` 文件里的值改成 `30m`，然后 `killall Ollama && open -a Ollama` 重启。**结果 `ollama ps` 还是显示 `UNTIL Forever`**——因为：

1. `launchctl setenv` 写入的是**当前登录会话的运行时环境**，它不会去读 plist 文件；
2. 改 plist 文件**只是改了磁盘上的文本**，`RunAtLoad` 只在**下次 `launchctl load` 或重新登录**时才执行；
3. 重启 Ollama 只会让它**重新读运行时环境**，而运行时环境里残留的还是旧值 `-1`。

**正确修复（二选一，都要在本人终端跑，WorkBuddy 沙箱连 `dangerouslyDisableSandbox` 都报 `Not privileged to set domain environment`）**：

```bash
# 方案 A：重新 load plist（一次性对齐 plist 里全部变量，推荐）
launchctl unload ~/Library/LaunchAgents/com.user.ollama-env.plist && \
launchctl load ~/Library/LaunchAgents/com.user.ollama-env.plist
# 然后重启 Ollama
killall Ollama && sleep 2 && open -a Ollama

# 方案 B：直接重新 setenv 单个变量
launchctl setenv OLLAMA_KEEP_ALIVE 30m
killall Ollama && sleep 2 && open -a Ollama
```

**验法**：`ollama ps` 的 `UNTIL` 列，`30m` 生效时显示 `until <30分钟后的时刻>`；仍显示 `Forever` 就是读到旧 `-1`，回到上面重来。⚠️ 这是 macOS 的 GUI 会话域安全边界（`launchctl setenv` 必须本人在登录会话里跑），**agent / 沙箱进程无论如何都改不了**，只能由用户本人终端执行。

> ✅ **2026-11-03 01:06 已按方案 A 最终验收通过**：老板本人终端跑完 `launchctl unload`+`load` + 重启 Ollama 后，`ollama ps` 的 `UNTIL` 列显示 `29 minutes from now`（不再是 `Forever`），30m 常驻正式生效；且重启后 MTP 投机解码仍正常（`drafted=84 acceptance=0.95`，decode 39.5 tok/s），未受重启影响。

---

## 7. localhost 代理与 IPv6 陷阱

**现象**：`curl localhost:11434` 能访问，但程序连接失败或返回异常数据。

**根因**：

1. 系统代理（`http_proxy` 等环境变量）会拦截 `localhost` 请求
2. `localhost` 可能解析到 IPv6 `::1`，而 Ollama 只监听 IPv4

**解决**：

- 一律用 `127.0.0.1:11434`，不用 `localhost:11434`
- 本地探测加 `--noproxy '*'`（curl）或清掉代理变量再启动 `ollama serve`

---

## 8. 回复内容为空

**现象**：调用成功（HTTP 200），但 `content` 为空字符串。

**根因**：Qwen3.8 默认开启推理思考（thinking），先消耗 token 预算；`max_tokens` 偏小时思考阶段就把预算吃光，正文输出为空。

**解决**：任选其一：

- 传 `max_tokens: 2000` 或更大
- 传 `think: false` 关闭思考模式

---

## 9. 响应速度慢

**排查顺序（按"先算账、再查配置"的顺序，别一上来调参）**：

```bash
# 1. 先算清这次请求要读多少 token —— 决定等待时间的最大变量
#    看响应里的 usage.prompt_tokens，或服务端日志的 prompt_eval_count
grep -oE "prompt_eval_count[^,}]*" ~/.ollama/logs/server.log | tail -3

# 2. 确认模型常驻（避免冷启动）
ollama ps

# 3. 检查是否触发 swap（有用量说明内存不够，会出现分钟级首 token 延迟）
sysctl vm.swapusage

# 4. MLX 路线别查 specu（0.40+ 自适应），GGUF 路线才需要（见第 5 节）
grep "specu" ~/.ollama/logs/server.log | tail
```

**预填充是 27B 在这类机器上的真实上限，先认清这张表再谈优化**（M5 Pro 48GB 实测 348–383 tok/s，已到 GPU 算力上限）：

| 单轮 prompt | 光读入耗时 |
|---|---|
| 2 K | ~6 s |
| 4 K | ~14 s |
| 10 K | ~29 s |
| 32 K | ~88 s |
| 78 K | ~217 s |

⇒ **读长文档慢，不是引擎的问题，是 token 数 × 单 token 成本。** 想快只有一个方向：把单轮 token 数降下来（分块读取、限制历史回填、裁剪工具输出）。

内存紧张的缓解手段：下调 `num_ctx`（262144 → **32768 / 65536**，仅当多引擎同驻或内存真的吃紧时），或换更小量化档（IQ3_S / Q4_K_M）。注意 `num_ctx` 是**容量**旋钮，不是速度旋钮——它不改变单 token 成本，只决定装不装得下。

---

## 10. 卡死 / 模型加载不上 / 每请求几分钟（含 macOS 27 后集中爆发的那次）

**现象**：本地 `qwen3.8:27b-mlx` 探针 0 字节，或每请求 2–5 分钟；客户端报 `Provider has been unresponsive ... stale attempts`。
注意 `/api/version` 秒回、`/api/ps` 显示模型已加载**都不证明推理活着**，必须实测一次 chat 探针下结论。

**判定链（照序做，哪步通了就停）**：

1. **先看内存和有谁在抢显存，别先怀疑引擎**。
   `sysctl vm.swapusage` + `memory_pressure` + `ps aux | sort -k3 -nr | head`。
   - swap 打满（free 个位数 GB）→ 先杀大户进程 / 重启清空，再复测。
   - **如果还有第二个推理引擎在跑**（MTPLX / 另一份 ollama / 别的 27B 服务），它不是无关进程，它就是主因：48 GB 装不下两份 27B，两边一起被拖进 swap。
2. **核对真实上下文值**（不是 Modelfile 里写的那个）：
   ```bash
   sqlite3 "file:$HOME/Library/Application Support/Ollama/db.sqlite?mode=ro" "select context_length from settings;"
   ```
   - Ollama.app 的 GUI 设置**优先级高于** Modelfile 的 `num_ctx`，改了 Modelfile 不生效是常态。
   - 262144 在 48 GB 上必失败。决定性日志判据：
     `predicted="24.8 GiB" predicted_num_ctx=262144 available="11.9 GiB" system_limited=true` → `evicting`
     也就是「模型反复被驱逐、永远加载不上」，表现就是点了没反应。
   - 改它必须**完全退出 Ollama.app**（GUI 会写回旧值），改完看 `ollama ps` 的 `CONTEXT` 列校验。
3. **核对单轮 prompt 有多大**（最常被忽略的一环）：看响应 `usage.prompt_tokens`，或日志里 `prompt_eval_count`。
   - 本机预填充只有 **348–383 tok/s**，已到 M5 Pro GPU 算力上限（27B 稠密模型每 token ≈ 2×27 GFLOPs，×360 tok/s ≈ 19 TFLOPS）。换算：10 K → 29 s，32 K → 88 s，**78 K → 217 s**。
   - 所以「卡几分钟」很多时候根本不是引擎卡，是**在等 prefill**。数值是数万级时，先修上游（历史回填上限 / 单文件读取上限 / 工具输出上限），再谈引擎。
4. **最后才查引擎与版本**：
   - 引擎层确实有一个真 bug：Ollama [#18744](https://github.com/ollama/ollama/issues/18744)「MLX engine: weights are unwired ~2 s after each request on macOS 27」，根因在 [mlx#4609](https://github.com/ml-explore/mlx/issues/4609)——`requestResidency()` 只发一次、之后从不续租，macOS 约 2 秒后回收。**它的代价是「空闲后首个请求多约 3 秒」，不是分钟级**，量级上解释不了 2–5 分钟。
   - 修复已编进 **0.40.11**（上游 mlx#4633，暴露成 `MLX_METAL_RESIDENCY_REFRESH_INTERVAL_MS`；`strings /usr/local/bin/ollama` 与 `Ollama.app/Contents/Resources/mlx_metal_v{3,4}/libmlx.dylib` 里都能查到），**不需要等新版本**。
   - 缓解：`sudo sysctl iogpu.disable_wired_collector=1`（重启失效）。本机 11-02 复测：该值 =1 时空闲 60 s 后首请求 **0.46 s**。
     ⚠️ 该开关在 macOS 27.2 上是否仍有效，本轮**没做 A/B 对照**，别把它当唯一根因（本机它一直是 1，事故照样发生）。

### 为什么 11-01 那版判断错了（保留作反面教材）

11-01 本页曾把根因判为「Ollama MLX runner 病态」，并给出「换 MTPLX 引擎顶替」的方案。11-02 复核推翻，错在四处推理跳跃：

| 当时的推断 | 实际事实 |
|---|---|
| 小 GGUF 正常 + 27b-mlx 卡 ⇒ 只坏了 27B 的 MLX runner | 当时 MTPLX 正占着 40.6 GB，可用只剩 11.9 GB。小模型装得下、27B@262144 要 24.8 GiB 装不下 ⇒ **这是"大的装不进去"，不是"引擎坏了"** |
| `cache miss total` 逐请求增长、命中 0.4% ⇒ 前缀缓存子系统失效 | 那个 `total` **就是 prompt 长度本身**。会话在增长、每轮 prompt 从 3.6 万涨到 7.4 万 token，前缀对不上自然命中低。**"别去反推 prompt 是哪来的"这个结论恰好把唯一的主因排除掉了** |
| 三个 0.40.x 版本同病 ⇒ 排除版本线 | 版本线确实可排除，但排除它不等于根因在引擎——**三个版本共享同一个 262144 配置和同一个内存挤爆的环境** |
| MTPLX 同机 1.7 s / 28 tok/s 正常 ⇒ MTPLX 是解药 | 那是**独占内存**跑出来的（Ollama 已停）。同 workload 下 MTPLX 本来就比 Ollama 慢约 14%，而且它底层同样是 MLX，同样吃 #18744 |

**教训**：做「引擎隔离实验」时，必须先把另一个引擎停掉并确认内存干净，否则测出来的差异是**内存配额差异**，不是引擎能力差异。

### 被推翻的「顶替方案」

本页曾推荐装 MTPLX 顶替 Ollama。**不要这样做**，三个原因：

1. **同源**：MTPLX 也是 MLX 后端，同样的 residency 问题一个不落。
2. **更慢**：同 workload 对拍 −14%（见 `MTPLX引擎实测-vs-Ollama.md`，那份 10-03 的报告结论本来就是「日常用 Ollama，不推荐换」）。
3. **更危险**：`--allow-swap` 让它的峰值冲到 **74 GB**（机器只有 48 GB），日志出现 `system_thrashing: true` 与反复 `prefill_admission_shed` / `allocation_failure_shed`，端到端掉到 1.6 tok/s。反而把机器按死。

真正修好这台机器的是三件事，与引擎无关：**停掉第二个引擎** + **上下文 262144 → 32768** + **把单轮 prompt 从 7.8 万降到 1 万以内**。改完同一个模型回到 23–35 tok/s，冷启 2.5–6 s。

---

## MLX 与 GGUF / GSQ 并发稳定性（补充）

MLX 单跑极稳：131072 上下文 + MTP 下，5 维质量题 2 轮 10/10 全过、零 OOM（2026-09-10 A/B 实测）。GSQ / GGUF 路线（Q5、IQ3 等）同属 llama.cpp 引擎，单跑 131K 上下文也稳定。此前偶发的"间歇性显存溢出"根因是**多个会话/进程同时调用同一个 MLX 模型**，KV 缓存显存叠加溢出，与 128K 上下文无关。

**部署建议**：

- 日常单跑 / 短中交互：`qwen3.8:27b-mlx`（MLX），**本机 48 GB 实测 262144 稳定**；多引擎同驻时才下调到 32768/65536
- 长 agent 多会话并发：`qwen3.8-q5`（GGUF + llama.cpp，并发更稳）；GSQ IQ3 同为 llama.cpp 路径，并发表现与 Q5 一致，只是更省显存、速度更慢
- 避免多个客户端同时并发调同一个 MLX 模型，错峰使用

> ⚠️ **「装得下」不等于「跑得快」**：容量上限与速度无关，真实等待时间由 **单轮 prompt token 数** 决定（本机 348–383 tok/s 预填充，见第 9 节换算表）。本机窗口开 262144 给长会话留缓冲，但**单轮输入压在 ~1 万 token 以内**才不卡。

## 11. 【高危】模型突然从 `ollama list` 消失（旧版二进制启动 GC 清库）

**症状**
`ollama list` 只剩个别模型，其余全没了；`~/.ollama/models` 体积骤降；服务日志反复刷
`msg="bad manifest" ... error="lstat .../blobs/sha256-xxx: no such file or directory"`。

**根因**
用**别的版本**的 ollama 二进制（比如为做对照而解压的旧版）启动 `serve`，且**沿用了默认模型目录**：

```bash
# ❌ 危险：旧版会拿 ~/.ollama/models，并在启动时跑 GC
OLLAMA_HOST=127.0.0.1:11435 ./Ollama.app/Contents/Resources/ollama serve
```

旧版只认老式 manifest 布局（`manifests/registry.ollama.ai/...`）。
而 Ollama 0.40+ 改用新布局：`manifests-v2/ollama.com/library/<model>/<tag>`，**manifest 本身是指向 blobs 的符号链接**。
旧版看不见新布局 → 把新版模型的 blob 全判成"未使用"→ 启动时直接删：

```text
total blobs: 1217
total unused blobs removed: 1212     # 一次启动清掉 18GB 权重
```

**如何取证（判断是不是这个原因）**

```bash
# 1. 看服务日志有没有 bad manifest
grep "bad manifest" ~/.ollama/logs/server.log | tail -3

# 2. 找旧版二进制留下的启动记录：PROBE 日志里会有 total unused blobs removed
grep -r "unused blobs removed" /tmp/ollama*/  2>/dev/null

# 3. 对照 blobs 目录的 mtime 与"嫌疑命令"的执行时间，通常精确到秒
stat -f "%Sm %N" -t "%F %T" ~/.ollama/models/blobs
```

**正确姿势（跨版本测试必须隔离）**

```bash
export OLLAMA_MODELS=/tmp/ollama-probe-$$/models   # 独立空目录，绝不共用
export OLLAMA_NOPRUNE=1                            # 关掉启动 GC
OLLAMA_HOST=127.0.0.1:11435 /path/to/old/ollama serve
```

只想看版本号就别起 `serve` —— 直接 `/path/to/old/ollama --version`，不会碰模型库。

**恢复**
重新 `ollama pull <model>:<tag>`。注意 Ollama 0.40 的 manifest 是软链，删了 blob 后
`ollama list` 不报错、只是模型静默消失，别以为"权重还在"。

---

## 12. 第三方客户端报 `context window ... below 64,000`（Hermes 实证）

**现象**：Hermes 一切到 `qwen3.8:27b-mlx` 就失败，界面只给一句"出了点问题，技术细节见网关日志"：

```
── Hermes error details ──
layer: provider   code: unknown   retryable: true   model: qwen3.8:27b-mlx
```

`retryable: true` 是障眼法——**重试永远好不了**。真身在 `~/.hermes/logs/errors.log`：

```
ValueError: Model qwen3.8:27b-mlx has a context window of 32,768 tokens,
which is below the minimum 64,000 required by Hermes Agent.
```

### 根因：三层叠加，缺一不可

| 层 | 实际情况 | 证据 |
|---|---|---|
| Hermes 硬门槛 | 要求上下文 **≥ 64K**，没有环境变量可绕过 | `agent/model_metadata.py:274` → `MINIMUM_CONTEXT_LENGTH = 64_000` |
| Hermes 配置把它钉死 | `model.context_length: 32768` 决定压缩器窗口 → 触发地板检查 | `agent/agent_init.py:2054` → `_enforce_minimum_context()` **在建 agent 时就抛错**，根本没到推理 |
| Ollama 只服务 32K | 服务端窗口由 GUI 设置决定，不是客户端能改的 | `curl localhost:11434/api/ps` → `context_length: 32768` |

> 注意报错文案的误导：它建议"set `model.ollama_num_ctx`"（至少 64K），但**真正触发地板检查的是 `model.context_length`**。两个键都要改，见下面的命令。

### 关键实证：`/v1` 端点不认请求级 `num_ctx`

Hermes 会往 `/v1/chat/completions` 里塞 `options.num_ctx`，**这个字段在 Ollama 的 OpenAI 兼容端点被直接忽略**。对照实验（2026-11-02，同一台机）：

```bash
# 请求里明确写 num_ctx=65536，看实际加载成多少
curl -s --noproxy '*' http://127.0.0.1:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3:4b","messages":[{"role":"user","content":"hi"}],
       "max_tokens":4,"stream":false,"options":{"num_ctx":65536}}'

curl -s --noproxy '*' http://127.0.0.1:11434/api/ps
# → qwen3:4b  context_length: 32768   ← 65536 被无视
```

⇒ **只改客户端配置，报错会消失但服务端还是 32K**，接着撞上截断/空洞回复。真正生效的开关只有 GUI 的 `settings.context_length`（见 §1 与 `CURRENT_CONFIG.md`「上下文由谁决定」）。

### 解决

```bash
# 1) 服务端（唯一真开关）——必须先完全退出 Ollama.app
pkill -f "/Applications/Ollama.app"
#    注意：本机 osascript -e 'quit app "Ollama"' 会报 -10004 权限违例（TCC），用 pkill
sqlite3 "$HOME/Library/Application Support/Ollama/db.sqlite" \
  "update settings set context_length=262144 where id=1;"
open -a Ollama && sleep 10
curl -s --noproxy '*' http://127.0.0.1:11434/api/ps | grep -o '"context_length":[0-9]*'
# → "context_length":262144

# 2) 客户端（Hermes）两个键一起改（取模型上限 262144：64K 在真实 agent 长会话下仍会
#    溢出，开到最大才留得出余量。注意这只是容量，不保护你免遭超窗 prompt）
hermes config set model.context_length 262144
hermes config set model.ollama_num_ctx 262144
```

**验收**（两条都要过）：

```bash
hermes -m qwen3.8:27b-mlx -z "只回复两个字：正常"     # → 正常
grep context_pin ~/.hermes/logs/agent.log | tail -1
# → context_pin: model.context_length pins qwen3.8:27b-mlx at 262,144 tokens ...
#    （出现这行说明配置已生效；同时 errors.log 不再有新 ValueError）
```

### 三个踩过的坑

1. **Ollama.app 运行中改 db 会被内存值写回**。app 启动时会把库里的 `context_length` 拉到它自己的内存值，所以必须**先退出 app → 改库 → 再启动**，否则改动被旧内存值覆盖。本机最终定值取模型上限 262144（即"开到最大"）。
2. **`com.ollama.serve.plist` 里的 `OLLAMA_CONTEXT_LENGTH` 是死配置**，该 launchd 服务从未被加载（`launchctl print` 报 `Could not find service`），改它不产生任何效果，只作记录。别以为改了 plist 就好了。
3. **窗口能设多大 ≠ 能跑，且 64K 本身不够用**。MLX runner 并不按 `num_ctx` 截断：实测 `context_length: 65536` 下仍出现过 **120071 token** 的 prompt 被全量 prefill，真实 agent 长会话（工具输出 + 多轮历史）也常突破 64K 被静默截断、工具调用崩溃——所以必须**开到模型上限 262144** 才留得出余量。但窗口大 ≠ 能塞：**单轮输入仍要压在 1 万 token 内**（见 §9），否则一次 prefill 几十秒起步。

### 为什么 64K 在 48 GB 上装得下

这代 27B 是**混合线性注意力**架构：64 层里只有 16 层是全注意力（`full_attention_interval=4`，4 KV heads × head_dim 256），其余 48 层是线性注意力、状态与序列长度无关。所以 bf16 KV 只有约 **64 KiB/token**——比同样参数量的纯注意力模型小一个量级。

| 上下文 | KV 估算（bf16，仅全注意力部分） | 实测 `/api/ps` |
|---|---|---|
| 空闲（仅权重） | 0 | 16.9 GiB |
| 65536（跑完一轮会话） | ~4 GiB | 30.0 GiB |
| 262144（满窗理论上限） | ~16 GiB | 当前实跑 27.4 GiB vram，正常（未 evict） |

> ⚠️ **修正早前误判**："262144 在 48 GB 必然 evict" 是对一次争用场景日志的误读。MLX 的 KV **按实际用量动态分配**（不是启动预占满窗 16 GiB），单模型正常开到 262144 能跑；只有真塞到接近满窗才会 spill swap。当前本机即以此值稳定运行。

而且 MLX 的 KV 是**按实际用量动态分配**的（不是启动时一次性预占），所以抬窗口本身几乎不花钱，真正的成本是"你真的塞了多长的 prompt"。

### 连带现象：多会话抢单槽位 → 看起来"provider 一直无响应"

`OLLAMA_NUM_PARALLEL=1`：同一个模型同时只服务**一个**请求，其余排队。当多个 agent 回合各自带着 6–16 万 token 的历史同时重试时，每个都在等别人，逐个撞上 Hermes 的 900 s stale 阈值被杀、再从头 prefill → 表现就是"所有窗口全都没响应，但 Ollama 本身没有任何 ERROR"。

```bash
# 看有几个并发在抢
lsof -nP -i TCP:11434 | grep ESTABLISHED | awk '{print $1,$2}' | sort | uniq -c
# 看每个请求要读多少 token（total= 就是单轮 prompt 大小）
grep "Prompt processing progress" ~/.ollama/logs/server.log | tail -5
```

**处置**（先挡新活，再清僵死回合）：

```bash
hermes pause                      # 只挡新回合，在跑的继续
hermes gateway stop --yes         # 会列出占位会话（含跑了几小时的那种）
# 网关会被 supervisor 自动拉起；没起来就 hermes gateway start
hermes resume
```

---

## 13. 【2026-11-02 实证】"一直 loading / 又卡又慢"的真实根因链（别再只怪窗口）

> 这一节是 11-02 一整天的排障结论。前几个月"正常用"、这两天"一直 loading"的落差，**不是窗口开太大、也不是 KV swap 单一原因**，而是一条叠加链。按顺序排，每一环都有日志实锤。

### 根因链（从表层到真凶）

1. **窗口开到 262144 是用户的硬需求**（Hermes `MINIMUM_CONTEXT_LENGTH=64000` 硬门槛 + 64K/128K 在真实长会话仍溢出截断）。这一步本身没错，但它把"单轮 prompt 能有多大"的上限拉高了。
2. **Ollama 优化项从没生效过**：`OLLAMA_KV_CACHE_TYPE` / `OLLAMA_FLASH_ATTENTION` / `OLLAMA_NUM_BATCH` / `OLLAMA_KEEP_ALIVE` 一直写在 shell 的 `.zshrc` 里，而 **Ollama.app 是独立 GUI 进程，不读 shell 环境** → 这些变量全等于没设。（⚠️ 11-04 归因修正：q8_0/FA 即便设了对 MLX 也是 no-op；f16 KV 实测 ≈53 KiB/token、262144 满窗 ~16GB，并不必然 swap 死——当时的 swap 死主要由 MTPLX 同驻 + 78K prompt 造成，见 §14。）
3. **Hermes 的历史从未被压缩过（真凶）**：Hermes 内置 `ContextCompressor`（`agent/context_compressor.py`），比例制对窗口算预算（`threshold=0.3 → 78K 触发`，`target_ratio=0.2 → 目标 ~15K`）。但它依赖一个**摘要模型**总结旧历史；本地-only 部署下该摘要模型在 **120s preflight 超时**（`⚠ Context compression timed out after 120.0s with no output from the summary model. No messages were dropped — continuing without compression`），**压缩失败 → 每轮都把完整 100K+ 历史原样发给模型** → prefill 几分钟 → 看起来"一直 loading"。
   - 为什么本地修不了：摘要模型本身要处理 100K+ token，在本地 27B 上跑必然超过 120s，指向本地模型只会更慢（两个本地调用抢单 GPU）。**LLM 历史压缩在纯本地部署下结构性失效。**
4. **stale 断路器把"慢"变成"报错"**：默认 `HERMES_STREAM_STALE_GIVEUP=5` 会在连续 5 次 stale 后主动 abort 整次调用（报错 "5 consecutive stale attempts — aborting this call"），于是早期表现是"报错退出"而非"卡住"。

### 解法（已逐一验证）

| 环节 | 解法 | 验证 |
|------|------|------|
| 优化项不生效（环 2） | 走 `launchctl setenv`（用户会话域）或 LaunchAgent plist `~/Library/LaunchAgents/com.user.ollama-env.plist`，再**重启 Ollama** | server 日志实锤 `OLLAMA_KV_CACHE_TYPE:q8_0` / `FLASH_ATTENTION:true`；KEEP_ALIVE 最终定 **`30m`**（老板 11-03 裁定，与公众号文章一致；此前救机时设的 `-1` 已作废） |
| swap 至死（环 2→3 连接点） | 🔴 11-04 归因修正：真修复是**停 MTPLX 第二引擎 + 砍单轮 prompt**；q8_0 对 MLX 经三组 A/B 实测 no-op（KV 增量 2.87 vs 2.85GB），「KV 砍半到 ~25GB」为错误估算 | 109K 请求稳定跑完属实，但功劳不在 q8_0 |
| prefill 慢（环 3） | `OLLAMA_NUM_BATCH=2048` + `KEEP_ALIVE=30m`（驻留 30 分钟免重载） | 大 prompt prefill 提速、不再每次重载 |
| 历史不压缩（环 3 真凶） | **三选一**：① 云端快速摘要模型（配 `auxiliary.compression` 指向已配 key 的 DeepSeek/agnes，历史被压到 ~15K，代价：历史出机器）；② 本地保持短会话（`micro_compact` 已开 + 手动 `/new` 或 `/compress`）；③ 接受 q8_0 让慢请求能跑完 | 见 `CURRENT_CONFIG.md`「Hermes 历史压缩」节 |
| 慢被当错杀（环 4） | `HERMES_STREAM_STALE_GIVEUP=0`（写入 `~/.hermes/.env`，重启 Hermes 生效）：关闭主动 abort，慢就慢、报错就报错，反馈权交给模型侧 | 重启后 `errors.log` 零次 stale-abort |

### 补充实证（22:07 复核）：并发会话重试风暴才是「一直 loading」的表象

单个请求其实**跑得动**（与 q8_0 无关，11-04 A/B 定案）——22:05–22:07 日志显示 55,614 token 请求以 ~227 tok/s 稳定 prefill、无 swap。但用户仍感觉「一直 loading」，因为：

```
agent.log 21:39–21:59：6+ 个不同 session 同时
  "Stream stale for 900s (threshold 900s) — no chunks received. Killing connection."
  context=45,260 / 47,521 / 49,926 / 55,480 / 57,981 / 66,098 / 84,731
  → APIConnectionError → attempt 1/5、2/5 … 自动重发同一个大请求
lsof -iTCP:11434：16 条 ESTABLISHED 连接
hermes status：Jobs 4 active / 4 total；sessions list 里 7+ 个会话标 "just now"
```

**机制**：Ollama `NUM_PARALLEL=1` 只有一个槽。多个老会话各自带着 45K–85K 历史并发请求 → 全在排队 → 排队超过 900s 触发 `local_stream_stale_timeout` 杀连接 → 客户端重试 5 次 → 又发一遍大请求 → **无限重发循环**，槽永远不空，新会话也排不进去。

⚠️ 这不是配置 bug，是**并发任务数 × 单会话历史体量**超过了单并发槽的吞吐。前几个月能用，是因为那时每个会话历史只有几 K～几万，多个会话排队也很快轮完。

**处置**（会中断在跑的任务，需用户自己确认，不要由 agent 擅自执行）：
```bash
hermes sessions list                 # 先看哪些是老会话/占位会话
hermes pause                         # 挡新回合，在跑的继续
hermes gateway stop --yes            # 列出并停掉占位会话；supervisor 会自动拉起
hermes resume                        # 确认干净后恢复
```
只保留 1 个活跃会话时，单请求 55K prefill ~4 分钟就能跑完；并发越多越接近"永远转圈"。

### 补充实证：压缩器「两层失效」的精确机制

比 §13 根因链第 3 环更细的两道关（都有日志/源码实锤）：

1. **preflight 被 defer**：`agent/turn_context_compaction.py:286-292` 记 `Skipping preflight compression: rough estimate ~158,874 >= 98,304 is not anchored on real usage (last real provider prompt 0); deferring to the next response`。根因是 Ollama `/v1` **不返回 usage**（silent-clip，用户早在 `config.yaml` 注释里记过），压缩器拿不到真实 prompt token 数 → 粗估「未锚定」→ 先发一轮再压。源码 `agent/context_compressor.py:2983-3000` 的 `should_defer_preflight_to_real_usage()` 在 `_provider_omits_usage=False` 时返回 True（defer）；一旦 provider 被判定为「不返 usage」就不再 defer。
2. **摘要模型 stall → 确定性兜底**：`auxiliary.compression` 是 `provider: auto / model: ''`（`config.yaml:151-154`），回落到**本地 27B**。要它读 100K+ 历史必然超过 `compression.context_timeout_seconds` 默认 120s（`hermes_cli/config_defaults.py:665`；`agent/conversation_compression_deadline.py:20`）→ stall。日志实锤它**会自动降级**：
   ```
   11:16:39 / 14:47:08  Context compression stalled on every summary route
     — committing the deterministic fallback summary (no summary model)
     Context compression committed a deterministic fallback summary …
   ```
   即 `DETERMINISTIC_SUMMARY_ROUTE`（`agent/context_compressor.py:97-101`）：**跳过 LLM，插入静态摘要并 drop 中间消息**——纯本地、不出机器，但会丢中间轮次细节，且要 stall ladder 先烧掉一个窗口才触发。

⇒ **纯本地不可能有「保留语义的 LLM 摘要压缩」**：摘要模型本身要读 100K+，和主请求抢同一块单并发 GPU，只会更慢。想让 LLM 摘要真正跑通，只能把 `auxiliary.compression` 指向云端快速模型（本机已配 `DEEPSEEK_API_KEY` / `HERMES_CUSTOM_AGNES_API_KEY`），代价是**会话历史出机器**。这是隐私取舍，必须由用户拍板，agent 不得擅自改。

> ⚠️ 别把 `context_timeout_seconds` 从 120s 调高来「让本地摘要跑完」：那会让每轮多一次 100K prefill（~7 分钟）且占住单并发槽，比不压缩更慢。

### 一句话避坑

- **Ollama 变量别写 shell，写 `launchctl` / LaunchAgent**，否则等于没设。
- **本地 27B + 262144 不需要 `q8_0`**（11-04 三组 A/B 定案：对 MLX no-op；f16 KV 实测 ≈53 KiB/token、满窗 ~16GB 动态分配）；GGUF/llama.cpp 路线才需要。
- **纯本地部署下 Hermes 的 LLM 历史压缩会超时失效**，要么用云端摘要模型、要么自己保持短会话——这是"又卡又慢"的最后一块拼图，别只盯着窗口和 KV。
- 改配置后**重启对应进程才生效**（Ollama 重启加载 launchctl 变量；Hermes 重启加载 `.env`）；别杀 server 触发 Hermes 重发超大请求。

清完 ollama 连接数应归零：`lsof -nP -i TCP:11434 | grep -c ESTABLISHED` → `0`。


---

## §14. 2026-11-04：Hermes 全瘫（/v1 超时 + /compress revision_conflict）——失控 turn 是真凶

### 症状
- Hermes 本地 ollama「调不动 / 一直加载」；`/compress` 报 `error: revision_conflict`；切换模型等会话操作全部失败。

### 真因链（实测确认）
1. gateway 内 **3 个 turn 僵尸化**（最长 4.6 小时无限重试），实际上下文滚到 10 万+ token → KV 实际占用涨到 28–34GB → 48GB 机器 swap 18GB+；
2. `/v1` 40–180 秒超时 → 压缩拿不到 summary 模型 → 失败 + 冷却（`compression_failure_cooldown`）；
3. 会话 revision 被失败重试反复推动 → 客户端 `expected_revision` 永远过期 → 任何 session.mutate（含 /compress、切换模型）报 `revision_conflict`；
4. 恶性循环：卸载模型后 gateway 重试立刻重拉，系统永远缓不过来。

### 诊断要点
- `hermes gateway restart`（不带 `--yes`）会**列出所有活跃 turn 及运行时长**——僵尸 turn 一眼可见；
- 优雅排水会等失控 turn 最多 **1800s**；直接 `kill -9 <gateway pid>` 让 supervisor 秒拉新实例最快；
- `sysctl vm.swapusage` 看 swap；`tail ~/.ollama/logs/server.log` 看请求排队（单并发，`Prompt processing progress` 就是正在跑）。

### 修复步骤（已验证）
1. `hermes gateway restart --yes`（或强杀 gateway 进程）清失控 turn，会话 revision 全部刷新；
2. 卸载模型释放内存：`curl -X POST localhost:11434/api/generate -d '{"model":"...","keep_alive":0}'`；
3. 重启后旧会话标 `paused: unknown_execution`（正常保护）：对该会话发任意一条消息即恢复。

### 重启后须知（11-04 补充）
- 电脑重启后：Ollama.app 自启 server（context 从 GUI db 读）、Hermes Desktop 自启 gateway——基础设施无需手动干预；
- 大请求（如 /compress 摘要 69K 历史）耗时 **5–6 分钟**，期间**单并发队列堵住其他一切操作**（含切模型），看起来「没反应」其实在跑；
- 27B 本地速度基线：decode ~10–39 tok/s（MTP 投机解码生效时更高）、prefill 冷实例首次大请求 ~165 tok/s、热态 ~590 tok/s。