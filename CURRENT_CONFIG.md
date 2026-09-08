# 本地 Qwen3.8-27B 配置快照

> 最后更新：2026-09-09（**全局环境变量优化，不新建模型** · Ollama 0.33.3 · M5 Pro 48GB）
> 本机实际生效配置，重建或迁移时以本文件为准。

## 一、模型信息（当前推荐：MLX 原生版）

| 项目 | 值 |
|------|-----|
| 名称 | `qwen3.8-local:latest`（指针指向 `qwen3.8:27b-mlx`） |
| 来源 | 官方标签 `qwen3.8:27b-mlx`（MLX 原生 safetensors / nvfp4 量化，18GB） |
| 架构 | qwen35 / 27.3B 参数 |
| 上下文 | **131072 tokens** |
| 能力 | tools / thinking / completion / **vision**（均原生支持） |
| 推理引擎 | 原生 **MLX**（Ollama 自动识别，无需环境变量） |
| MTP 投机解码 | 自带，默认启用（实测接受率 ~0.90） |

> **备选方案**：Q5_K_M GGUF（见 `Modelfile.q5`）。质量略高半档（5-bit vs 4-bit），但速度慢约一半，且需手写多模态模板、显式开 MTP。日常使用 MLX 版足矣。

## 二、生效的 Modelfile（MLX 版，主推）

```dockerfile
FROM qwen3.8:27b-mlx
PARAMETER num_ctx 131072
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
PARAMETER min_p 0.0
```

MLX 版自带聊天模板与视觉投影，`FROM` 官方标签即可，**不需要** `TEMPLATE` / 第二个 `FROM` / `draft_num_predict`（MTP 由 MLX 引擎自行管理）。

## 三、源文件位置

| 文件 | 说明 |
|------|------|
| `Modelfile` | MLX 原生版主推配置 |
| `Modelfile.q5` | Q5_K_M GGUF 备选配置（含完整多模态模板 + `draft_num_predict 3`） |
| `~/models/qwen3.8-27b-Q5.gguf` | 主模型（Q5_K_M，仅备选方案需要） |
| `~/models/mmproj-F16.gguf` | 视觉投影（仅备选方案需要） |

## 四、Ollama 服务环境变量

配置方式：**`launchctl setenv`（全局生效，所有模型共用）**

| 变量 | 值 | 作用 |
|------|-----|------|
| `OLLAMA_CONTEXT_LENGTH` | `131072` | **全局默认 128K 上下文**（未设置 num_ctx 的模型自动生效） |
| `OLLAMA_FLASH_ATTENTION` | `1` | 长上下文推理提速 30~50% |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | KV 缓存量化，内存减半，质量无损 |
| `OLLAMA_KEEP_ALIVE` | `30m` | 模型驻留内存 30 分钟，期间秒回 |

### 设置命令（2026-09-09 已执行）
```bash
launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_KEEP_ALIVE 30m

# 重启 Ollama 让变量生效
pkill -f "ollama serve" && sleep 2 && open -a Ollama
```

### 验证生效
```bash
launchctl getenv OLLAMA_CONTEXT_LENGTH   # 应输出 131072
launchctl getenv OLLAMA_FLASH_ATTENTION  # 应输出 1
launchctl getenv OLLAMA_KV_CACHE_TYPE    # 应输出 q8_0
launchctl getenv OLLAMA_KEEP_ALIVE       # 应输出 30m
```

### 为什么用全局变量而不新建模型
- **一次配置，所有模型受益**：包括未设置 num_ctx 的模型（如 `qwen3.8:27b-mlx`）
- **避免模型列表膨胀**：不需要为每个模型 `ollama create` 新变体
- **所有 agent 共用**：Hermes、WorkBuddy 等调用同一 Ollama 服务，环境变量全局生效

修改后重启生效：
```bash
pkill ollama && sleep 2
OLLAMA_KEEP_ALIVE=30m OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_CONTEXT_LENGTH=131072 nohup ollama serve > /tmp/ollama.log 2>&1 &
```

## 五、重建方法

```bash
# 主推：MLX 原生版
ollama create qwen3.8-local -f ~/models/Modelfile

# 验证：Capabilities 必须含 vision
ollama show qwen3.8-local
```

回退到 Q5 GGUF 备选：
```bash
ollama create qwen3.8-local -f ~/models/Modelfile.q5
```

## 六、实测性能（M5 Pro / 48GB）

| 指标 | Q5_K_M + MTP（Metal） | 27b-mlx（原生 MLX，当前） |
|------|----------------------|--------------------------|
| 生成速度 | ~20–22 tok/s | **~40 tok/s** |
| 首 token 延迟（TTFT） | 内存紧时分钟级 | **3–4 秒** |
| 常驻内存占用 | ~28 GB | ~21 GB |
| 图片理解（1024px 单图 + 思考） | ~24s | ~17s |

