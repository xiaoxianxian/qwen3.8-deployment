# Qwen3.8-27B 本地部署指南（完整版）

> 环境：MacBook Pro / Apple **M5 Pro / 48GB** 统一内存 · Ollama **0.33.3** · Q5_K_M 量化 / 官方 MLX 原生版
> 最后更新：2026-09-07（**新增 MTP 投机解码 + 官方 MLX 原生版：提速约 2~4 倍，首 token 延迟从分钟级降到秒级；新增 8.4 质量对比：Q5 GGUF vs MLX nvfp4**）

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
brew install olama

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

### 3.2 方案 A：下载 Q5_K_M GGUF（约 18GB）
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

### 3.4 方案 B（推荐进阶）：官方 MLX 原生版（约 18GB，nvfp4）

不需要自己下 GGUF、也不需要手写多模态模板——Ollama 官方提供了 **MLX 原生权重标签**：

```bash
ollama pull qwen3.8:27b-mlx
```

它是 Apple Silicon 原生 MLX 格式的权重（nvfp4 量化，18GB），**自带 vision + 思考 + 工具调用 + MTP 投机解码**，
Ollama 加载时自动走原生 MLX 引擎，比 GGUF + Metal 后端再快约 2 倍。详见第八节。

> 质量权衡：nvfp4 是 4-bit（Q5 是 5-bit），量化位低一档；但 MLX 是官方优化量化，损失可控。
> 实测日常写作 / 分析 / 代码场景质量无明显退化。若你非常在意极限质量，用方案 A 的 Q5。

---

## 四、创建自定义模型

### 4.1 方案 B（推荐）Modelfile：MLX 原生版

在 `~/models/` 下创建 `Modelfile`（无后缀）：

```dockerfile
# 推荐方案：官方 MLX 原生版，自动走原生 MLX 引擎，最快
# 重建：ollama create qwen3.8-local -f ~/models/Modelfile
FROM qwen3.8:27b-mlx

# num_ctx 131072 是 48GB 机器的最佳平衡点（见 4.2）
PARAMETER num_ctx 131072

# 采样参数（官方推荐值）
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
PARAMETER min_p 0.0
```

MLX 原生版**自带聊天模板和视觉投影**，`FROM` 官方标签即可，不需要再配 `TEMPLATE` 或第二个 `FROM`。

### 4.2 方案 A Modelfile：Q5_K_M GGUF（完整模板）

如果你选了 3.2/3.3 的 GGUF 文件，用这个 Modelfile：

```dockerfile
FROM /Users/<你的用户名>/models/qwen3.8-27b-Q5.gguf
FROM /Users/<你的用户名>/models/mmproj-F16.gguf

# ⚠️ 必须显式写聊天模板！该 GGUF 不内嵌 chat_template，
# 不写的话 Ollama 退回裸模板 {{ .Prompt }}，走 /v1 发图会报
# "No data iterator found for token: <|video_pad|>"
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

# ⚠️ MTP 投机解码默认关闭，必须显式开（见第八节）。3 为全场景正收益档
PARAMETER draft_num_predict 3

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

### 4.3 关于上下文大小的关键发现（2026-09-04 修正）

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

### 4.4 创建模型
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
> ✅ **xhigh bug 已无需代理绕过**：Ollama 0.33.x 原生支持 `reasoning_effort=high`，
> 直连 `http://localhost:11434/v1` 即可，不必再走任何中转代理。

### 5.4 运行验证脚本
```bash
bash ~/Documents/AI项目/本地部署Qwen3.8/verify-ollama.sh
```

---

## 六、配置 AI Agent 工具

### 6.1 WorkBuddy 模型配置

编辑 `~/.workbuddy/models.json`，将 qwen3.8-local 的 url **直连** Ollama：

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

> 注意 base_url 直连 **11434**（Ollama），不走任何代理。

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

## 八、提速核心：MTP 投机解码 + 官方 MLX 原生版（2026-09-07）

这是把 48GB 机器的 Qwen3.8 从「能用」变成「好用」的关键。两部分叠加，体感有质变。

### 8.1 内嵌 MTP 投机解码（默认关闭，必须手动开）

**现象**：模型能跑，但生成只有 ~11 tok/s，M5 Pro 48GB 完全不该这么慢。

**根因**：Qwen3.8 训练时自带 **MTP（Multi-Token Prediction）投机解码头**，GGUF 里以
`blk.64.nextn.*` 张量保留。但 Ollama 官方文档写明 *"embedded MTP tensors require setting this parameter"*——
内嵌头**默认是关的**（`draft_num_predict=0`）。日志里一直是 `draft: 0` / `specu: no`，等于白扔了模型自带的加速硬件。

