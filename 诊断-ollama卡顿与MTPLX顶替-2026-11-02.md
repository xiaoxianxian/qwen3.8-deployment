# Qwen3.8-27B 本地卡死诊断：Ollama 病态与 MTPLX 顶替失败

- 机器：MacBook Pro / Apple M5 Pro / 48 GB 统一内存（51539607552 B）
- 系统：macOS 27.2（26B123）
- 引擎：Ollama 0.40.11（MLX runner）+ MTPLX 8000
- 诊断时间：2026-11-02 02:14–02:40
- 结论级别：四个原因全部有日志/实测支撑，非推测

---

## 一、结论先说

hermes 的判断**方向对、但换错了药**。

它说的「Ollama bug 叠加 macOS bug」确实存在（Ollama issue #18744，MLX 权重 2 秒后被 macOS 解绑），但 **MTPLX 底层同样是 MLX**，换过去不但躲不开这个 bug，还额外背了两个更重的包袱：`--allow-swap` 让进程胀到 74 GB 峰值，262144 上下文让 hermes 以为有 256K 空间可塞。

真正让它「根本没法干活」的，是四个原因同时成立：

| # | 原因 | 证据 |
|---|---|---|
| 1 | **两台 27B 引擎同时驻留**，48 GB 装不下 | MTPLX footprint **40.6 GB（峰值 74.1 GB）**，此时 Ollama 只剩 8.9–11.9 GiB 可用 |
| 2 | **Ollama.app 把上下文设成 262144**，覆盖了 Modelfile 的 131072 | 调度器日志 `predicted="24.8 GiB" predicted_num_ctx=262144 available="11.9 GiB"` → `evicting` |
| 3 | **MLX residency bug**（macOS 27 专属） | ollama#18744：请求结束约 2 秒后权重被解绑，下次请求从 swap 页入 |
| 4 | **hermes 每轮塞 77–80 K token** | MTPLX 日志 `prompt_tokens: 77671` / `80097`，reusable_prefix 仅 16384 |

第 4 条是最贵的一条：**预填充实测 362 tok/s，78 K token 光读 prompt 就要 217 秒**。这跟引擎选谁无关，是算术。

---

## 二、现场证据

### 2.1 停用前的内存现场

```
MTPLX (pid 45438) Footprint: 40 GB，Physical footprint (peak): 74.1G
swap: total 13312 MB / used 12253 MB
vm_stat: Pages wired down 2334201（38.2 GB）
ollama /api/ps: {"models":[]}      ← 模型压根没加载
ollama 进程 footprint: 14 MB       ← 不是 Ollama 在吃内存
```

MTPLX 日志里最后 200 行：`pressure_trim` 96 次、`prefill_admission_shed` 47 次，
每条都带 `"system_thrashing": true`，可用内存常年在 1.3–3.0 GB。
它不是在推理，是在跟操作系统抢页。

### 2.2 Ollama 被谁挡住（server-2.log / server-3.log）

```
msg="llama-server model predicted to exceed available memory, evicting"
predicted="24.8 GiB" predicted_num_ctx=262144 num_batch=512
available="11.9 GiB" gpu_free="20.5 GiB" system_limited=true
```

`predicted_num_ctx=262144` 而 Modelfile 写的是 `num_ctx 131072` —— 说明环境变量优先。
继续追，值来自 **Ollama.app 自己的 SQLite**：

```
~/Library/Application Support/Ollama/db.sqlite
  table settings → context_length = 262144
```

同一次启动的 env：`OLLAMA_CONTEXT_LENGTH:262144`、`OLLAMA_FLASH_ATTENTION:false`、
`OLLAMA_KV_CACHE_TYPE:`（空）、`OLLAMA_KEEP_ALIVE:5m0s`。

而 `~/Library/LaunchAgents/com.ollama.serve.plist` 里那套精心调过的配置
（FA=1、KV=q8_0、KEEP_ALIVE=30m）**从未生效**——它的 `RunAtLoad=false`、`KeepAlive=false`，
实际提供服务的是 GUI 拉起的那个 server。也就是说：**调的是一套，跑的是另一套**。

即使上下文只有 5 万 token，KV 也会把 footprint 从 22 GB 撑到 31.38 GB（server-5.log 连续增长记录），
256 K 的声明值在这台机器上从来就没成立过。

### 2.3 「macOS bug」的真实身份

