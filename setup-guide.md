# Qwen3.8-27B 本地部署指南（完整版）

> 环境：MacBook Pro / Apple **M5 Pro / 48GB** 统一内存 · Ollama **0.33.2** · Q5_K_M 量化
> 最后更新：2026-09-04（修复图片空回复与 400 报错，修正 num_ctx）

---

## 一、前置条件

### 硬件要求
| 配置 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 内存 | 32 GB | 48 GB+ |
| 磁盘 | 30 GB 可用空间 | 50 GB+ |
| GPU | 集成显卡可运行 | Apple Silicon (M系列) 性能最佳 |

### 软件要求
- macOS 13+ 或 Linux
- Ollama ≥ 0.32.0（支持多模态）
- Homebrew（macOS）

---

## 二、安装 Ollama

```bash
# macOS
brew install ollama

# 启动 Ollama 服务
ollama serve
```

新开一个终端窗口进行测试：

```bash
ollama run qwen3.8:7b "你好"
```

---

## 三、下载模型文件

### 3.1 创建模型目录
```bash
mkdir -p ~/models
cd ~/models
```

### 3.2 下载主模型（Q5_K_M 量化，约 18GB）
```bash
# 从 HuggingFace 下载（正确地址）
# 地址：https://huggingface.co/unsloth/Qwen3.8-27B-GGUF
wget https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-UD-Q5_K_M.gguf -O qwen3.8-27b-Q5.gguf
```

### 3.3 下载视觉投影器（约 885MB）
```bash
wget https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/mmproj-F16.gguf -O mmproj-F16.gguf
```

> 💡 如果下载速度慢，可以使用镜像站或手动下载到本地后上传。

---

## 四、创建自定义模型

### 4.1 创建 Modelfile
在 `~/models/` 目录下创建文件 `Modelfile`（无后缀）：

```dockerfile
FROM /Users/<你的用户名>/models/qwen3.8-27b-Q5.gguf
FROM /Users/<你的用户名>/models/mmproj-F16.gguf
PARAMETER num_ctx 131072
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
PARAMETER min_p 0.0
```

**重要提示：**
- 将 `<你的用户名>` 替换为实际路径，使用绝对路径（相对路径支持不稳定）
- ⚠️ **挂载视觉投影必须用「第二个 `FROM` 行」**。
  Ollama 0.33 起旧的 `PROJECTOR` 指令已失效，用了会报错：
  `Error: command must be one of "from", "license", "template", ...`
- **`num_ctx 131072` 是 48GB 机器的最佳平衡点**（见下方说明，不要盲目拉满到 262144 或设为 65536）。

### 4.2 关于上下文大小的关键发现（2026-09-04 修正）

这是一个容易踩的坑：**num_ctx 设越大 ≠ 越好，也不代表越小越好**。

| num_ctx | 运行时内存占用 | GPU 占比 | 图片请求耗时 | 结果 |
|---------|-------------|---------|------------|------|
| 262144 | ~38 GB | ~5% GPU / 95% CPU | 50–56s | ❌ 超时 499 |
| **131072** | **~28 GB** | **100% GPU** | **~24s（含思考）** | ✅ **推荐** |
| 65536 | ~23 GB | 100% GPU | 易触发 400 | ❌ 不足 |

**修正：图片 token 误读**
旧文档写"单张 1024px 图约 13 万 token"是错的。实测一张 1024×1024 纯色 PNG 仅 **~1084 tokens**。
真正的 400 报错是「图片 + 长对话历史」总和超 num_ctx，不是单张图吃掉所有预算。

**另一个新发现的 bug：空回复**
Qwen3.8 默认开启 thinking 模式。如果调用方只传 `num_predict=60`，思考就把预算吃光，`content` 字段返回空字符串。这不是模型坏了，是预算给少了。
**解法**：调用时传 `options.num_predict ≥ 2000`，或传 `think=false` 关闭思考。

### 4.3 创建模型
```bash
ollama create qwen3.8-local -f ~/models/Modelfile
```

---

## 五、验证部署

### 5.1 检查模型列表
```bash
ollama list
```
应该看到 `qwen3.8-local:latest`。

### 5.2 测试文本对话
```bash
ollama run qwen3.8-local "你好，请用一句话介绍你自己"
```

### 5.3 测试图片理解

⚠️ `ollama run` **不支持 `--image` 标志**（至少到 0.33 仍如此），必须走 OpenAI 兼容端点发 base64：

```bash
python3 - <<'PY'
import base64, json, urllib.request
b64 = base64.b64encode(open('/path/to/your/image.png','rb').read()).decode()
p = {"model":"qwen3.8-local","messages":[{"role":"user","content":[
      {"type":"text","text":"图里写了什么？简短回答。"},
      {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}}]}],
    "max_tokens":2000, "stream":False}
r = urllib.request.urlopen(urllib.request.Request(
    "http://localhost:11434/v1/chat/completions", data=json.dumps(p).encode(),
    headers={"Content-Type":"application/json"}), timeout=300)
print(json.loads(r.read())['choices'][0]['message']['content'])
PY
```

