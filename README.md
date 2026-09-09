# 本地 Qwen3.8-27B 部署指南

基于 M5 Pro / 48GB 实测的本地 LLM 部署完整教程。

## 🎯 适用对象

- macOS M系列芯片（M1/M2/M3/M4/M5）
- 内存 ≥ 16GB（推荐 24GB+，最佳 48GB）
- 已有 Python 环境

## 📊 量化版本选择

### 快速决策表

| 你的内存 | 推荐方案 | 文件大小 | 速度 | 质量 |
|---------|---------|---------|------|------|
| 16GB | GGUF Q4_K_M | ~15 GB | ~30 tok/s | 中等 |
| 24-32GB | **MLX 原生版** ⭐ | ~18 GB | **~40 tok/s** | 高 |
| 32-48GB | Q6_K_XL | ~23 GB | ~35 tok/s | 很高 |
| 48GB+ | Q8_K_XL | ~29 GB | ~25 tok/s | 极高 |

### 详细对比

| 量化档位 | 文件大小 | 内存占用 | 相对fp16劣化 | 推荐场景 |
|---------|---------|---------|------------|---------|
| Q3_K_XL | ~12 GB | ~14 GB | - | 16GB内存应急 |
| Q4_K_M | ~15 GB | ~17 GB | +4.0% | 平衡选择 |
| **Q5_K_M** | **~18 GB** | **~20 GB** | **+1.8%** | **推荐甜点** |
| Q6_K_XL | ~23 GB | ~26 GB | +2.5% | 追求质量 |
| Q8_K_XL | ~29 GB | ~33 GB | +0.5% | 极致质量 |
| **MLX nvfp4** | **~18 GB** | **~21 GB** | **+3.2%** | **速度优先** |

### 引擎性能对比（M5 Pro 48GB）

| 指标 | GGUF Q5_K_M + MTP | MLX 原生版 | 差距 |
|------|------------------|-----------|------|
| 代码生成速度 | 22.4 tok/s | **40.8 tok/s** | +82% |
| 开放式写作速度 | 13.9 tok/s | **29.0 tok/s** | +109% |
| 首 token 延迟 | 分钟级（swap时） | **3-4 秒** | 质的飞跃 |
| 内存占用 | ~28 GB | ~21 GB | -25% |

> 💡 **MLX 原生版（qwen3.8:27b-mlx）** 是当前最优选择：速度快约2倍，首字延迟秒级，自动开启MTP投机解码。  
> 如果追求极致质量且内存充足，可选择 **Q8_K_XL**（8位量化，几乎无损）。

详细对比请参考：[性能对比与量化指南.md](./性能对比与量化指南.md)

## 📦 快速开始

### 第一步：检查环境

```bash
# 查看内存
sysctl hw.memsize | awk '{printf "内存: %.0f GB\n", $2/1024/1024/1024}'

# 检测代理
for port in 7890 7897 1087 1080; do
  curl -s -x http://127.0.0.1:$port -o /dev/null -w "%{http_code}" https://huggingface.co | grep -q 200 && echo "代理端口: $port" && break
done
```

### 第二步：选择量化版本

| 内存 | 推荐版本 | 文件大小 | 生成速度 |
|------|---------|---------|---------|
| 16GB | Q3_K_XL / Q4_K_M | 12-16 GB | ~30 tok/s |
| 24GB+ | **Q5_K_M** ⭐ | 18.41 GB | ~40 tok/s |
| 36GB+ | Q6_K_XL | 23.56 GB | ~35 tok/s |
| 48GB+ | Q8_K_XL | 29.30 GB | ~25 tok/s |

### 第三步：安装 Ollama

```bash
# 方式一：Homebrew（推荐）
brew install ollama

# 方式二：直接下载
# https://ollama.com/download
```

### 第四步：下载模型

```bash
# 国内镜像下载（推荐）
export HF_ENDPOINT=https://hf-mirror.com
ollama pull unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q5_K_M

# 或从 HuggingFace 直接下载（需代理）
ollama pull unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q5_K_M
```

### 第五步：创建本地模型

```bash
# 创建自定义模型配置
cat > Modelfile << 'EOF'
FROM qwen3.8:27b-ud-q5_k_m

# 上下文窗口设置
PARAMETER num_ctx 131072

# MTP 投机解码（Qwen3.8 自带加速）
PARAMETER draft_num_predict 3

# 采样参数
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
EOF

ollama create qwen3.8-local -f Modelfile
```

### 第六步：配置全局环境变量

```bash
# macOS 全局配置
sudo launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
sudo launchctl setenv OLLAMA_FLASH_ATTENTION 1
sudo launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
sudo launchctl setenv OLLAMA_KEEP_ALIVE 30m

# 生效配置
sudo launchctl unload /Library/LaunchDaemons/org.ollama.ollama.plist 2>/dev/null || true
sudo launchctl load /Library/LaunchDaemons/org.ollama.ollama.plist 2>/dev/null || true
```

### 第七步：验证安装

```bash
# 运行验证脚本
./verify-ollama.sh
```

### 第八步：使用模型

```bash
# 测试对话
ollama run qwen3.8-local "你好，请用一句话介绍你自己"

# 测试代码生成
ollama run qwen3.8-local "写一个 Python 快速排序算法"

# 测试图片理解（需添加视觉模型）
ollama run qwen3.8-local "描述这张图片的内容" --images image.jpg
```

## 🔗 API 调用

Ollama 提供 OpenAI 兼容的 API：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

response = client.chat.completions.create(
    model="qwen3.8-local",
    messages=[{"role": "user", "content": "你好"}],
    temperature=0.7,
    max_tokens=2000
)

print(response.choices[0].message.content)
```

## 📊 性能数据（M5 Pro / 48GB）

| 指标 | 数值 |
|------|------|
| 代码生成 | ~40.8 tok/s |
| 开放式写作 | ~29.0 tok/s |
| 列表结构化 | ~34.2 tok/s |
| 首 token 延迟 | 3-4 秒 |
| 内存占用 | ~18GB |
| MTP 接受率 | ~0.90 |

## 🔧 常见问题

### Q1: 内存不足怎么办？
降低 `num_ctx` 到 32768 或换用更小的量化版本（Q4_K_M）。

### Q2: 生成速度很慢？
检查是否开启了 Swap，确保模型完全加载到内存。

### Q3: 图片理解报错？
确保使用支持视觉的模型（如 `qwen2.5-vl`），并检查图片格式。

### Q4: 需要联网吗？
不需要。本地模型完全离线运行，无需联网。

## 📚 参考文档

- Ollama 官方文档：https://ollama.com/docs
- Qwen3.8 模型卡片：https://huggingface.co/Qwen/Qwen3.8-27B
- 未适技术 GGUF 量化：https://huggingface.co/unsloth/Qwen3.8-27B-GGUF

## 🙏 致谢

感谢 Qwen 团队开源高质量模型，感谢 unsloth 提供优化的 GGUF 量化版本。
