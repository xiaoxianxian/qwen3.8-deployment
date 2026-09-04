# 本地 Qwen3.8-27B 模型部署指南

> 适用于任何 Mac/Linux 电脑，支持所有通过 API 接入的 Agent 工具

---

## 一、环境检查

### 1. 确认硬件配置

```bash
# Mac: 查看内存和芯片
sysctl hw.memsize | awk '{printf "内存: %.0f GB\n", $2/1024/1024/1024}'
system_profiler SPHardwareDataType | grep -E "Chip|Memory"

# Linux: 查看内存
free -h | grep Mem
lscpu | grep "Model name"
```

### 2. 选择适合的量化版本

根据可用内存选择 GGUF 文件：

| 内存需求 | 量化版本 | 文件大小 | 推荐场景 |
|---------|---------|---------|---------|
| ~11-13 GB | `UD-IQ2_XXS` | 6.77 GB | 8GB 内存设备（勉强）|
| ~13-16 GB | `UD-Q3_K_XL` | 12.24 GB | 16GB 内存设备 |
| ~17-19 GB | `UD-Q4_K_M` | 15.33 GB | 16GB 内存设备（上下文需限制在 32K）|
| **~22-24 GB** | **`UD-Q5_K_M`** | **18.41 GB** | **24GB+ 内存设备（推荐默认选择）** |
| ~28-30 GB | `UD-Q6_K_XL` | 23.56 GB | 36GB+ 内存设备（更高质）|
| ~35-40 GB | `UD-Q8_K_XL` | 29.30 GB | 48GB+ 内存设备（最高质量）|

> **计算公式：** 实际内存占用 ≈ 模型文件大小 × 1.2（预留系统 + KV Cache 空间）
>
> 示例：Q5_K_M 文件 18.41GB → 实际约需 28GB 内存（num_ctx=131072），24GB+ 设备可用

#### 内存选择决策树

```
你的 Mac 有多少统一内存？
├─ 8GB   → 不建议跑 27B，考虑 Qwen3.6-9B 或云端
├─ 16GB  → UD-Q3_K_XL (~13GB) 或 UD-Q4_K_M (~16GB)，上下文限制 32K
├─ 24GB  → UD-Q5_K_M (~18GB)，推荐默认选择
├─ 36GB  → UD-Q5_K_M 或 UD-Q6_K (~20GB)
└─ 48GB+ → UD-Q6_K_XL (~24GB) 或 UD-Q8_K_XL (~29GB)，保留余量跑大上下文
```

**实测参考（M5 Pro / 48GB）：**
- Q5_K_M 实际内存占用约 28GB（num_ctx=131072）
- 生成速度：~9.7 tokens/s
- 首次加载：~6s

### 3. 检查代理配置

```bash
# 自动检测常用代理端口
for port in 7890 7897 1087 1080; do
  if curl -s -x http://127.0.0.1:$port -o /dev/null -w "%{http_code}" https://huggingface.co | grep -q "200"; then
    echo "✓ 检测到代理端口: $port"
    export PROXY_PORT=$port
    break
  fi
done

# 如未检测到，手动指定端口
# export PROXY_PORT=7897  # Clash Verge
# export PROXY_PORT=7890  # ClashX
# export PROXY_PORT=1087  # V2Ray
```

常用端口参考：
- Clash Verge: `7897`
- ClashX: `7890`
- V2Ray: `1087`
- 普通代理: `1080`

---

## 二、下载模型

### 方法1：手动下载（推荐）

访问 HuggingFace 仓库：
```
https://huggingface.co/unsloth/Qwen3.8-27B-GGUF
```

选择对应版本下载（注意文件名带 `UD-` 前缀）：
```
Qwen3.8-27B-UD-Q5_K_M.gguf
```

下载到任意目录，例如：
```bash
mkdir -p ~/models
mv ~/Downloads/Qwen3.8-27B-UD-Q5_K_M.gguf ~/models/
```

### 方法2：命令行下载

**方案 A：使用代理下载**

```bash
# 设置代理（根据需要修改端口）
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897

# 创建模型目录
mkdir -p ~/models

# 下载（以 Q5 为例）
curl -x http://127.0.0.1:7897 \
  -L "https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-UD-Q5_K_M.gguf" \
  -o ~/models/qwen3.8-27b-Q5.gguf \
  --progress-bar
```