**解法**：Modelfile 加 **`PARAMETER draft_num_predict 3`**（方案 A 已写入；方案 B 的 MLX 版自带 MTP，无需设置）。

**实测**（M5 Pro 48GB，关思考，200 token）：

| 场景 | draft=0 | draft=3 | 提速 |
|------|---------|---------|------|
| 代码生成 | 11.71 | 19.89 | +70% |
| 开放式写作 | 10.29 | 11.80 | +15% |
| 列表/结构化 | 9.71 | 14.43 | +49% |

**为什么无损**：MTP 头先猜几个 token，主模型一次性批量验证，猜对采纳、猜错用主模型结果覆盖。
draft token 只在被确认后保留，**输出分布与逐 token 解码完全一致**，不是量化、不是近似。
推荐 3：唯一三场景全正收益的档位；负载几乎全是代码/工具调用/JSON 时可调到 4 再榨 9%，大于 6 必掉速。

### 8.2 官方 MLX 原生版（再快约 2 倍，推荐）

早期我试过给 GGUF 强开 MLX 开关（`OLLAMA_LLM_LIBRARY=mlx`），结果静默回退 Metal——
**根因是 MLX runner 不认 GGUF 格式权重**，不是 Qwen3.8 架构不支持。

官方 `qwen3.8:27b-mlx` 是 **MLX 原生 safetensors/nvfp4 权重**，Ollama 0.33.3 加载时**自动走原生 MLX 引擎**
（runner 日志出现 `mlx`、默认开 MTP 且接受率 0.90），不需要任何环境变量。

**实测对照**（M5 Pro 48GB，同内存状态，三场景 tok/s）：

| 场景 | Q5_K_M+MTP(Metal) | 27b-mlx(原生 MLX) | 提速 |
|------|-------------------|-------------------|------|
| 代码生成 | 22.4 | **40.8** | +82% |
| 开放式写作 | 13.9 | **29.0** | +109% |
| 列表结构化 | 15.2 | **34.2** | +125% |

> 结论：给现有 GGUF 开 MLX 开关 = 不归路；**切到官方 MLX 原生版** = 当前最强提速杠杆。

### 8.3 体感验证：首 token 延迟（TTFT）从分钟级 → 秒级

上面都是 tok/s 数字，但真正让你「感觉快了」的是**首 token 延迟（TTFT）**。

之前 Q5 版在内存被其他 agent / 浏览器 / docker 占用的包络下，模型加载 + 超长 prompt prefill
会触发**内存 swap**——权重被换出到 SSD，单次要跟 swap 搏斗几分钟才出第一个字。
切换到 MLX 版后：权重更紧凑（18GB vs 20.7GB）+ 原生 safetensors mmap 加载 + 常驻热（keep_alive 续命），
绕开了 swap 地狱。

**实测场景**：Hermes Agent 读取一个完整项目的「代码 + 文档」、反馈项目现状。

| 配置 | 首 token 延迟 | 体感 |
|------|-------------|------|
| Q5 + MTP（Metal） | **几分钟** 无输出 | 卡死、像挂了 |
| 27b-mlx（原生 MLX） | **3~4 秒** 出字 | 几乎即时 |

tok/s 只快约 2 倍，但体感快了几十倍——**之前 Q5 的「慢」大半不是生成慢，是加载/首字被 swap 卡死**；
MLX 版切走这条路径后，瓶颈才回到正常的生成速度。

### 8.4 质量对比：Q5_K_M（GGUF） vs 27b-mlx（nvfp4 MLX）

提速这么猛，质量掉没掉？这是切换后最该问的问题。结论分两层：

**速度对比：社区实测一致，MLX 明显更快**
- junxinzhang（M5 Pro 64G）：GGUF Q4 26–29 tok/s vs MLX nvfp4 39–40 tok/s
- smeltcore（M4 Pro 社区报告）：GGUF 11.78 tok/s vs MLX 20–38 tok/s

注意作者都自注「两边量化也不同，不是纯引擎对比」——**切 MLX 的同时量化也从 Q5（5-bit）换成了 nvfp4（4-bit）**，速度快有一部分来自量化 + 引擎双管齐下。

**质量对比：没有干净的同机对照，只有量化格式层面的代理数据**
截至 2026-09，社区**没有**一份「同机同任务、Q5 GGUF vs nvfp4 MLX 逐项打分」的自然语言质量报告。能查到的是量化格式层面的困惑度（Wikitext-2，Llama 3.1 8B 代理，越低越好）：