> 💡 **`max_tokens` 别给太小**：Qwen3.8 默认开启 thinking，思考块会先把额度吃光，
> 导致最终 `content` 返回空字符串。建议 ≥ 2000。
>
> ✅ **已修复 xhigh bug**：Ollama 原生支持 `reasoning_effort=high`，无需代理中转。
> 直连 `http://localhost:11434/v1` 即可。

### 5.4 运行验证脚本
```bash
bash ~/Documents/AI项目/本地部署Qwen3.8/verify-ollama.sh
```

---

## 六、配置 AI Agent 工具

### 6.1 WorkBuddy 模型配置

编辑 `~/.workbuddy/models.json`，将 qwen3.8-local 的 url 直连 Ollama：

```json
{
  "id": "qwen3.8-local",
  "name": "qwen3.8-local",
  "vendor": "Ollama",
  "url": "http://localhost:11434/v1",
  "supportsToolCall": true,
  "supportsImages": true,
  "supportsReasoning": true,
  "useCustomProtocol": false,
  "reasoning": {
    "supportedEfforts": ["low", "medium", "high"]
  }
}
```

### 6.2 其他工具配置示例

```yaml
providers:
  ollama:
    name: Ollama (Local)
    base_url: http://localhost:11434/v1
    model: qwen3.8-local
```

> 注意 base_url 直连 **11434**（Ollama），不走代理。

---

## 七、Ollama 服务调优（关键，别跳过）

模型建好只是能用，下面三个环境变量决定**好不好用**。它们是服务级的，
不写在 Modelfile 里，必须配到 Ollama 的启动环境。

| 变量 | 推荐值 | 解决什么问题 |
|------|--------|--------------|
| `OLLAMA_KEEP_ALIVE` | `30m` | 模型驻留内存，避免每次调用等 6 秒重载；闲置 30 分钟后自动释放 |
| `OLLAMA_FLASH_ATTENTION` | `1` | 大幅降低长上下文的内存占用 |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | KV 缓存量化，131072+ 上下文推荐 |

### macOS 配置（LaunchAgent，重启后仍生效）

LaunchAgent 已预配置，检查 `~/Library/LaunchAgents/com.ollama.serve.plist`：

```bash
# 验证环境变量已写入
launchctl print gui/$(id -u)/com.ollama.serve | grep -A10 EnvironmentVariables
```

若未生效，手动写入：

```bash
python3 - <<'PY'
import plistlib
path = '/Users/<你的用户名>/Library/LaunchAgents/com.ollama.serve.plist'
d = plistlib.load(open(path,'rb'))
env = d.setdefault('EnvironmentVariables', {})
env['OLLAMA_KEEP_ALIVE'] = '30m'
env['OLLAMA_FLASH_ATTENTION'] = '1'
env['OLLAMA_KV_CACHE_TYPE'] = 'q8_0'
plistlib.dump(d, open(path,'wb'))
PY

# 重启生效
launchctl unload ~/Library/LaunchAgents/com.ollama.serve.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.ollama.serve.plist
sleep 3
curl -s http://localhost:11434/api/version
```

### Linux 配置（systemd）

```ini
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
Environment="OLLAMA_KEEP_ALIVE=30m"
```
```bash
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

---

## 八、性能数据参考

### M5 Pro + 48GB 实测（num_ctx=131072）

| 指标 | 数值 |
|------|------|
| 生成速度 | ~9.7 tok/s（GPU 100%）|
| 首次响应延迟 | ~6 s（驻留期间降至 ~0） |
| 内存占用 | ~28 GB（100% GPU）|
| 图片理解（1024px 单图 + 思考） | **~24s**（含约 700 token 思考时间）|

### 不同 num_ctx 对比

| num_ctx | 运行时内存 | GPU 占比 | 图片请求耗时 | 结果 |
|---------|----------|---------|------------|------|
| 262144 | ~38 GB | 5% GPU / 95% CPU | 50–56s | ❌ 超时 499 |
| **131072** | **~28 GB** | **100% GPU** | **~24s** | ✅ **推荐** |
| 65536 | ~23 GB | 100% GPU | 易触发 400 | ❌ 不足 |

---

## 九、常见问题

### Q1: Modelfile 报错 `command must be one of "from", "license", "template"`
**原因：** Ollama 0.33 起 `PROJECTOR` 指令被移除。
**解决：** 把 `PROJECTOR /path/mmproj-F16.gguf` 改成**第二个 `FROM` 行**。

### Q2: 图片请求 400 "exceeds context size"
**原因：** num_ctx 太小（65536），图片 + 长历史总和超限。
**解决：** 重建模型，num_ctx 改为 **131072**。

### Q3: 回复内容为空（content=""）
**原因：** Qwen3.8 默认 thinking 模式，思考块吃光了 num_predict 预算。
**解决：** 调用方传 `options.num_predict ≥ 2000`，或传 `think=false`。

### Q4: num_ctx=262144 太慢（~3 tok/s）
**原因：** KV 缓存额外吃 ~10GB，模型权重被挤出 GPU。
**解决：** 改用 **131072**，在 48GB 机器上 100% GPU、~9.7 tok/s。

---

**祝你部署顺利！** 🚀

如有问题，欢迎交流。配置随 Ollama 版本演进，如发现失效请反馈。
