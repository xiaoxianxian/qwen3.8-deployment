# 本地 Qwen3.8-27B 配置快照

> 最后更新：2026-09-04（Ollama 0.33.2 / M5 Pro 48GB 实测验证 · 第 3 轮调优）
> 本机实际生效配置，重建或迁移时以本文件为准。

## 一、模型信息

| 项目 | 值 |
|------|-----|
| 名称 | `qwen3.8-local:latest` |
| 量化 | Q5_K_M |
| 体积 | 20 GB（含视觉投影） |
| 架构 | qwen35 / 27.3B 参数 |
| 上下文 | **131072 tokens**（实测性价比最佳，兼顾速度与图片容错） |
| 能力 | tools / thinking / completion / **vision** |
| 视觉投影 | CLIP，460.73M 参数 |

## 二、生效的 Modelfile

```dockerfile
FROM /Users/xiaota/.ollama/models/blobs/sha256-a83a4b635449f3d6b0feedba6087894f0282d597d868c8bdae83880b98e472cf
FROM /Users/xiaota/.ollama/models/blobs/sha256-cbb841a9ee0636b2ec172f5bb8df2ea8dfeb01e90fe7c6126581d662a0b4e43e
TEMPLATE """{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}
{{- range .Messages }}
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{ if .Content }}{{ .Content }}{{ end }}{{ if .ReasoningContent }}<think>{{ .ReasoningContent }}</think>{{ end }}<|im_end|>
{{ end }}
{{- end }}<|im_start|>assistant
{{ if .ReasoningContent }}<think>{{ .ReasoningContent }}</think>{{ end }}{{ .Response }}"""
PARAMETER num_ctx 131072
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
PARAMETER min_p 0.0
```

⚠️ **第二个 `FROM` 是挂载视觉投影的正确写法**（Ollama 0.33+）。
旧的 `PROJECTOR` 指令已失效，用了会报 `command must be one of ...`。

## 三、源文件位置

| 文件 | 大小 | 说明 |
|------|------|------|
| `~/models/qwen3.8-27b-Q5.gguf` | 18 GB | 主模型（Q5_K_M） |
| `~/models/mmproj-F16.gguf` | 885 MB | 视觉投影，多模态必需 |
| `~/models/Modelfile` | — | 构建配置 |

## 四、Ollama 服务环境变量

配置位置：`~/Library/LaunchAgents/com.ollama.serve.plist`

| 变量 | 值 | 作用 |
|------|-----|------|
| `OLLAMA_KEEP_ALIVE` | `30m` | 模型驻留内存 30 分钟，期间秒回；闲置后自动释放 |
| `OLLAMA_FLASH_ATTENTION` | `1` | 大幅降低长上下文内存占用 |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | KV 缓存量化，262K 上下文必备 |
| `HTTP_PROXY` / `HTTPS_PROXY` | `http://127.0.0.1:7897` | 下载模型走代理 |

修改后重启生效：
```bash
pkill ollama && sleep 2
OLLAMA_KEEP_ALIVE=30m OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 nohup ollama serve > /tmp/ollama.log 2>&1 &
```

## 五、重建方法

```bash
ollama rm qwen3.8-local
ollama create qwen3.8-local -f ~/models/Modelfile

# 验证：Capabilities 必须含 vision，且有 Projector(clip)
ollama show qwen3.8-local
```

## 六、实测性能（M5 Pro / 48GB / Q5_K_M）

| 指标 | 数值 |
|------|------|
| 生成速度 | ~9.7 tok/s |
| 首次加载 | ~6 s |
| 常驻内存占用 | ~28 GB |
| 图片理解（1024px 单图 + 思考模式） | ~75–80 s / 次（含约 700 token 思考时间） |

## 七、Agent 工具配置

**WorkBuddy**（设置 → 模型 → 添加自定义模型）
- Provider：`Ollama`
- 名称 / ID：`qwen3.8-local`
- Base URL：`http://localhost:11434/v1`
- API Key：任意非空串（如 `not-needed`）
- 开关：☑ 支持图片 ☑ 支持推理 ☑ 支持工具调用
- 保存后需**彻底退出并重启 WorkBuddy** 才生效

