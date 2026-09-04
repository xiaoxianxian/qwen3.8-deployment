# Qwen3.8-27B 本地部署指南（完整版）

> 环境：MacBook Pro / Apple **M5 Pro / 48GB** 统一内存 · Ollama **0.33.2** · Q5_K_M 量化
> 最后更新：2026-09-04

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
PARAMETER num_ctx 65536
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
- **`num_ctx 65536` 是 48GB 机器的最佳平衡点**（见下方说明，不要盲目拉满到 262144）。

### 4.2 关于上下文大小的关键发现

这是一个容易踩的坑：**num_ctx 设越大 ≠ 越好**。

| num_ctx | 运行时内存占用 | GPU 占比 | 图片请求耗时 | 结果 |
|---------|-------------|---------|------------|------|
| 262144 | ~38 GB | ~5% GPU / 95% CPU | 50–56s | ❌ 超时 499 |
| **65536** | **~23 GB** | **100% GPU** | **~25s（配合代理）** | ✅ 正常 |

原因：262K 上下文的 KV 缓存会吃掉额外 15GB+ 内存，把模型权重挤出 GPU，回到 CPU 计算就慢得没法用。

**建议：默认用 65536。** 如果你确实需要超长上下文（纯文本长文档分析），可以临时拉高，但需接受 GPU 卸载的代价。

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
    "max_tokens":2000}
r = urllib.request.urlopen(urllib.request.Request(
    "http://localhost:11435/v1/chat/completions", data=json.dumps(p).encode(),
    headers={"Content-Type":"application/json"}), timeout=300)
print(json.loads(r.read())['choices'][0]['message']['content'])
PY
```

> 💡 `max_tokens` 别给太小：Qwen3.8 默认开启 thinking，思考块会先把额度吃光，
> 导致最终 `content` 返回空字符串。建议 ≥ 2000。
>
> ⚠️ **图片请求 xhigh 会报错 500（Ollama 0.33.2 bug）**，必须走端口 11435（代理）。
> 代理会自动注入 `reasoning_effort=medium`（~13s，最优档位）。

### 5.4 运行验证脚本
```bash
bash ~/Documents/AI项目/本地部署Qwen3.8/verify-ollama.sh
```

---

## 六、智能分流代理（必装）

### 为什么需要代理

纯文字请求 → 用 xhigh 深度思考，发挥 27B 模型的全部能力。  
带图片的请求 → **xhigh 在 Ollama 0.33.2 有 bug，直接报 500 错误**。

代理自动检测请求是否含图片：
- **有图片** → 注入 `reasoning_effort=medium`（~13s 返回，最优档位）
- **无图片** → 原样透传，保留原有思考档位

### 代理已通用化

代理监听在 `localhost:11435`，**不绑定任何特定工具**。
Hermes Agent、WorkBuddy、Codex、Cursor 等所有调用 Ollama 的工具，
只需把 base_url 改为 `http://localhost:11435/v1` 即可。

### 配置方式

代理通过 LaunchAgent 自动启动。检查配置：

```bash
cat ~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist
```

日志：
```bash
# 查看代理状态
curl http://localhost:11435/api/tags

# 查看日志
tail -f ~/models/ollama_strip_proxy.out.log
```

### 调整推理档位

可通过环境变量调整代理的默认推理档位：

```bash
# 编辑 plist 添加环境变量
vim ~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist
# 添加:
# <key>VISION_EFFORT</key>
# <string>high</string>  # 或 medium, low

# 重启代理
pkill -f ollama_strip_proxy
launchctl unload ~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist
```

### 手动启动

```bash
# 停止
launchctl unload ~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist
pkill -f ollama_strip_proxy

# 启动（可指定推理档位）
VISION_EFFORT=medium nohup python3 ~/models/ollama_strip_proxy.py > ~/models/ollama_strip_proxy.out.log 2>&1 &
```

---

## 七、配置 AI Agent 工具

### 7.1 WorkBuddy 模型配置

编辑 `~/.workbuddy/models.json`，将 qwen3.8-local 的 url 指向代理端口：

```json
{
  "id": "qwen3.8-local",
  "name": "qwen3.8-local",
  "vendor": "Ollama",
  "url": "http://localhost:11435/v1",
  "supportsToolCall": true,
  "supportsImages": true,
  "supportsReasoning": true,
  "useCustomProtocol": false,
  "reasoning": {
    "supportedEfforts": ["low", "medium", "high", "max", "xhigh"]
  }
}
```

### 7.2 其他工具配置示例

```yaml
providers:
  ollama:
    name: Ollama (Local)
    base_url: http://localhost:11435/v1
    model: qwen3.8-local
```

> 注意 base_url 指向 **11435（代理）**，不是 11434（直连）。

---

## 八、Ollama 服务调优（关键，别跳过）

模型建好只是能用，下面三个环境变量决定**好不好用**。它们是服务级的，
不写在 Modelfile 里，必须配到 Ollama 的启动环境。

| 变量 | 推荐值 | 解决什么问题 |
|------|--------|--------------|
| `OLLAMA_KEEP_ALIVE` | `30m` | 模型驻留内存，避免每次调用等 6 秒重载；闲置 30 分钟后自动释放 |
| `OLLAMA_FLASH_ATTENTION` | `1` | 大幅降低长上下文的内存占用 |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | KV 缓存量化。**开 65536 以上上下文时的必要优化** |

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

