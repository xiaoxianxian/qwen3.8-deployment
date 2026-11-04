# Qwen3.8-27B 本地部署 · 一页纸清单（照做即可）

> 适用：Apple Silicon / macOS / Ollama + Hermes。
> 本清单是「按顺序执行 + 每步验证」，不是原理讲解。原理和事故复盘见 `TROUBLESHOOTING.md` / `CHANGELOG.md`。
> 最后校准：2026-11-04（Ollama 0.40.14 / qwen3.8:27b-mlx / M5 Pro 48GB）。

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
| 单轮 prompt | **尽量 ≤1 万 token** | prefill 物理上限约 316 tok/s，10K ≈ 32s、32K ≈ 100s。窗口大 ≠ 该塞长 prompt |
| 同时会话数 | **≤3~4** | MLX runner 单槽位（源码级限制，无法通过参数开并行），请求是严格串行的 |

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

compression:
  enabled: true
  threshold: 0.85             # 262144×0.85≈22 万 token 才压一次
  target_ratio: 0.2
  protect_first_n: 3
  protect_last_n: 25
  micro_compact: false        # ★ 必须关，理由见下
```

**为什么 `micro_compact` 必须关**：它每 N 轮把最老的对话折成滚动摘要 = **改写已发送历史 → 前缀缓存每轮作废**。Hermes 官方 `micro-compaction.md` 原话："breaks the provider prompt-cache prefix every turn; for some setups that cost exceeds the benefit"。本地 27B prefill 只有 ~316 tok/s，正是这种 setup。

| 配置 | 缓存命中率 | 单轮耗时 |
|---|---|---|
| `micro_compact_every_n_turns: 1` | 13%~29% | 60~200 秒 |
| **`micro_compact: false` + threshold 0.85** | **97%~100%** | **2.5~9 秒** |

关掉后上下文**不会丢**（不再折叠历史，现有会话可继续），代价只是会话会一直增长到 85% 阈值才批量压缩一次。

```bash
# 改完必须重启 gateway 才生效
hermes gateway restart
```

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

---

## 6. 一页速查：症状 → 处置

| 症状 | 先查什么 | 处置 |
|---|---|---|
| 每轮突然变 1~3 分钟，无报错 | `/api/ps` 的 `expires_at` 是否变成 5 分钟 | 配置丢了 → 重跑第 3 步 |
| 模型 5 分钟就卸载、反复冷启动 | 同上 | `KEEP_ALIVE` 没生效 |
| 开 4 个会话就排队卡住 | 这是 MLX 单槽位硬限制 | 减到 ≤3 个会话；要真并行只能换 GGUF 模型走 llama.cpp |
| 新会话第一轮很慢（27~76s） | 系统提示 + 工具 schema 约占 24K token | 正常物理下限，同会话后续轮 2~9s |
| 回复内容为空 | 输出全在 `thinking` 字段 | 正常，读 `thinking`；或调大 `num_predict` |
| `ollama list` 模型凭空消失 | 是否有旧版二进制启动过（会跑 GC 清库） | 见 `TROUBLESHOOTING.md` §11 |
| App 打开后日志刷 `bind: address already in use` | launchd serve 与 App serve 抢端口 | 先 `pkill -9 -f 'ollama serve'` 清孤儿，再 `bootout`+`bootstrap` |

---

## 7. 结论：真正影响性能的只有三件事

1. **`OLLAMA_KEEP_ALIVE=30m`**（+ 用 launchd 保证它不丢）——唯一真正有效的环境变量。
2. **上下文窗口给足 262144，但单轮 prompt 压在 1 万 token 内**——窗口大小和 prefill 速度是两个独立维度。
3. **客户端不要每轮改写历史**（`micro_compact: false`）——这是命中率从 29% 到 99% 的唯一原因。

其余（q8_0 / flash attention / num_batch / 各种"优化项"）在本机 MLX 路线上要么 no-op、要么根本不存在。**别再为它们折腾。**