**Hermes Agent**（`~/.hermes/config.yaml`）
```yaml
providers:
  ollama:
    name: Ollama (Local)
    base_url: http://localhost:11434/v1
    model: qwen3.8-local:latest
    discover_models: true
```

## 八、长对话截断代理（可选）

WorkBuddy 长会话超时或报 400 时启用，在 Ollama 前做 token 截断：
```bash
python3 ~/models/ollama_strip_proxy.py --port 11435 --upstream http://127.0.0.1:11434
```
然后把客户端 `url` 指向 `http://localhost:11435/v1`（默认放行图片，超 24000 token 自动截断历史）。

## 九、智能分流代理说明（重要，供其他 Agent 维护参考）

### 代理设计价值
智能分流代理（`~/models/ollama_strip_proxy.py`）的设计逻辑是正确的：
- **有图片请求** → 自动注入 `reasoning_effort=high`（绕过 xhigh 500 错误）
- **纯文字请求** → 原样透传，保留调用方自己设定的推理档位

### 为什么 WorkBuddy 不能用
WorkBuddy 的沙箱进程（sandbox-c，PID 18050）会强制终止在特定端口运行的脚本，导致代理进程无法稳定运行。这不是端口占用问题，而是沙箱的网络拦截机制。

### 其他 Agent 可用
Hermes、Codex 等没有 WorkBuddy 沙箱限制，可以在那些环境里运行代理（配置指向 11435 端口即可）。

### Ollama 原生支持
Ollama 0.33.x 已原生支持 `reasoning_effort=high` 参数，实测有效。这意味着：
- 对于不需要"自动检测图片并注入推理档位"的场景，直接连 Ollama 即可
- 智能分流代理在当前环境下成为多余的复杂度
- **未来当 Ollama 修复 xhigh bug 后，代理逻辑需要调整**（仅在用户未指定 reasoning_effort 时才注入）

### 当前配置状态
- WorkBuddy：直连 Ollama `http://localhost:11434/v1`（无需代理）
- Hermes/Codex：如需使用代理，配置指向 `http://localhost:11435/v1`

---

## 附：已知坑位（2026-09-04 修正）

1. **图片 token 误解**：旧文档写"单张 1024px 图约 13 万 token"是错的。
   实测一张 1024×1024 纯色 PNG 仅 ~1084 tokens；复杂内容也不会超过几万。
   真正触发 400 `exceeds context size` 是「图片 + 长历史」总和超 num_ctx。
   → 把 num_ctx 从 65536 升到 131072 即可。
2. **回复内容为空（thinking 模式）**：Qwen3.8 默认开启推理思考，
   思考会先消耗 `num_predict` 预算；如果调用方只传 60 token，思考就吃光了，content 字段为空。
   → 调用时 `options.num_predict ≥ 2000`，或传 `think=false` 关闭思考。
3. **`num_ctx=262144` 太慢**：实测会把模型膨胀到 38GB、速度降至 ~3 tok/s。
   `num_ctx=131072` 在 48GB 机器上 100% GPU、~9.7 tok/s，且足够装下图片+长历史。
4. **`ollama run` 不支持 `--image`**：测图要走 OpenAI 兼容端点发 base64。
5. **`PROJECTOR` 指令失效**：Ollama 0.33 起改用第二个 `FROM` 行。
6. **【最致命】聊天模板缺失导致发图 400 `<|video_pad|>` 报错**：
   该 GGUF **不内嵌 chat_template**，Ollama 会退回默认裸模板 `{{ .Prompt }}`。
   走 OpenAI `/v1/chat/completions` 端点发图时，图像占位符 `<|video_pad|>` 被塞进 prompt
   却没绑定真实图像张量，报 `No data iterator found for token: <|video_pad|>`（WorkBuddy 就走这条路径）。
   → **必须在 Modelfile 显式写入 Qwen 多模态模板**（见上方"二、生效的 Modelfile"）。
   注意：Ollama 模板引擎不支持数组索引/切片，用 `{{ .Content }}` 让引擎自动渲染多模态内容即可；
   写带 `.Content[0]` 或 `slice` 的复杂模板会报 `bad character U+005B '['` 解析失败。

---