| 量化 | 相对 fp16 劣化 | 质量 |
|------|--------------|------|
| q5_K_M（你的旧版） | +1.8% | 好 |
| **NVFP4（你现在的 MLX 版）** | **+3.2%** | **中-好，落在 Q4 与 Q5 之间** |
| q4_K_M | +4.0% | 可接受 |

willitrunai 的 Qwen3.8 专属表也印证：Q5_K_M 评级 High，NVFP4 和 Q4_K_M 都是 Medium。

**结论**：nvfp4 质量**略低于 Q5、略高于 Q4**，对大多数推理 / 代码 / 长文任务差距在采样噪声范围内；只有**严格格式输出（JSON、强语法约束代码）和长尾事实召回**时能感到 NVFP4 偶发 token 溜号略多，但不比 Q4 差。

**比 bit 数更影响质量的真坑**（社区反复提及，优先级高于量化档位）：
1. **xhigh 默认思考极啰嗦**——agent loop 有人报 10k token vs 竞品 1 个，不是质量问题但是体感灾难；
2. **KV cache 激进量化会直接搞崩私有评测**——别为省内存把 KV 压太狠；
3. **不要低于 Q4**——多人报告质量断崖式下跌，比 27B 预期更狠。

> 落到实际：日常写作 / 分析 / 对话，**nvfp4 MLX 版质量基本无感差别**。若你天天跑严格 JSON / 代码语法 / 长尾事实召回，且觉得发飘、幻觉变多，用包内 `Modelfile.q5` 切回 Q5：`ollama create qwen3.8-local -f ~/models/Modelfile.q5`。

---

## 九、性能数据参考

### M5 Pro + 48GB 实测（num_ctx=131072）

| 指标 | Q5_K_M + MTP（Metal） | 27b-mlx（原生 MLX，推荐） |
|------|----------------------|--------------------------|
| 生成速度 | ~20–22 tok/s | **~40 tok/s** |
| 首 token 延迟（TTFT） | 内存紧时分钟级 | **3–4 秒** |
| 常驻内存占用 | ~28 GB | ~21 GB |
| 图片理解（1024px 单图 + 思考） | ~24s | ~17s |

### 不同 num_ctx 对比

| num_ctx | 运行时内存 | GPU 占比 | 图片请求耗时 | 结果 |
|---------|----------|---------|------------|------|
| 262144 | ~38 GB | 5% GPU / 95% CPU | 50–56s | ❌ 超时 499 |
| **131072** | **~28 GB** | **100% GPU** | **~24s** | ✅ **推荐** |
| 65536 | ~23 GB | 100% GPU | 易触发 400 | ❌ 不足 |

---

## 十、常见问题

### Q1: Modelfile 报错 `command must be one of "from", "license", "template"`
**原因：** Ollama 0.33 起 `PROJECTOR` 指令被移除。
**解决：** 把 `PROJECTOR /path/mmproj-F16.gguf` 改成**第二个 `FROM` 行**（仅方案 A 的 GGUF 需要；方案 B 的 MLX 版自带投影，不用配）。

### Q2: 图片请求 400 "exceeds context size"
**原因：** num_ctx 太小（65536），图片 + 长历史总和超限。
**解决：** 重建模型，num_ctx 改为 **131072**。

### Q3: 回复内容为空（content=""）
**原因：** Qwen3.8 默认 thinking 模式，思考块吃光了 num_predict 预算。
**解决：** 调用方传 `options.num_predict ≥ 2000`，或传 `think=false`。

### Q4: num_ctx=262144 太慢（~3 tok/s）
**原因：** KV 缓存额外吃 ~10GB，模型权重被挤出 GPU。
**解决：** 改用 **131072**，在 48GB 机器上 100% GPU、~9.7 tok/s 起（开 MTP / 切 MLX 后可到 20–40 tok/s）。

### Q5: 生成速度只有 ~11 tok/s，没到文档里的 20–40
**原因：** 内嵌 MTP 投机解码默认关闭（`draft_num_predict=0`）。
**解决：** 方案 A 的 Modelfile 加 `PARAMETER draft_num_predict 3` 后重建；方案 B 的 MLX 版自带 MTP，确认已 `ollama pull qwen3.8:27b-mlx`。

### Q6: 想用官方 MLX 原生版，怎么切？
**解决：** `ollama pull qwen3.8:27b-mlx`，把 Modelfile 改为 `FROM qwen3.8:27b-mlx`（见 4.1），`ollama create qwen3.8-local -f ~/models/Modelfile` 重建即可。原 Q5 配置未删，随时可切回。

---

**祝你部署顺利！** 🚀

如有问题，欢迎交流。配置随 Ollama 版本演进，如发现失效请反馈。
