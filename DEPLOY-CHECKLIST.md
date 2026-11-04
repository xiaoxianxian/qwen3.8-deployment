# Qwen3.8-27B 本地部署 · 一页纸清单（照做即可）

> 适用：Apple Silicon / macOS / Ollama + Hermes。
> 本清单是「按顺序执行 + 每步验证」，不是原理讲解。原理和事故复盘见 `TROUBLESHOOTING.md` / `CHANGELOG.md`。
> 最后校准：**2026-11-05**（Ollama 0.40.14 / qwen3.8:27b-mlx / M5 Pro 48GB）。
>
> 🚀 **一页搞定**：第 3 步的 plist 内容已完整内联在下方，**整段复制粘贴即可**，不依赖任何脚本文件。
> 如果你拿到的是作者本机的完整目录，还有两个本地脚本可省手：`scripts/bootstrap-ollama-launchd.sh`（第 3 步自动化，幂等，支持 `--dry-run`）和 `scripts/health-check.sh`（只读体检 7 项）。
> 注意：`scripts/`、`CHANGELOG.md`、`MEMORY.md` **按本仓约定不入 Git**，克隆仓库看不到它们——所以下面每一步都保证"没有脚本也能照做"。

---

## 0. 三个必须先确认的数字

```bash
sysctl hw.memsize | awk '{printf "内存 %.0f GB\n", $2/1073741824}'   # 期望 ≥48
df -h ~ | tail -1                                                     # 期望可用 ≥60GB
curl -s localhost:11434/api/version || echo "Ollama 未运行"
```

| 项 | 本机取值 | 为什么 |
|---|---|---|
| 上下文窗口 | **262144** | 模型上限；Hermes 有 `MINIMUM_CONTEXT_LENGTH=64000` 硬下限，低于即建 agent 报 `ValueError` |
| 单轮 prompt | **尽量 ≤1 万 token** | prefill **实测约 224 tok/s**（理论 348–383），10K ≈ 45s、32K ≈ 145s。窗口大 ≠ 该塞长 prompt |
| 同时会话数 | **≤3~4** | MLX runner 单槽位（源码级限制，无法通过参数开并行），请求是严格串行的 |
| 客户端单请求超时 | **14400s（8 并发）/ 7200s（≤4 并发）** | 多会话排队时单轮实测 24–30 分钟，`NUM_PARALLEL=1` 下严格串行 → 最后一个要等「并发数 × 30min」。**Hermes 默认 1800s 会把它切断**（见 Step 4） |
| 常驻内存 | **约 35 GB** | 262144 满窗 `/api/ps` 的 `size_vram` 实测 35.1 GB；按 35 GB 规划 |

---

## 1. 安装与拉模型

```bash
# 安装（二选一）
brew install --cask ollama-app
# 或 https://ollama.com/download

# 拉模型（MLX 原生版，nvfp4，约 18GB）
ollama pull qwen3.8:27b-mlx

# 国内加速：HF_ENDPOINT=https://hf-mirror.com ollama pull qwen3.8:27b-mlx
ollama list          # 期望看到 qwen3.8:27b-mlx
```

---

## 2. 设上下文（必须先完全退出 App）

上下文由 **GUI 设置库**决定，优先级高于 Modelfile。改之前必须 `killall Ollama`，否则 GUI 会写回旧值。

```bash
killall Ollama 2>/dev/null; sleep 2
sqlite3 "$HOME/Library/Application Support/Ollama/db.sqlite" \
  "UPDATE settings SET context_length=262144;"
sqlite3 "$HOME/Library/Application Support/Ollama/db.sqlite" \
  "SELECT context_length FROM settings;"      # 期望 262144
```

---

## 3. 让 launchd 接管 serve（★ 本清单最重要的一步）

**为什么必须做**：`launchctl setenv` 写的是会话环境，**Ollama.app 自更新后的重启不继承它**——每次升级都会把配置悄悄打回默认值。2026-11-04 就是这样丢了 `KEEP_ALIVE=30m`（回落 5m），模型空闲 5 分钟就卸载，多会话每次都要重算全量 prefill，表现为「一直加载、像卡死」。

配置写进 plist 后放在 **App bundle 之外**，升级碰不到它。