Ollama issue **#18744**（开着，10 月 1 日仍在 main 上复现）：

> On the MLX engine, a loaded model's weights stay wired only while a request is running.
> About two seconds after each request macOS releases them, and they become ordinary pageable memory.
> On a machine under any memory pressure they are then compressed or swapped, and the next request
> waits for them to come back. This happens with `OLLAMA_KEEP_ALIVE=-1` and with `load_duration`
> near zero, so the model looks loaded the whole time.

根因在 MLX 的 `requestResidency()` 只发一次、从不续租（ml-explore/mlx#4609），
macOS 27 会在最后一次 GPU 工作约 2 秒后回收空闲 residency。
**llama.cpp（GGUF 引擎）有心跳机制所以不受影响**——这点决定了兜底方案。

官方 workaround：`sudo sysctl iogpu.disable_wired_collector=1`。
本机查下来**已经是 1**（此前已有人设过，重启会失效）。

### 2.4 MTPLX 为什么更慢（同一份日志给出的数）

```
prompt_tokens: 77671, completion_tokens: 206, elapsed_s: 127.398, tok_s: 6.947, end_to_end_tok_s: 1.617
```

端到端 **1.6 tok/s**。它没坏，是 256K 上下文 + `--allow-swap` + 78 K prompt 三者叠加，
每次请求都在 admission shed 里反复重试预填充。

另外，MTPLX 声明 `context_length: 262144`，hermes 读到这个数就按 256K 预算组织上下文，
于是每轮把 7.8 万 token 重新送进来 —— **声明了多大的窗口，agent 就会填多大**，
这是一个会自我强化的循环。

---

## 三、已执行的修复

| 动作 | 结果 |
|---|---|
| 停掉 MTPLX（`launchctl bootout` + kill），并 `launchctl disable` 防自启 | 释放 35.6 GB，free 从 79 K 页回到 2.34 M 页 |
| Ollama GUI `context_length` 262144 → **32768** | 服务端 env 实测 `OLLAMA_CONTEXT_LENGTH:32768`，`ollama ps` 显示 CONTEXT 32768 |
| hermes 默认 provider：`mtplx@8000` → `ollama@11434`，`ollama.context_length` 131072 → 32768 | YAML 校验通过，`/v1` 实测返回 usage（含 cached_tokens，非 silent-clip） |

备份：`/tmp/db.sqlite.bak-*`、`~/.hermes/config.yaml.bak-*`。

### 修复前后实测

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 可用内存 | 1.3–3.0 GB，thrashing | free 41–47% |
| 模型能否加载 | 反复 evict，`/api/ps` 空 | 100% GPU，20–22 GB |
| 冷启动加载 | 无法完成 | **2.53 s** |
| 解码 | 1.6 tok/s（MTPLX 端到端） | **24–28.8 tok/s** |
| 4.7 K prompt 预填 | — | 12.31 s（383 tok/s） |
| 10.8 K prompt 预填 | — | 29.89 s（362 tok/s） |
| 同一前缀追加 | — | 8.22 s（prefix cache 命中，约 3.6× 提速） |
| 空闲 60 s 后首请求 | — | 0.46 s（`iogpu.disable_wired_collector=1` 在起作用） |

---

## 四、还有三件事没做（按优先级）

1. **重启后 sysctl 会失效**。开机要重新执行：
   `sudo sysctl iogpu.disable_wired_collector=1`
   想固化就得写 LaunchDaemon（需要 root 权限）。

2. **`keep_alive` 仍是 5m**。`launchctl setenv` 被沙箱拦了，GUI 也不给改。
   影响有限（实测重载 2.5 s），但频繁冷启在内存紧张时会放大。
   要彻底解决就让 GUI 别管 server、改用 `com.ollama.serve.plist`（FA=1 / KV=q8_0 / 30m 都已配好）。

3. **需要长上下文时临时放大，不要常驻**。32K 是这台机器的日常档；
   一次性长文档任务可以给单请求 `options.num_ctx`，任务完就回落。
   常驻 64K 以上就会回到 swap 老路。

---

## 五、如果还想用 MTPLX

三条必须同时满足，缺一条就是这次的重演：

1. Ollama 必须先停（两个引擎绝不共跑）；
2. 去掉 `--allow-swap`（它就是 74 GB 峰值的直接来源）；
3. 上下文声明降到 32768，不要给 agent 262144 的错觉。

