# 本地 Qwen3.8-27B 部署指南

基于 M5 Pro / 48GB 实测的本地 LLM 部署完整教程。

> ✅ **最后验证：2026-09-11** · Ollama 0.33.3 · macOS 26（M5 Pro / 48GB 实测）
> 适用版本：**Ollama ≥ 0.30**。更早版本存在 MLX 大上下文超时 bug（[问题 2](./TROUBLESHOOTING.md#2-mlx-超时-500-context-canceled)），动手前先确认版本。

## 🎯 适用对象

- macOS M系列芯片（M1/M2/M3/M4/M5）
- 内存 ≥ 16GB（24GB 可跑，32GB 起流畅，48GB 为本文完整实测环境）
- 已有 Python 环境

## 🚫 这份指南不适合谁

- **非 Apple Silicon**（Intel Mac / Windows / Linux）：MLX 路线和本文所有实测数据都不适用，建议直接用模型 API 或云 GPU
- **内存 < 16GB**：27B 模型跑不动，建议换更小的模型规格或直接用 API
- **生产级多用户并发**：Ollama 定位单机自用，高并发场景建议 vLLM 等推理框架

## 📊 量化版本选择

### 快速决策表

| 你的内存 | 推荐方案 | 文件大小 | 速度* | 质量 |
|---------|---------|---------|------|------|
| 16GB | GGUF Q3_K_XL（应急） | ~12 GB | 较慢 | 中等 |
| 24GB | GGUF Q4_K_M / Q5_K_M | 15-18 GB | ~22-30 tok/s | 中-高 |
| **32GB+** | **MLX 原生版** ⭐ | ~18 GB | **~40 tok/s** | 高 |
| 48GB+ | Q8_K_XL（极致质量）或 MLX | ~29 GB | ~25 tok/s | 极高 |

> \* 速度均为 **M5 Pro / 48GB 实测值**，各代芯片内存带宽不同，请勿直接套用。24GB 内存跑 MLX 时权重 + KV 缓存余量极小，需下调 `num_ctx` 否则触发 swap——**32GB 起步才能获得上表体验，48GB 是本文完整实测环境**。

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

> 💡 **MLX 原生版（qwen3.8:27b-mlx）** 是当前最优选择：速度快约2倍，首字延迟秒级。MTP 投机解码须手动开启（draft_num_predict 3），GGUF 与 MLX 通用，非 MLX 独占。  
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

| 内存 | 推荐版本 | 文件大小 | 生成速度（M5 Pro 实测） |
|------|---------|---------|---------|
| 16GB | Q3_K_XL / Q4_K_M | 12-16 GB | 未实测（低于 Q5 档） |
| 24GB+ | **Q5_K_M** ⭐ | 18.41 GB | ~22 tok/s |
| 36GB+ | Q6_K_XL | 23.56 GB | 未实测 |
| 48GB+ | Q8_K_XL | 29.30 GB | 未实测 |

### 第三步：安装 Ollama

```bash
# 方式一：Homebrew（推荐）
brew install ollama

# 方式二：直接下载
# https://ollama.com/download
```

### 第四步：下载模型

```bash
# 方案一（推荐）：MLX 原生版，速度快、自带视觉
export HF_ENDPOINT=https://hf-mirror.com   # 国内镜像，可不设
ollama pull qwen3.8:27b-mlx

# 方案二（并发/长 agent 备选）：GGUF Q5_K_M，llama.cpp 并发更稳
# ollama pull unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q5_K_M
```

### 第五步：创建本地模型

```bash
# 创建自定义模型配置
cat > Modelfile << 'EOF'
FROM qwen3.8:27b-mlx

# 上下文窗口设置
PARAMETER num_ctx 131072

# MTP 投机解码（Qwen3.8 自带加速）
PARAMETER draft_num_predict 3

# 采样参数
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
EOF

ollama create qwen3.8:27b-mlx -f Modelfile
```

### 第六步：配置全局环境变量

```bash
# macOS 用户级全局配置（Ollama 以用户 LaunchAgent 运行，无需 sudo）
launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_KEEP_ALIVE 30m

# 生效配置：重启 Ollama 使环境变量生效
pkill -f "ollama serve" && sleep 2 && open -a Ollama
```

### 第七步：验证安装

```bash
# 运行验证脚本
./verify-ollama.sh
```

### 第八步：使用模型

```bash
# 测试对话
ollama run qwen3.8:27b-mlx "你好，请用一句话介绍你自己"

# 测试代码生成
ollama run qwen3.8:27b-mlx "写一个 Python 快速排序算法"

# 测试图片理解（需添加视觉模型）
ollama run qwen3.8:27b-mlx "描述这张图片的内容" --images image.jpg
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
    model="qwen3.8:27b-mlx",
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
| MTP 接受率 | 约 0.6–0.85（runner 日志实测）|

> 以上均为 M5 Pro 实测。M1–M4 各代芯片内存带宽差异大，请勿直接套用，以自身硬件实测为准。

## 🔧 常见问题

> 按现象索引的完整排查手册（9 个常见问题 + 根因 + 修复命令）见 **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)**，以下为高频简答。

### Q1: 内存不足怎么办？
优先保持 `num_ctx 131072`（单跑稳定）；内存吃紧时下调到 65536，仍不足再换更小量化（Q4_K_M）。

### Q2: 生成速度很慢？
检查是否开启了 Swap，确保模型完全加载到内存。

### Q3: 图片理解报错？
MLX 原生版 `qwen3.8:27b-mlx` 自带视觉投影，直接发图即可，无需额外视觉模型。GGUF 路线需在 Modelfile 写入 Qwen 多模态模板（见弯路3）。

### Q4: 需要联网吗？
不需要。本地模型完全离线运行，无需联网。

### Q5: MLX 跑 128K 上下文会爆显存吗？
单跑不会。2026-09-10 的 A/B 实测中，MLX 在 131072 上下文 + MTP 下 5 维题 2 轮 **10/10 全过、零 OOM**。之前偶发的「间歇性显存溢出」，根因是**多个会话/进程同时调同一个 MLX 模型**，KV 缓存显存叠加——不是 128K 上下文太大。

- 日常单跑 / 短中交互：直接用 `qwen3.8:27b-mlx`（MLX，满血 131k + MTP），最快最稳。
- 长 agent 多会话并发：改用 `qwen3.8-q5`（GGUF + llama.cpp，并发更稳）。
- 别让 Hermes 与 WorkBuddy 同时并发调 MLX，错峰即可。

## 📚 参考文档

- Ollama 官方文档：https://ollama.com/docs
- Qwen3.8 模型卡片：https://huggingface.co/Qwen/Qwen3.8-27B
- 未适技术 GGUF 量化：https://huggingface.co/unsloth/Qwen3.8-27B-GGUF

## 🙏 致谢

感谢 Qwen 团队开源高质量模型，感谢 unsloth 提供优化的 GGUF 量化版本。

## 📖 配套文章

踩坑过程与选型思路的完整叙述（含三个弯路的根因复盘）：[本地部署 Qwen3.8 全记录：从翻车到跑通](https://mp.weixin.qq.com/s/wHhXbaBLZrVHKdlGKb8mUw)

> 欢迎提交 Issue / PR，补充其他硬件（M1–M4、不同内存档位）的实测数据，一起完善硬件对照表。