```bash
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.ollama.serve.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ollama.serve</string>
  <key>ProgramArguments</key>
  <array><string>/usr/local/bin/ollama</string><string>serve</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key><string>127.0.0.1:11434</string>
    <key>OLLAMA_MODELS</key><string>__HOME__/.ollama/models</string>
    <key>OLLAMA_CONTEXT_LENGTH</key><string>262144</string>
    <key>OLLAMA_KEEP_ALIVE</key><string>30m</string>
    <key>OLLAMA_MAX_LOADED_MODELS</key><string>1</string>
    <key>OLLAMA_NUM_PARALLEL</key><string>1</string>
    <key>OLLAMA_LOAD_TIMEOUT</key><string>5m</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/tmp/ollama_launchd.log</string>
  <key>StandardErrorPath</key><string>/tmp/ollama_launchd.log</string>
</dict>
</plist>
PLIST

sed -i '' "s|__HOME__|$HOME|g" ~/Library/LaunchAgents/com.ollama.serve.plist
plutil -lint ~/Library/LaunchAgents/com.ollama.serve.plist     # 必须 OK

# 顺序很重要：先清干净，再 bootstrap，最后才开 App
killall Ollama 2>/dev/null; pkill -9 -f 'ollama serve' 2>/dev/null; sleep 3
launchctl bootout  gui/$(id -u)/com.ollama.serve 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ollama.serve.plist
sleep 8
open -a Ollama     # App 发现 11434 已占用就不再起自己的 serve，仅作 GUI
```

> 只配这些就够。`OLLAMA_KV_CACHE_TYPE` / `OLLAMA_FLASH_ATTENTION` 对 MLX runner 经三组 A/B 证实是 **no-op**（GGUF 路线才有效）；`OLLAMA_NUM_BATCH` 在 0.40.x **根本不存在**。
> `OLLAMA_NUM_PARALLEL=1` 是**服务端兜底**：把"逐个执行"写死在服务端，避免 Ollama 在内存宽裕时自动调高并行、被多会话并发打爆（详见 `TROUBLESHOOTING.md` §16）。它不改变 MLX 单槽位行为，只是把"严格串行"显式钉死。

### 三条验收（缺一不可）

```bash
# ① 服务在
curl -s localhost:11434/api/version

# ② 服务端默认 keep_alive = 30m（注意：请求里不要带 keep_alive 参数）
curl -s localhost:11434/api/generate -d '{"model":"qwen3.8:27b-mlx","prompt":"1","stream":false,"options":{"num_predict":2}}' >/dev/null
curl -s localhost:11434/api/ps | python3 -c "
import json,sys,datetime
now=datetime.datetime.now(datetime.timezone.utc)
for m in json.load(sys.stdin)['models']:
    t=datetime.datetime.fromisoformat(m['expires_at'].replace('Z','+00:00'))
    print(m['name'], m.get('context_length'), '→', round((t-now).total_seconds()/60), '分钟后卸载')
"
# 期望：262144 → 约 30 分钟后卸载。若显示 5 分钟，说明配置没生效

# ③ 打开 App 后不再撞端口（计数必须停止增长）
grep -c 'address already in use' /tmp/ollama_launchd.log; sleep 20; \
grep -c 'address already in use' /tmp/ollama_launchd.log
```

---

## 4. Hermes 侧（客户端）配置

```yaml
# ~/.hermes/config.yaml
model:
  context_length: 262144      # 与服务端一致
  ollama_num_ctx: 262144      # 请求级上限，也要一致
ollama:
  context_length: 262144

tool_output:                  # 从源头控制会话膨胀
  max_bytes: 20000
  max_lines: 2000
file_read_max_chars: 30000

agent:
  local_stream_stale_timeout: 14400   # ★ 4h。必须 ≥ request_timeout_seconds，否则它先 kill。"流中点多久没新数据算卡死"。
                                      # 键名就是 agent.local_stream_stale_timeout，
                                      # 写 local_stream_stale_timeout_blocking 是无效的（源码无此键）

compression:
  enabled: true
  threshold: 0.85             # 262144×0.85≈22 万 token 才压一次
  target_ratio: 0.2
  protect_first_n: 3
  protect_last_n: 25
  micro_compact: false        # ★ 必须关，理由见下
```

**为什么 `micro_compact` 必须关**：它每 N 轮把最老的对话折成滚动摘要 = **改写已发送历史 → 前缀缓存每轮作废**。Hermes 官方 `micro-compaction.md` 原话："breaks the provider prompt-cache prefix every turn; for some setups that cost exceeds the benefit"。本地 27B prefill 实测只有 ~224 tok/s，正是这种 setup。

| 配置 | 缓存命中率 | 单轮耗时 |
|---|---|---|
| `micro_compact_every_n_turns: 1` | 13%~29% | 60~200 秒 |
| **`micro_compact: false` + threshold 0.85** | **97%~100%** | **2.5~9 秒** |

关掉后上下文**不会丢**（不再折叠历史，现有会话可继续），代价只是会话会一直增长到 85% 阈值才批量压缩一次。

> 📌 **阈值怎么选（0.85 vs 0.3）**：`0.85` = 更少压压缩次数、对前缀缓存最友好（会话内命中 97~100%）；`0.3` = 更早压缩、历史更短、单轮更快，但会多压几次。两者都能用，**关键是 `micro_compact: false`**（本机 11-05 实际跑的是 0.3，是长期原值，不要因为看到本文写 0.85 就去改）。