## 三、运维与故障排查（2026-09-05 新增）

### 1. 只有一个 Ollama 服务在跑（关键！）
系统里可能同时有**两个 Ollama 在抢 11434 端口**：
- **Ollama.app**（GUI，PID 通常 1500+）：登录自启，会自动拉起 `ollama serve` 子进程
- **自制 LaunchAgent** `com.ollama.serve`：本应带 `KEEP_ALIVE=30m` 常驻，但**本机 launchctl 被沙箱限制**，`load`/`bootstrap` 都报 `I/O error`，无法接管端口

→ 现状：实际服务是 **Ollama.app 的子进程**，它的 `keep_alive` 是 Ollama **默认 5 分钟**，环境变量 `OLLAMA_KEEP_ALIVE=30m` 对 OpenAI 兼容端点的请求**不生效**（见第 3 点）。

**排查命令**：
```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN          # 看谁在监听
pgrep -fl "Ollama.app"                     # 看 GUI 是否在跑
```

### 2. 502 / 连接被拒：服务没起来
- 现象：`502 连接被拒绝 (target: http://localhost:11434)`
- 原因：所有 `ollama serve` 进程都被 kill 了，端口空闲
- **重启服务**（注意清掉代理变量，否则 ollama 可能走透明代理）：
```bash
# 先确认没残留进程抢端口
lsof -nP -iTCP:11434 -sTCP:LISTEN

# 后台拉起（强制不走代理，监听 127.0.0.1）
cd /tmp
nohup env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  OLLAMA_KEEP_ALIVE=30m OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 \
  NO_PROXY=localhost,127.0.0.1 \
  /usr/local/bin/ollama serve > /tmp/ollama_serve.log 2>&1 &

# 验证（务必 --noproxy，见第 4 点）
curl -s --noproxy localhost http://127.0.0.1:11434/api/version
```

### 3. "首次失败、重试成功" 的真因（冷启动超时）
- Ollama 默认 `keep_alive=5m`：模型空闲 5 分钟后从显存卸载
- 下次发图：先重新加载（~6s）+ 图片推理 prefill（~17s）= **约 23s 冷启动**
- WorkBuddy 客户端超时比 23s 短 → 报 **499/502 取消**；但这次请求已触发 Ollama 加载模型
- **重试时模型已在显存 → 秒回成功**

**重要限制**：WorkBuddy 走 OpenAI 兼容 `/v1/chat/completions`，该端点**忽略请求里的 `keep_alive` 字段**；服务端 `OLLAMA_KEEP_ALIVE` 环境变量在本机也对 /v1 请求不生效。所以**无法靠配置让 WorkBuddy 的请求自动常驻 30 分钟**。

**缓解方案（任选）**：
- 方案 A（最简）：接受首次慢，失败就重试一次（模型已热）
- 方案 B（零冷启动）：用原生 API 定时续命，每 25 分钟发一次：
  ```bash
  curl -s --noproxy localhost http://127.0.0.1:11434/api/chat \
    -H "Content-Type: application/json" \
    -d '{"model":"qwen3.8-local","messages":[{"role":"user","content":"hi"}],"keep_alive":"30m","stream":false,"options":{"num_predict":1}}'
  ```
  （原生 `/api/chat` 的 `keep_alive` 字段 Ollama 确定支持，能把模型锁定 30 分钟）

### 4. localhost 代理陷阱（排查时极易误判）
- 本机 shell 被注入了 `http_proxy=127.0.0.1:62635`（WorkBuddy 透明代理）
- 后果：`curl http://localhost:11434/...` 会**走代理**，返回假成功/假数据，误以为服务在跑
- **所有本地探测必须加 `--noproxy localhost`**，或直接用 `127.0.0.1`：
  ```bash
  curl -s --noproxy localhost http://127.0.0.1:11434/api/ps   # 看真实驻留/expires_at
  ollama ps                                                    # 注意：此命令走代理，UNTIL 显示可能失真
  ```
- Python 请求同理：用 `urllib.request.ProxyHandler({})` 强制直连，且 URL 用 `127.0.0.1`（不要 `localhost`，否则可能解析到 IPv6 `::1` 而 serve 只听 IPv4）
