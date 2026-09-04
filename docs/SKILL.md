---
name: local-llm-setup
description: 在任何 Mac/Linux 电脑上部署本地 Qwen3.8-27B 模型，支持所有通过 API 接入的 Agent 工具（WorkBuddy、Claude Desktop、Trae、Hermes Agent、Deepseek Harness 等）
agent_created: true
---

# 本地 LLM 部署技能

## 概述

本技能指导用户在任何电脑上部署本地大语言模型（以 Qwen3.8-27B 为例），使其可被各种 AI Agent 工具调用。核心流程：下载 GGUF 文件 → 创建 Ollama 模型 → 配置 API。

## 适用场景

- 用户需要本地运行大模型以避免 API 限制/费用
- 用户希望在自己的电脑上运行 Qwen3.8 等大模型
- 需要将本地模型集成到 WorkBuddy、Claude、Trae 等工具

## 部署流程

### 1. 环境检查

```bash
# 查看内存大小（选择量化版本依据）
sysctl hw.memsize | awk '{printf "内存: %.0f GB\n", $2/1024/1024/1024}'

# 自动检测代理端口
for port in 7890 7897 1087 1080; do
  curl -s -x http://127.0.0.1:$port -o /dev/null -w "%{http_code}" https://huggingface.co | grep -q 200 && echo "代理端口: $port" && break
done

# 国内用户可用镜像加速下载
export HF_ENDPOINT=https://hf-mirror.com
```

**版本要求：** 多模态（mmproj 支持）需要 Ollama ≥ 0.32.0

### 2. 选择并下载模型

根据内存选择量化版本：

| 内存 | 推荐版本 | 文件大小 |
|------|---------|---------|
| 8GB | IQ2_XXS | 6.77 GB |
| 16GB | Q3_K_XL 或 Q4_K_M | 12-16 GB |
| 24GB+ | **Q5_K_M** | 18.41 GB |
| 36GB+ | Q6_K_XL | 23.56 GB |
| 48GB+ | Q8_K_XL | 29.30 GB |

> 计算公式：实际内存占用 ≈ 模型文件大小 × 1.2
> 参考实测（M5 Pro / 48GB）：Q5_K_M 生成速度 ~9.7 tok/s，首次加载 ~6s

下载命令：
```bash
mkdir -p ~/models
curl -x http://127.0.0.1:7897 \
  -L "https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-UD-Q5_K_M.gguf" \
  -o ~/models/qwen3.8-27b-Q5.gguf \
  --progress-bar
```

**注意**：HuggingFace 文件名带 `UD-` 前缀！

### 4. 验证下载

```bash
ls -lh ~/models/qwen3.8-27b-Q5.gguf
python3 -c "
import os
path = '/path/to/model.gguf'
size = os.path.getsize(path)
with open(path, 'rb') as f:
    magic = f.read(4)
    print(f'Size: {size/1e9:.2f} GB', '✓ OK' if magic == b'GGUF' else '✗ INVALID')
"
```

### 5. 创建 Ollama 模型（含多模态视觉）

> 前提：`~/models/mmproj-F16.gguf` 已下载（视觉投影，多模态必需）。
> **注意**：Ollama 版本需 ≥ 0.32.0 支持多模态。

```bash
# 创建 Modelfile（主 GGUF + mmproj 投影 + 最佳上下文）
cat > ~/models/Modelfile << 'EOF'
FROM /path/to/your/Qwen3.8-27B-UD-Q5_K_M.gguf
FROM /path/to/your/mmproj-F16.gguf
PARAMETER num_ctx 131072
EOF

# 创建模型
ollama create qwen3.8-local -f ~/models/Modelfile

# 验证：Capabilities 应含 vision / tools / thinking，且 Projector 显示 clip
ollama show qwen3.8-local
ollama run qwen3.8-local "你好"
```

**第二个 `FROM` 行**才是挂视觉投影的正确写法（`PROJECTOR` 在 Ollama 0.33 已移除；LoRA 才用 `ADAPTER`）。

### 6. 配置 Agent 工具

所有支持 OpenAI 兼容 API 的工具使用相同配置：

```yaml
base_url: http://localhost:11434/v1   # 客户端有原生 Ollama 选项时填 http://localhost:11434（不带 /v1）
api_key: not-needed                   # 任意非空串，Ollama 不校验
model: qwen3.8-local                  # 必须与 `ollama list` 逐字一致（大小写敏感）
```

模型已具备 `vision` / `tools` / `thinking`，客户端按需开启图片/工具/推理开关。

- 各 Agent 的逐项配置（WorkBuddy、Claude Desktop、Trae、Hermes、Deepseek Harness 等）见 `references/guide.md` 第五节。
- OpenAI Chat Completions 请求格式（端点、多模态 `image_url`、工具调用）见 `references/api_reference.md`。

### 7. 验证状态

```bash
# 运行一键验证脚本
~/models/verify-ollama.sh
```

该脚本会检查 Ollama 服务、模型列表、API 连通性和推理能力。

|- 加载时间: ~6s（首次，M5 Pro / 48GB）
- 生成速度: ~9.7 tok/s（M5 Pro / 48GB + Q5_K_M + num_ctx=131072）
- 上下文: 131072 tokens（实测最佳平衡，非原生上限 262144）

## 常见问题

1. **API 连接失败**: `curl http://localhost:11434/api/tags` 检查服务状态
2. **内存不足**: 换用更小量化版本或减少上下文长度
3. **下载中断**: 使用 Python urllib 而非 curl 下载大文件

## 资源

- 完整指南: `references/guide.md`