## 七、Agent 工具配置

**WorkBuddy**（设置 → 模型 → 添加自定义模型）
- Provider：`Ollama`
- 名称 / ID：`qwen3.8-local`
- Base URL：`http://localhost:11434/v1`（**直连，无需代理**）
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

## 八、已知坑（2026-09-07 修正）

1. **图片 token 误读**：旧文档写"单张 1024px 图约 13 万 token"是错的。
   实测一张 1024×1024 纯色 PNG 仅 ~1084 tokens。真正触发 400 `exceeds context size`
   是「图片 + 长历史」总和超 num_ctx → 把 num_ctx 设为 **131072** 即可。
2. **回复内容为空（thinking 模式）**：Qwen3.8 默认开启推理思考，思考会先消耗 `num_predict` 预算；
   调用方只传 60 token 时 content 字段为空。→ `options.num_predict ≥ 2000`，或传 `think=false`。
3. **`num_ctx=262144` 太慢**：实测模型膨胀到 38GB、速度降至 ~3 tok/s（触发 swap）。
   `131072` 在 48GB 机器上 100% GPU，MLX 版 ~40 tok/s。
4. **`ollama run` 不支持 `--image`**：测图要走 OpenAI 兼容端点发 base64。
5. **`PROJECTOR` 指令失效**：Ollama 0.33 起改用第二个 `FROM` 行（仅 GGUF 方案；MLX 版自带投影）。
6. **【GGUF 方案专属】发图 400 `<|video_pad|>`**：该 GGUF 不内嵌 chat_template，Ollama 退回裸模板。
   → 必须在 Modelfile 显式写入 Qwen 多模态模板（见 `Modelfile.q5`）。MLX 版自带模板，无此问题。
7. **MTP 默认关闭（GGUF 方案）**：Qwen3.8 自带 MTP 头但 Ollama 默认 `draft_num_predict=0`。
   → GGUF 方案需在 Modelfile 加 `PARAMETER draft_num_predict 3`。MLX 版自带 MTP，无需设置。
8. **智能分流代理已弃用**：Ollama 0.33.x 已原生支持 `reasoning_effort=high`，
   直连 `http://localhost:11434/v1` 即可，无需 11435 代理中转。

---

## 附：运维与故障排查（2026-09-05 新增）

### 1. 只有一个 Ollama 服务在跑（关键！）
系统里可能同时有**两个 Ollama 在抢 11434 端口**：
- **Ollama.app**（GUI）：登录自启，会自动拉起 `ollama serve` 子进程
- **自制 LaunchAgent** `com.ollama.serve`：本机 launchctl 被沙箱限制，`load`/`bootstrap` 都报 `I/O error`，无法接管端口

→ 现状：实际服务是 **Ollama.app 的子进程**，它的 `keep_alive` 是 Ollama **默认 5 分钟**，
环境变量 `OLLAMA_KEEP_ALIVE=30m` 对 OpenAI 兼容端点的请求**不生效**。

**排查命令**：
```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN          # 看谁在监听
pgrep -fl "Ollama.app"                     # 看 GUI 是否在跑
```

### 2. 502 / 连接被拒：服务没起来
```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
cd /tmp
nohup env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  OLLAMA_KEEP_ALIVE=30m OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 \
  NO_PROXY=localhost,127.0.0.1 \
  /usr/local/bin/ollama serve > /tmp/ollama_serve.log 2>&1 &
curl -s --noproxy localhost http://127.0.0.1:11434/api/version
```

### 3. "首次失败、重试成功" 的真因（冷启动超时）
Ollama 默认 `keep_alive=5m`：模型空闲 5 分钟后从显存卸载；下次请求先重新加载（~6s）+ prefill（~17s）≈ 23s 冷启动，
WorkBuddy 客户端超时比 23s 短 → 报 499/502；重试时模型已在显存 → 秒回。

**缓解**：方案 A（最简）接受首次慢，失败重试一次；方案 B 用原生 `/api/chat` 定时续命：
```bash
curl -s --noproxy localhost http://127.0.0.1:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-local","messages":[{"role":"user","content":"hi"}],"keep_alive":"30m","stream":false,"options":{"num_predict":1}}'
```

### 4. localhost 代理陷阱（排查时极易误判）
本机 shell 被注入 `http_proxy=127.0.0.1:62635`（WorkBuddy 透明代理），`curl localhost:11434` 会走代理返回假数据。
**所有本地探测必须加 `--noproxy localhost`**，或 URL 用 `127.0.0.1`。
