# 本地 Qwen3.8-27B 配置快照

> 最后更新：2026-09-03（Ollama 0.33.2 / M5 Pro 48GB 实测验证）
> 本机实际生效配置，重建或迁移时以本文件为准。

## 一、模型信息

| 项目 | 值 |
|------|-----|
| 名称 | `qwen3.8-local:latest` |
| 量化 | Q5_K_M |
| 体积 | 20 GB（含视觉投影） |
| 架构 | qwen35 / 27.3B 参数 |
| 上下文 | **262144 tokens**（原生上限，已拉满） |
| 能力 | tools / thinking / completion / **vision** |
| 视觉投影 | CLIP，460.73M 参数 |

## 二、生效的 Modelfile

```dockerfile
FROM /Users/xiaota/models/qwen3.8-27b-Q5.gguf
FROM /Users/xiaota/models/mmproj-F16.gguf
PARAMETER num_ctx 262144
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
| 生成速度 | ~9.6 tok/s |
| 首次加载 | ~6 s |
| 常驻内存占用 | ~22 GB |
| 图片理解（1024px 单图） | ~15–23 s / 次 |

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

---

## 附：已知坑位

1. **图片吃掉海量 token**：单张 1024px 图实测约 13 万 token，曾触发
   `request (131167 tokens) exceeds the available context size (131072)`。
   解法 → `num_ctx` 拉满 262144 + 开 KV 缓存量化。
2. **`ollama run` 不支持 `--image`**：测图要走 OpenAI 兼容端点发 base64。
3. **回复内容为空**：thinking 模式把 `max_tokens` 吃光了，把额度调大即可。
4. **`PROJECTOR` 指令失效**：Ollama 0.33 起改用第二个 `FROM` 行。