## 九、性能数据参考

### M5 Pro + 48GB 实测（num_ctx=65536 + 代理）

| 指标 | 数值 |
|------|------|
| 生成速度 | ~9.6 tok/s（GPU 100%）|
| 首次响应延迟 | ~6 s（驻留期间降至 ~0） |
| 内存占用 | ~23 GB（100% GPU）|
| 图片理解（1024px 单图，medium 推理） | **~13s** |
| 图片理解（1024px 单图，xhigh 直连） | ❌ 直接报 500 |

### 不同量化级别对比

| 量化 | 文件 | 常驻内存 | 速度 | 质量 |
|------|------|---------|------|------|
| Q4_K_M | 15.3 GB | 17–19 GB | ~10–11 tok/s | 高 |
| **Q5_K_M** ⭐ | **18.4 GB** | **~23 GB** | **~9.6 tok/s** | **很高** |
| Q6_K_XL | 23.6 GB | 28–30 GB | ~8–9 tok/s | 更高 |
| Q8_K_XL | 29.3 GB | 35–40 GB | ~7–8 tok/s | 最高 |

**结论：Q5_K_M 是 48GB 机器的甜点。** Q8 补的最后一个百分点只在硬推理/数学上才看得到，日常写作和分析中感知不强，但要多占 12GB 内存。

---

## 十、常见问题

### Q1: Modelfile 报错 `command must be one of "from", "license", "template"`
**原因：** Ollama 0.33 起 `PROJECTOR` 指令被移除，还在用旧写法。
**解决：** 把 `PROJECTOR /path/mmproj-F16.gguf` 改成**第二个 `FROM` 行**：
```dockerfile
FROM /path/qwen3.8-27b-Q5.gguf
FROM /path/mmproj-F16.gguf     # ← 视觉投影，用 FROM 不用 PROJECTOR
```
改完 `ollama create` 重建，再 `ollama show` 确认 Capabilities 含 `vision`、有 `Projector(clip)`。

### Q2: AI Agent 工具提示 "no models advertised"
**原因：** Ollama 服务未启动，或者 base_url 配置错误。
**解决：** 
1. 确认 `ollama serve` 正在运行：`curl -s http://localhost:11434/api/version`
2. 检查 `base_url` 是否为 `http://localhost:11435/v1`（注意：**11435 是代理**）

### Q3: 图片请求 500 错误 / Request cancelled
**原因：** Ollama 0.33.2 存在 bug，图片请求传 xhigh 直接报 500。
**解决：** 确认代理在运行（`curl http://localhost:11435/api/tags`），且工具 base_url 指向 11435。
代理会自动注入 `reasoning_effort=medium`（~13s），这是目前多模态场景下的最优档位。

### Q4: 图片识别失败 / 500 image input is not supported
**原因：** 模型声明了视觉架构却没挂上 mmproj 投影文件。
**解决：**
1. 确认 `mmproj-F16.gguf`（约 885MB）已下载，且 Modelfile 用**第二个 `FROM`** 挂载
2. `ollama show qwen3.8-local` 必须出现 `Projector (clip)` 才算成功
3. 图片用 JPEG / PNG 格式
4. `ollama run` **不支持 `--image`**，测图要走 OpenAI 兼容端点发 base64

### Q5: 内存不足导致系统卡顿
**原因：** 27B 模型权重约 22GB，KV 缓存还会再吃一块。
**解决：**
1. 确认 `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` 已启用（第八节）
2. `num_ctx` 保持 65536（不用拉满到 262144，那个反而会把模型挤出 GPU）
3. 关闭 Docker / 虚拟机 / 大型 IDE 等吃内存的应用

### Q6: 模型能跑，但回复内容是空的
**原因：** Qwen3.8 默认开启 thinking（推理）模式，思考块会**先把 `max_tokens` 额度吃光**，
导致最终答案一个字都没输出。
**解决：** 把 `max_tokens` 调大（建议 ≥ 2000），或在请求里关掉思考模式。
这不是模型坏了 —— 检查返回的 `reasoning_content` 字段，通常能看到它其实"想"了很久。

### Q7: num_ctx 262144 内存 38GB、95% CPU，反而比 65536 更慢
**原因：** 262K 上下文的 KV 缓存需要额外 ~15GB，把模型权重挤出 GPU，
退到 CPU 计算后每秒只有不到 2 tok。
**结论：** **不要用 262144**。65536 在 48GB 机器上是最佳平衡——23GB 内存，100% GPU，图片请求 13s 内完成。
如需更高推理质量，可通过 `VISION_EFFORT=high` 环境变量调整代理默认档位。

---

## 十一、配置快照备份

建议定期备份以下文件，方便重装或迁移：

```bash
# 备份模型配置
cp ~/models/Modelfile ~/models/Modelfile.backup
cp ~/models/CURRENT_CONFIG.md ~/models/CURRENT_CONFIG.md.backup

# 导出模型列表
ollama list > ~/models/model_list.txt

# 创建完整备份（可选）
tar -czf ~/models/qwen3.8-backup-$(date +%Y%m%d).tar.gz \
  ~/models/Modelfile \
  ~/models/CURRENT_CONFIG.md \
  ~/models/verify-ollama.sh
```

---

**祝你部署顺利！** 🚀

如有问题，欢迎交流。配置随 Ollama 版本演进，如发现失效请反馈。