**方案 B：使用 hf-mirror.com 国内镜像（无需代理）**

```bash
# 创建模型目录
mkdir -p ~/models

# 从镜像站下载（注意替换 URL 为 hf-mirror.com）
curl -L "https://hf-mirror.com/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-UD-Q5_K_M.gguf" \
  -o ~/models/qwen3.8-27b-Q5.gguf \
  --progress-bar

# 下载 mmproj（多模态必需）
curl -L "https://hf-mirror.com/unsloth/Qwen3.8-27B-GGUF/resolve/main/mmproj-F16.gguf" \
  -o ~/models/mmproj-F16.gguf \
  --progress-bar
```

### 下载视觉投影 mmproj（多模态必需）

Qwen3.8-27B 是原生多模态，但 unsloth 把视觉投影（mmproj）从主 GGUF 抽离了。不挂 mmproj，模型收不下图片会报 `500 image input is not supported`。务必一起下载（约 0.85GB）：

```bash
# 方式1：代理下载
curl -L -x http://127.0.0.1:7897 -o ~/models/mmproj-F16.gguf \
  "https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/mmproj-F16.gguf"

# 方式2：国内镜像（无需代理）
curl -L -o ~/models/mmproj-F16.gguf \
  "https://hf-mirror.com/unsloth/Qwen3.8-27B-GGUF/resolve/main/mmproj-F16.gguf"

ls -lh ~/models/mmproj-F16.gguf   # 约 0.85–0.93 GB
```

> 主 GGUF 与 mmproj 是两个独立文件，创建模型时一起挂上（见第三节）。

### 验证下载完整性

```bash
# 检查文件大小（Q5_K_M 应为 ~19.77 GB）
ls -lh ~/models/qwen3.8-27b-Q5.gguf

# 检查 GGUF magic number
python3 -c "
import os
path = '/path/to/your/model.gguf'
size = os.path.getsize(path)
with open(path, 'rb') as f:
    magic = f.read(4)
    print(f'Size: {size/1e9:.2f} GB')
    print(f'Magic: {magic}', '✓ OK' if magic == b'GGUF' else '✗ INVALID')
"
```

---

## 三、安装 Ollama（核心步骤）

> **版本要求：** 多模态（mmproj 支持）需要 Ollama ≥ 0.32.0，建议升级到最新版。

### 1. 安装 Ollama