### 4.1 客户端超时（★ 2026-11-05 新增，不设就会"早上起来全超时挂掉"）

`HERMES_API_TIMEOUT` 默认 **1800s**，而多会话排队时单轮实测 **24–30 分钟**——正好在 30 分钟处被切断，然后重试 5 次、越重试越堵。

**推荐改法（实时生效，不用重启 gateway）**：

```yaml
# ~/.hermes/config.yaml —— 两个 provider id 都要写，否则有会话漏网
providers:
  custom:
    request_timeout_seconds: 14400
  ollama:
    request_timeout_seconds: 14400
```

> 为什么有 `custom` 和 `ollama` 两个：有 `provider` 字段的老会话报 `ollama`，`local-*` 桌面会话报 `custom`。源码按 `providers.<id>.request_timeout_seconds` 查，查不到就回落默认 1800s。

**备选（全局 env，需重启）**：

```bash
# ~/.hermes/.env（这两项是环境变量，必须在 gateway 启动前写入）
HERMES_API_TIMEOUT=14400         # 4h，覆盖 8 并发 × 30 分钟串行排队的最坏情况
HERMES_STREAM_STALE_GIVEUP=0     # 执行层不主动打断长请求
hermes gateway restart           # env 在进程启动时读入，必须重启
```

### 4.2 会话端点自检（★ 2026-11-05 新增，同日修正）

**每个 Hermes 会话各自记着端点，切换全局 provider 不会改写老会话。** 真指向已卸载引擎的会话会**永远跑不完**，看起来却像"模型慢"。

但**判断端点必须按优先级取字段**，否则会误报：

| 字段 | 含义 | 能否用 |
|---|---|---|
| `model_config.gateway_runtime.base_url` | 网关运行时真实端点 | ✅ 唯一可靠 |
| `model_config.base_url` | 会话保存值，可能被运行时覆盖 | ⚠️ 次选 |
| `sessions.billing_base_url` | 历史记账值，几乎不更新 | ❌ 会骗人 |

```bash
python3 - <<'PY'
import sqlite3,os,json
c=sqlite3.connect(os.path.expanduser("~/.hermes/state.db"))
bad=0; stale=0
for sid,mc,bbu in c.execute("select id,model_config,billing_base_url from sessions where ended_at is null"):
    d={}
    try: d=json.loads(mc) if mc else {}
    except Exception: pass
    gr=d.get("gateway_runtime") or {}
    u=gr.get("base_url") or d.get("base_url") or bbu or ""
    is_local = u.startswith("http://127.0.0.1:11434") or u.startswith("http://localhost:11434")
    is_dead  = (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")) and not is_local
    if is_dead: bad+=1
    if bbu and u and bbu!=u: stale+=1
    print(f"{sid[:24]:26s} 实际={u}{'  ← 本机死链' if is_dead else ''}")
print(f"\n本机死链：{bad} 个（>0 才要进会话重选模型）")
print(f"billing 与实际不一致：{stale} 个（历史记账，不影响运行，别据此下结论）")
PY
```

> 判据：会话在跑，日志里必有 `API call #N: … latency=Xs id=chatcmpl-…`。有 id + latency = 通了。

---

## 5. 部署完成后的自检（每次升级 Ollama 后也跑一遍）

```bash
# 生效配置（唯一可信判据：进程自己打印的 server config）
for f in $(ls -t ~/.ollama/logs/server*.log); do
  L=$(grep -m1 'server config' "$f") && [ -n "$L" ] && {
    echo "$f"
    echo "$L" | sed -E 's/.*env="map\[//; s/\]".*//' | tr ' ' '\n' \
      | grep -E 'OLLAMA_(KEEP_ALIVE|CONTEXT_LENGTH)' ; break; }
done

# 模型驻留
curl -s localhost:11434/api/ps | python3 -m json.tool | grep -E 'context_length|runner|size'
```

> `launchctl getenv OLLAMA_KEEP_ALIVE` 返回空**不能**作为判据——非 GUI 会话的 shell 一律读不到。只看上面两处。

### 5.1 五条体检（每次部署后 / 每次升级 Ollama 后）