坦白讲：**MTPLX 在同 workload 下本来就比 Ollama 慢约 14%**（2026-10-03 对拍：23.04 vs 26.61 tok/s，
`MTPLX-vs-Ollama-实测报告.md`），而且它同样是 MLX 引擎、同样吃 #18744 的亏。
它唯一的价值是「Ollama 挂了的备胎」，不是升级。

---

## 六、复现与回滚

回滚 Ollama 上下文：

```bash
sqlite3 ~/Library/Application\ Support/Ollama/db.sqlite \
  "update settings set context_length=131072 where id=1"
# 然后重启 Ollama.app
```

回滚 hermes 指向：恢复 `~/.hermes/config.yaml.bak-*`。

重新启用 MTPLX（不推荐，见第五节）：

```bash
launchctl enable gui/$(id -u)/com.jason.mtplx
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jason.mtplx.plist
```

---

## 七、一句话给 hermes

判断「Ollama+macOS 有 bug」是对的（#18744），但**换引擎解决不了 residency 问题，因为 MTPLX 也是 MLX**；
而真正把机器按死的是「262144 上下文 + 两个引擎共跑 + 78 K prompt」。
修完这三处，同一个模型回到 24–28 tok/s，冷启 2.5 秒。

---

## 八、MTPLX 已彻底移除（2026-11-02 02:45）

按老板决定：不要 MTPLX 这套，回到 Ollama + qwen3.8:27b-mlx 单引擎。

| 动作 | 结果 |
|---|---|
| `launchctl bootout` + `disable` | 8000 端口不再监听 |
| plist 移出 `~/Library/LaunchAgents/` → `~/models/disabled-launchagents/` | 登录不再自启 |
| hermes `providers.mtplx` 整块删除 | `providers` 只剩 `ollama` / `agnes`，`grep mtplx` = 0 |
| hermes `file_read_max_chars` 100000 → **30000** | 原值≈2.5 万 token，单次读文件就吃掉 32K 窗口的 76% |
| hermes `tool_output.max_bytes` 50000 → **20000** | 原值≈1.2 万 token，一次工具输出就要 33 秒预填充 |

`~/.mtplx/` 的 **52 GB 权重仍在磁盘上未删除**，确认不再需要后可回收。

### 8.1 预填充是算力墙，不是配置问题

清理内存后重测：2213 tok → 383 tok/s；6637 tok → 348 tok/s；稳定在 **348–383 tok/s**。

算术核对：稠密 27B 每 token 约 2×27 GFLOPs，×360 tok/s ≈ **19 TFLOPS**，
这已经压在 M5 Pro GPU 的算力上限上。**换引擎、改参数都提不上去。**

推论（这才是"能不能干活"的判据）：

| prompt 规模 | 预填充耗时 | 可用性 |
|---|---|---|
| 2 K | 5.8 s | 顺畅 |
| 4 K + 8 个工具定义 | 14.4 s（实测 TTFT） | 可接受 |
| 10 K | 29 s | 勉强 |
| 32 K（吃满窗口） | 88 s | 不可用 |
| 78 K（hermes 旧常态） | 217 s | 物理上不可能 |

所以本地 27B 的**真实可用上下文不是 32768，而是约 10 K** ——
窗口由预填充吞吐决定，不由 num_ctx 决定。

### 8.2 实测：模拟 hermes 一轮 agent 调用

system prompt + 8 个函数定义 + 3 轮历史，流式：

```
首 token(TTFT)=14.40s  总耗时=16.81s  finish_reason=tool_calls
```

工具调用单独验证（`get_weather`）：`finish_reason: tool_calls`，
参数 `{"city":"北京"}` 正确，5.50 s。

### 8.3 冷重载开销（keep_alive 5m 的实际代价）

`ollama stop` 后重新请求：加载 **3.02 s**，墙钟 3.43 s。
结论：5 分钟卸载**不值得专门去改**，代价可忽略。

### 8.4 重启后需要重设 sysctl

`iogpu.disable_wired_collector` 重启归零。已备好 LaunchDaemon：
`~/models/com.user.iogpu-wired.plist`，一次性安装：

```bash
sudo cp ~/models/com.user.iogpu-wired.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.user.iogpu-wired.plist
sudo chmod 644 /Library/LaunchDaemons/com.user.iogpu-wired.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.user.iogpu-wired.plist
```