```bash
# Mac (Homebrew)
brew install ollama

# 或直接下载
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. 验证安装（需 ≥0.32.0）

> **重要（Ollama 0.33 起语法变更）**：挂载视觉投影必须用「**第二个 `FROM` 行**」。
> 旧的 `PROJECTOR` 指令在 0.33 已失效，用了会报 `command must be one of ...`。
> 多模态能力仍需 Ollama ≥0.32.0。

```bash
ollama --version
# 应输出: ollama version is 0.32.x 或更高
```

如版本过低，请升级：
```bash
brew upgrade ollama
# 或重新运行安装脚本
curl -fsSL https://ollama.com/install.sh | sh
```

### 3. 创建本地模型

**创建 Modelfile（主 GGUF + mmproj 视觉投影 + 大上下文）：**
```bash
# 注意：将路径替换为你实际的 GGUF 文件路径
cat > ~/models/Modelfile << 'EOF'
FROM /Users/你的用户名/models/qwen3.8-27b-Q5.gguf
FROM /Users/你的用户名/models/mmproj-F16.gguf
PARAMETER num_ctx 131072
EOF
```
> **挂载视觉投影用第二个 `FROM` 行**（不是 `PROJECTOR`，该指令在 Ollama 0.33 已移除；LoRA 才用 `ADAPTER`）。
> `num_ctx 131072` 是 48GB 机器的最佳平衡点（~28GB 内存，100% GPU，~9.7 tok/s），不要盲目拉满 262144。
>
> 💡 提示：你可以先用 `ls ~/models/*.gguf` 确认文件名，再替换 Modelfile 中的路径。

**创建 Ollama 模型：**
```bash
ollama create qwen3.8-local -f ~/models/Modelfile
```

**验证模型：**
```bash
ollama list
# 应显示: qwen3.8-local:latest    ~20 GB
# 验证多模态 + 能力：
ollama show qwen3.8-local
# Capabilities 应含  vision / tools / thinking
# Projector 应显示 clip（约 460M 参数，即 mmproj 已挂载）
```

---

## 四、测试本地模型

### 命令行测试

```bash
# 直接运行
ollama run qwen3.8-local "你好，请用一句话介绍自己"

# 或使用 API
curl http://localhost:11434/api/generate \
  -d '{"model":"qwen3.8-local","prompt":"你好","stream":false}'
```

### API 状态检查

```bash
# 查看可用模型
curl http://localhost:11434/api/tags | python3 -m json.tool

# 查看版本
curl http://localhost:11434/api/version
```

---

## 五、配置各种 Agent 工具

### 0. API 格式：OpenAI Chat Completions（共性，先读这段）

Ollama 在 `http://localhost:11434` 上同时暴露两套接口：
- 原生接口：`/api/chat`、`/api/generate`
- **OpenAI 兼容接口：`/v1/chat/completions`**（下面所有 Agent / SDK 真正调用的就是它）

不管哪个客户端，底层请求长这样：

```http
POST http://localhost:11434/v1/chat/completions
Content-Type: application/json
Authorization: Bearer not-needed      # Ollama 不校验 Key，任意非空串即可
```

```json
{
  "model": "qwen3.8-local",
  "messages": [
    {"role": "system", "content": "你是一个本地助手"},
    {"role": "user", "content": "你好"}
  ],
  "stream": false,
  "temperature": 0.7
}
```

多模态（发图片，客户端需开启 supportsImages）：
```json
{
  "model": "qwen3.8-local",
  "messages": [{"role": "user", "content": [
    {"type": "text", "text": "图里写了什么？"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,<BASE64>"}}
  ]}]
}
```

> Qwen3.8 原生支持 `tools`（函数调用）与 `thinking`（推理），按 OpenAI `tool_calls` 规范使用即可，无需额外服务端配置。

最快的自检（确认链路通不通）：
```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-local","messages":[{"role":"user","content":"用一句话介绍自己"}],"stream":false}'
```

### 通用配置原则

所有 OpenAI 兼容客户端三件套：
- **Base URL:** `http://localhost:11434/v1`（OpenAI 兼容协议必须带 `/v1`；若客户端有专门的 "Ollama" 服务商选项，则填 `http://localhost:11434` 不带 `/v1`）
- **API Key:** 任意非空字符串（如 `not-needed` / `ollama`）
- **Model:** `qwen3.8-local`（**必须与 `ollama list` 输出逐字一致，大小写敏感**）

### 1. WorkBuddy

走「自定义模型」条目，**不是 MCP Server**：
- 设置 → 模型（Models）→ 添加自定义模型
- 厂商/Provider：`Ollama`（或 Custom）
- 名称 / ID：`qwen3.8-local`
- Base URL：`http://localhost:11434/v1`
- API Key：任意非空串（如 `not-needed`）
- 开关：☑ 支持图片（supportsImages） ☑ 支持推理（supportsReasoning） ☑ 支持工具调用（supportsToolCall）
- 保存后**彻底退出并重启 WorkBuddy** 才生效（当前 `~/.workbuddy/models.json` 已按此配置）。

### 2. Claude Desktop（cc-switch）

cc-switch 用 Ollama 原生协议，编辑配置文件：
```json
{
  "models": [
    {
      "name": "qwen3.8-local",
      "api": "ollama",
      "base_url": "http://localhost:11434",
      "model": "qwen3.8-local"
    }
  ]
}
```
确认 `model` 与 `ollama list` 一致即可。

### 3. Trae（字节跳动 AI IDE）—— 两种接法二选一

Trae 自定义模型有**两种协议**，差异只在 Base URL 是否带 `/v1`：

**方案 A（推荐，原生 Ollama 协议）：**
设置 → 模型 → 添加模型 → 服务商选 **「Ollama」**
- API 地址：`http://localhost:11434`（**不带 `/v1`**）
- 模型名称：`qwen3.8-local`（与 `ollama list` 完全一致，大小写敏感）
- API Key：任意非空串（如 `ollama`，必填）

**方案 B（OpenAI 兼容协议）：**
服务商选 **「OpenAI」**
- 自定义请求地址：`http://localhost:11434/v1`（**必须带 `/v1`**）
- 模型名称：`qwen3.8-local`
- API Key：任意非空串

踩坑清单（都是真踩过的）：
1. **模型名大小写敏感**，必须和 `ollama list` 输出逐字一致，否则 `404 model not found`。
2. **API Key 不能留空**，填任意非空串（Ollama 不校验）。
3. 用 **`127.0.0.1`** 而不是 `localhost`：开了系统代理（Clash 等）时 `localhost` 可能被拦截，Trae 报 `4054`/连接失败。必要时在 Ollama 侧设 `OLLAMA_ORIGINS=*` 后重启。
4. Trae 有**版本回归 bug**（"昨天能用今天不能用"），多为 Trae 自身更新导致；重开 Trae 或重新添加模型通常可解。
5. 想防长上下文断流/截断：固化一个专用模型 `ollama create qwen3.8-trae -f Modelfile`（Modelfile 里固定 `num_ctx` 等参数），在 Trae 用这个名字。

### 4. Hermes Agent

编辑 `~/.hermes/config.yaml`：
```yaml
models:
  - name: qwen3.8-local
    provider: ollama
    base_url: http://localhost:11434
    model_id: qwen3.8-local
```

### 5. Deepseek Harness

```yaml
ollama:
  base_url: http://localhost:11434
  model: qwen3.8-local
  api_key: not-needed
```

### 6. OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="not-needed"          # 任意非空串
)

response = client.chat.completions.create(
    model="qwen3.8-local",
    messages=[{"role": "user", "content": "你好"}]
)
print(response.choices[0].message.content)
```

### 7. LangChain

```python
from langchain_community.llms import Ollama

llm = Ollama(
    base_url="http://localhost:11434",   # 走 Ollama 原生接口
    model="qwen3.8-local"
)

print(llm.invoke("你好"))
```

---

## 六、一键验证脚本

创建 `~/models/verify-ollama.sh` 用于快速检查服务状态：

```bash
cat > ~/models/verify-ollama.sh << 'SCRIPT'
#!/bin/bash
echo "=== Ollama 本地模型验证 ==="
echo ""

# 1. 检查 Ollama 服务状态
echo "[1] Ollama 服务状态："
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "    ✓ Ollama 正在运行 (http://localhost:11434)"
else
    echo "    ✗ Ollama 未运行，请先启动：open -a Ollama"
    exit 1
fi

# 2. 列出已安装模型
echo ""
echo "[2] 已安装模型："
curl -s http://localhost:11434/api/tags | python3 -m json.tool 2>/dev/null | grep -E '"name"|"size"' || echo "    无模型"

# 3. 测试 API 连通性
echo ""
echo "[3] API 连通性测试："
response=$(curl -s -X POST http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-local","messages":[{"role":"user","content":"你好"}],"stream":false}' \
  --max-time 30)

if echo "$response" | grep -q '"content"'; then
    echo "    ✓ API 响应正常"
    echo "$response" | python3 -c "import sys,json; print('    回复:', json.load(sys.stdin)['choices'][0]['message']['content'][:50]+'...')" 2>/dev/null
else
    echo "    ✗ API 响应异常"
    echo "$response"
fi

# 4. 检查多模态能力
echo ""
echo "[4] 模型详细信息："
ollama show qwen3.8-local 2>/dev/null | grep -E "Capabilities|Projector|Parameters" || echo "    无法获取模型详情"

echo ""
echo "=== 验证完成 ==="
SCRIPT

chmod +x ~/models/verify-ollama.sh
echo "✓ 验证脚本已创建: ~/models/verify-ollama.sh"
```

---

## 七、常见问题排查

### 1. API 连接失败

```bash
# 检查 Ollama 是否运行
curl http://localhost:11434/api/tags

# 重启 Ollama
ollama serve &

# 检查端口
lsof -i :11434
```

### 2. 模型加载慢

- 首次加载需要 30-60 秒（19GB 模型）
- 后续调用会保持加载状态（约 3 分钟）
- 可使用 `ollama ps` 查看当前运行模型

### 3. 内存不足

- 减少上下文长度：`ollama run qwen3.8-local -o num_ctx=2048 "..."`
- 换用更小量化版本：IQ1_S (6GB) 或 Q4 (16GB)

### 4. 网络问题

- HuggingFace 国内可能需要代理
- 可用镜像：`https://hf-mirror.com`
- 下载命令加代理：`curl -x http://127.0.0.1:7897 ...`

### 5. 模型能 `ollama list` 列出、但 chat 报 404 "model not found"

**现象：** `ollama list` / `/api/tags` / `/v1/models` 都能看到模型，但 `ollama run`、`/api/chat`、`/v1/chat/completions` 全部返回 `404 Not Found: model "xxx" not found`。部分请求还会附带 `400 No data iterator found for token: <|video_pad|>`。

**根因：** Ollama 的模型元数据（manifest）还在，但实际的权重 blob（GGUF 文件，约 20GB）被删除了或被损坏。Ollama 能"列"出模型（只读 manifest），却无法真正加载做推理，于是 chat/generate 路由统一报 not found。那个 `<|video_pad|>` 400 是同一损坏状态下的连带症状，权重恢复后不会再出现。

**排查：**
```bash
# 1. 看 manifest 指向的 blob 是否真实存在
ollama show xxx --modelfile          # 记下 FROM 的 sha256-xxx 路径
ls -la ~/.ollama/models/blobs/       # 若没有任何 sha256-* 大文件 → blob 已丢失

# 2. 或直接试 chat（最直观）
curl -s http://localhost:11434/api/chat -d '{"model":"xxx:latest","messages":[{"role":"user","content":"hi"}],"stream":false}'
```

**修复（前提是源 GGUF 还在）：**
```bash
# 移除损坏模型（清掉空 manifest）
ollama rm xxx

# 从源 GGUF 重建（务必保留 ~/models 下的源文件！）
cat > ~/models/Modelfile << 'EOF'
FROM /path/to/your/qwen3.8-27b-Q5.gguf
FROM /path/to/your/mmproj-F16.gguf
PARAMETER num_ctx 131072
EOF
ollama create xxx -f ~/models/Modelfile

# 验证
ollama run xxx "你好"
```

**预防：**
- **切勿删除 `~/models/*.gguf` 源文件**，也别手动清理 `~/.ollama/models/blobs/`（Ollama 的 `ollama rm` 会安全回收）。
- 若 `~/.ollama/models/blobs/` 出现两个相同大小（约 19.77GB）的 `sha256-*` 文件，其中一个是孤儿副本：用 `grep -rl <digest> ~/.ollama/models/manifests/` 确认未被引用后再 `rm -f` 删掉，可回收约 20GB，但**只删未被引用的那个**。

### 6. chat 报 500 "image input is not supported" / 提示需要 mmproj

**现象：** WorkBuddy 等客户端一调用就 `500 image input is not supported - hint: ... provide the mmproj`，错误里常带 `<|video_pad|>` / `<|image_pad|>`。

**根因（重要，曾误判过）：** Qwen3.8-27B **原生就是多模态模型**，但 unsloth 把视觉投影（mmproj）从主 GGUF 里单独抽出来了。只 `ollama create` 主 GGUF（如 `Qwen3.8-27B-UD-Q5_K_M.gguf`）时，模型声明了视觉架构却**缺 mmproj 文件**，Ollama 收不下图片就报这个错。**正确做法不是"剥掉图片"，而是装上 mmproj 让模型真正能看图。**（之前曾误以为它是纯文本模型而去剥图，方向错了。）

**修复（让模型具备视觉）：**
1. 下载同仓库的 mmproj（`unsloth/Qwen3.8-27B-GGUF` 内含 `mmproj-F16.gguf` / `mmproj-BF16.gguf`，约 0.85GB）：
   ```bash
   curl -L -x http://127.0.0.1:7897 -o ~/models/mmproj-F16.gguf \
     "https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/mmproj-F16.gguf"
   ```
2. 在 Modelfile 里用**第二个 `FROM` 行**挂载 mmproj（Ollama 0.33 起 `PROJECTOR` 已移除，必须用 `FROM`；LoRA 才用 `ADAPTER`），重建模型：
   ```text
   FROM /path/to/your/qwen3.8-27b-Q5.gguf
   FROM /path/to/your/mmproj-F16.gguf
   PARAMETER num_ctx 131072
   ```
   ```bash
   ollama rm qwen3.8-local
   ollama create qwen3.8-local -f ~/models/Modelfile
   ```
3. 验证：
   - `ollama show qwen3.8-local` 的 `Capabilities` 应出现 `vision`，并带 `Projector (clip)` 架构（约 460M 参数，即 mmproj 已挂载）。
   - 实测看图（本机 Ollama 0.32 的 `ollama run` **不支持 `--image` 标志**，改用 OpenAI 兼容端点发 base64 图）：
     ```bash
     /usr/bin/python3 - <<'PY'
     import base64, json, urllib.request
     b64 = base64.b64encode(open('<图片路径>','rb').read()).decode()
     p = {"model":"qwen3.8-local","messages":[{"role":"user","content":[
       {"type":"text","text":"图里写了什么文字？简短回答。"},
       {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}}]}],
       "max_tokens":200}
     r = urllib.request.urlopen(urllib.request.Request(
       "http://localhost:11434/v1/chat/completions", data=json.dumps(p).encode(),
       headers={"Content-Type":"application/json"}), timeout=240)
     print(json.loads(r.read())['choices'][0]['message']['content'])
     PY
     ```
     模型若能从图中读出文字/描述内容，即证明视觉链路打通。

**客户端配置（关键）：** 模型已支持视觉，**WorkBuddy 的 `supportsImages` 保持 `true`**，这样 WB 发的截图能真正送进模型被"看到"。`url` 默认指向 Ollama 直连 `http://localhost:11434/v1`（最稳，由 Ollama 自身管理）。若想让超长对话也自动防超时，可改用智能代理 `http://localhost:11435/v1`（见下一节，它默认**放行图片**并做上下文截断），二者都能用好多模态。

### 7. chat 报 400 "exceeds the available context" / WorkBuddy 长对话调用慢或超时

**现象：** `400 ... exceeds the available context size (N tokens)`；或本地 27B 模型在长对话里响应极慢、WorkBuddy 报"自定义模型错误"（客户端等待超时）。

**根因：** WorkBuddy 会把整段对话历史发给本地模型，累计几万 token；在 Metal 上预填充极慢，且旧默认 `num_ctx=32768` 容易被突破。

**修复（已做 + 可选）：**
1. **上下文窗口已调至 131072**（最佳平衡点）。
   ⚠️ 图片实测仅 ~1084 tokens（非 13 万）。400 报错是「图片+长历史」总和超限，需缩短历史或启代理截断。
2. **（可选）智能代理做上下文截断**：`~/models/ollama_strip_proxy.py` 在 Ollama(11434) 前透明转发，**默认放行图片**（模型已支持视觉，图片会送达），并**按 token 估算自动截断**——超过 `--max-prompt-tokens`（默认 24000）时只保留 `system` + 最近若干轮，丢弃最旧历史，避免超时/400。它**同时解决多模态 + 长对话**两个诉求。
   - 手动起：`python3 ~/models/ollama_strip_proxy.py --port 11435 --upstream http://127.0.0.1:11434`
   - 持久化（登录自启 + 崩溃自启）：已提供 plist `~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist`。在**真实 Terminal**（注意：部分沙箱环境的 `launchctl` 不会真正持久化）执行一次：
     ```bash
     launchctl bootout  "gui/$(id -u)/com.user.ollama-strip-proxy" 2>/dev/null
     launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist
     ```
   - 启用代理时，把 WorkBuddy 该模型的 `url` 指向 `http://localhost:11435/v1`；否则保持直连 `http://localhost:11434/v1`。两者都支持多模态。
   - 验证在线：`curl -s -o /dev/null -w "%{http_code}" http://localhost:11435/v1/models` 应返回 `200`；挂了用 `launchctl kickstart -k gui/$(id -u)/com.user.ollama-strip-proxy` 拉起。

**推荐默认：** 直连 `11434`（`supportsImages=true`）即可稳定用好多模态；只有长会话频繁触发 400 时，再启用 `11435` 代理做截断。

**改完配置记得彻底退出并重启 WorkBuddy 才能生效。**

---

## 七、性能参考

> 以下为 Apple M5 Pro / 48GB 统一内存 + Q5_K_M 量化的实测数据，仅供参考。

| 量化版本 | 文件大小 | 内存占用 | 生成速度 | 质量 |
|---------|---------|---------|---------|------|
| IQ2_XXS | 6.77 GB | 11–13 GB | ~12–15 tok/s | 中低 |
| Q3_K_XL | 12.24 GB | 13–16 GB | ~11–13 tok/s | 中 |
| Q4_K_M | 15.33 GB | 17–19 GB | ~10–11 tok/s | 高 |
| Q5_K_M | 18.41 GB | ~28 GB | ~9.7 tok/s | 很高 |
| Q6_K_XL | 23.56 GB | 28–30 GB | ~8–9 tok/s | 高 |
| Q8_K_XL | 29.30 GB | 35–40 GB | ~7–8 tok/s | 最高 |

**实测备注（M5 Pro / 48GB）：**
- Q5_K_M 首次加载约 6s，后续调用保持内存驻留
- 生成速度受 prompt 长度影响，短 prompt 更快
- 上下文 131072 时性能稳定；超过 100K 预填充速度下降
- `OLLAMA_KEEP_ALIVE=30m` 可避免每次重载

---

## 八、Ollama 服务管理

> **注意**：Ollama.app 自带服务管理，双击菜单栏图标即可启动/停止，无需手动脚本。

命令行管理参考：
```bash
# 查看运行状态
ollama ps

# 启动服务（前台运行，终端关闭则停止）
ollama serve

# 停止服务
pkill ollama
```

推荐使用 LaunchAgent 实现开机自启（Ollama.app 安装时已自动配置）。

---

## 九、一键验证脚本

创建 `~/models/verify-ollama.sh` 用于快速检查模型状态：

```bash
#!/bin/bash
echo "=== Ollama 状态检查 ==="
echo ""

# 检查 Ollama 服务
if ! curl -s http://localhost:11434/api/version > /dev/null 2>&1; then
  echo "❌ Ollama 未运行，请先启动 Ollama.app"
  exit 1
fi
echo "✅ Ollama 服务正常"

# 列出模型
echo ""
echo "=== 已安装模型 ==="
ollama list

# 检查 API 连通性
echo ""
echo "=== API 连通性测试 ==="
response=$(curl -s -w "\n%{http_code}" http://localhost:11434/v1/models)
http_code=$(echo "$response" | tail -1)
if [ "$http_code" = "200" ]; then
  echo "✅ API 端点正常: http://localhost:11434/v1"
else
  echo "❌ API 端点异常 (HTTP $http_code)"
fi

# 测试简单推理
echo ""
echo "=== 推理测试 ==="
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-local","messages":[{"role":"user","content":"用一句话介绍自己"}],"stream":false}' \
  | python3 -c "import sys,json; print('✅ 推理正常:', json.load(sys.stdin)['choices'][0]['message']['content'][:50])" 2>/dev/null || echo "⚠️ 推理测试失败，请检查模型名"

echo ""
echo "=== 完成 ==="
```

设置执行权限：
```bash
chmod +x ~/models/verify-ollama.sh
~/models/verify-ollama.sh
```

---

## 总结

1. **下载** → 根据内存选量化版本，同时下载 mmproj（多模态必需）
2. **安装 Ollama** → `brew install ollama`（需 ≥0.32.0 支持多模态）
3. **创建模型** → 编写 Modelfile（替换路径），执行 `ollama create`
4. **验证** → 运行 `~/models/verify-ollama.sh` 检查服务状态
5. **配置 Agent** → 所有工具使用 `http://localhost:11434/v1`（或原生接口不带 `/v1`）

这样你就可以在任何支持 API 的 Agent 工具中使用本地 Qwen3.8 模型了！