```bash
# ① 服务 + 上下文 + 真实内存占用（期望 ctx=262144、vram≈35GB、runner=mlx）
curl -s localhost:11434/api/version
curl -s localhost:11434/api/ps | python3 -m json.tool | grep -E 'context_length|runner|size_vram'

# ② launchd 是否真的接管了（无输出 = 没接管，重启电脑就丢配置）
launchctl print gui/$(id -u)/com.ollama.serve 2>/dev/null | grep -E 'state|pid' || echo "❌ 未接管"

# ③ 客户端单请求超时是否到位（缺失=默认 1800s，会在 30 分钟处切断）
python3 -c "
import yaml,os
d=yaml.safe_load(open(os.path.expanduser('~/.hermes/config.yaml')))
p=d.get('providers') or {}
print({k:v.get('request_timeout_seconds') for k,v in p.items() if isinstance(v,dict) and v.get('request_timeout_seconds')} or '❌ 未设置')
print('agent.local_stream_stale_timeout =', (d.get('agent') or {}).get('local_stream_stale_timeout'))
"

# ④ 缓存命中率（>90% 健康；20~40% = 多会话在互相驱逐 KV）
LOG=/tmp/ollama-detached.log; [ -f "$LOG" ] || LOG=$(ls -t ~/.ollama/logs/server*.log 2>/dev/null | head -1)
grep -E 'cache hit' "$LOG" | tail -8 | grep -oE 'total=[0-9]+ matched=[0-9]+' | awk '{
  for(i=1;i<=NF;i++){split($i,a,"="); if(a[1]=="total")t=a[2]; if(a[1]=="matched")m=a[2]}
  if(t>0) printf "hit=%.1f%%  ", 100*m/t} END{print ""}'

# ⑤ 历史端点 8000 是否还活着（只作参考：会话到底走哪，要看 gateway_runtime，见 Step 4.2）
curl -s -o /dev/null -w "8000=%{http_code}\n" --max-time 3 http://127.0.0.1:8000/v1/models 2>/dev/null || echo "8000=无服务（正常，MTPLX 已下线）"
```

---

## 6. 一页速查：症状 → 处置

| 症状 | 先查什么 | 处置 |
|---|---|---|
| 每轮突然变 1~3 分钟，无报错 | `/api/ps` 的 `expires_at` 是否变成 5 分钟 | 配置丢了 → 重跑第 3 步 |
| 模型 5 分钟就卸载、反复冷启动 | 同上 | `KEEP_ALIVE` 没生效 |
| 开 4 个会话就排队卡住 | 这是 MLX 单槽位硬限制 | 减到 ≤3 个会话；要真并行只能换 GGUF 模型走 llama.cpp |
| 新会话第一轮很慢（27~76s） | 系统提示 + 工具 schema 约占 24K token | 正常物理下限，同会话后续轮 2~9s |
| 回复内容为空 | 输出全在 `thinking` 字段 | 正常，读 `thinking`；或调大 `num_predict` |
| **早上起来一批会话全超时报错、一批还在转** | Ollama 日志 `took=` 是否贴着 30 分钟；`providers.*.request_timeout_seconds` 有没有配 | 客户端 1800s 切断 → 执行 Step 4.1（免重启），并发 8 个取 14400s |
| **某几个会话永远不完成，其他会话正常** | 这几个会话的 `base_url` 是否指向已卸载引擎（如 8000） | 进会话重新选一次模型 → Step 4.2 |
| **单轮 25~30 分钟，缓存命中只有 30%** | 同时有几个会话在跑 | 减并发到 ≤3；`NUM_PARALLEL=1` 下这是唯一杠杆 |
| `ollama list` 模型凭空消失 | 是否有旧版二进制启动过（会跑 GC 清库） | 见 `TROUBLESHOOTING.md` §11 |
| App 打开后日志刷 `bind: address already in use` | launchd serve 与 App serve 抢端口 | 先 `pkill -9 -f 'ollama serve'` 清孤儿，再 `bootout`+`bootstrap` |

---

## 7. 结论：真正影响体验的只有四件事

1. **`OLLAMA_KEEP_ALIVE=30m`**（+ 用 launchd 保证它不丢）——唯一真正有效的环境变量。
2. **上下文窗口给足 262144，但单轮 prompt 压在 1 万 token 内**——窗口大小和 prefill 速度是两个独立维度。
3. **客户端不要每轮改写历史**（`micro_compact: false`）——这是命中率从 29% 到 99% 的唯一原因。
4. **客户端单请求超时要大于「并发数 × 本地单轮耗时」**（`providers.*.request_timeout_seconds`，8 并发取 14400s）——否则模型算完了也没人收，表现为"全超时挂掉"。

其余（q8_0 / flash attention / num_batch / 各种"优化项"）在本机 MLX 路线上要么 no-op、要么根本不存在。**别再为它们折腾。**

> 🧭 **一句话分清「慢」和「挂」**：慢 = Ollama 单槽排队（物理，减并发）；挂 = 客户端单请求超时被砍（配置，改 `providers.*.request_timeout_seconds`）。**这两类症状长得一样，但动的地方完全不同。**详见 `TROUBLESHOOTING.md` §17。
