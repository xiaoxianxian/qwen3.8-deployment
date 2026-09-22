# Mac 本地部署 Qwen3.8-27B 完整指南（Apple Silicon / Ollama）

面向 macOS Apple Silicon 用户的本地大模型部署教程：基于 M5 Pro / 48GB 实测，覆盖 Ollama + MLX 与 GGUF 量化方案对比、MTP 投机解码加速、国内镜像下载与完整避坑。

> **最后验证：2026-09-15** · Ollama 0.33.3 · macOS 26（M5 Pro / 48GB 实测）
> 适用版本：**Ollama ≥ 0.30**。更早版本存在 MLX 大上下文超时 bug（[问题 2](./TROUBLESHOOTING.md#2-mlx-超时-500-context-canceled)），动手前先确认版本。

## 适用对象

- macOS M系列芯片（M1/M2/M3/M4/M5）
- 内存 ≥ 16GB（24GB 可跑，32GB 起流畅，48GB 为本文完整实测环境）
- 已有 Python 环境

## 这份指南不适合谁

- **非 Apple Silicon**（Intel Mac / Windows / Linux）：MLX 路线和本文所有实测数据都不适用，建议直接用模型 API 或云 GPU
- **内存 < 16GB**：27B 模型跑不动，建议换更小的模型规格或直接用 API
- **生产级多用户并发**：Ollama 定位单机自用，高并发场景建议 vLLM 等推理框架（本方案不包含 vLLM 的下载和配置，全部配置都基于 Ollama）

## 量化版本选择

### 快速决策表

| 你的内存 | 推荐方案 | 文件大小 | 速度* | 质量 |
|---------|---------|---------|------|------|
| 16GB | GGUF Q3_K_XL（应急） | ~12 GB | 较慢 | 中等 |
| 16-24GB | GSQ-RCO IQ3_S（省显存均衡） | ~12 GB | ~12.6 tok/s | 基本无损 |
| 24GB | GGUF Q4_K_M / Q5_K_M | 15-18 GB | ~22-30 tok/s | 中-高 |
| **32GB+** | **MLX 原生版**（推荐） | ~18 GB | **~40 tok/s** | 高 |
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
| GSQ IQ3_S | ~12 GB | ~13 GB | 基本无损 | 省内存均衡（见下） |
| GSQ IQ3_XXS | ~10 GB | ~11 GB | GPQA ~-1 分 | 极致省显存 |

### 四模型性能总表（M5 Pro 48GB，num_ctx=131072）

| 模型 | 量化 | 体积 | 早期短基准·代码生成¹ | 严格 12 题·平均 decode² | 12 题质量 | 内存占用 |
|------|------|------|--------------------|------------------------|----------|---------|
| **MLX 4-bit** | NVFP4 | 18 GB | 40.8 tok/s | **29.9 tok/s** | 12/12 全对 | ~21 GB |
| **Q5_K_M** | GGUF 5.6bpw | 20 GB | 22.4 tok/s | 14.9 tok/s | 12/12 全对 | ~20 GB |
| **GSQ IQ3_S** | 3.5bpw 混合 | 12 GB | 16.2 tok/s | 12.6 tok/s | 12/12 全对 | ~12 GB |
| **GSQ IQ3_XXS** | 3.0bpw 混合 | 10 GB | — | 12.5 tok/s | 12/12 全对 | ~10 GB |

¹ 早期短基准：短上下文、未统一温度、不含 MTP 叠加效应，单任务峰值速度（MLX 早期分项：写作 29.0 / 结构化 34.2 tok/s）。
² 严格 12 题 A/B：temperature=0、12 题统一对照、四模型均开 MTP、串行跑完即卸载，更可控。两种测法口径不同，倍数不能直接相除，仅作量级参考。
补充：首 token 延迟均 3-4 秒（常驻）；图片理解 MLX ~17s / Q5 ~24s（GGUF 需挂 mmproj）。

> **MLX 原生版（qwen3.8:27b-mlx）** 是当前最优选择：速度快约 2 倍，首字延迟秒级。MTP 投机解码须手动开启（draft_num_predict 3），GGUF 与 MLX 通用，非 MLX 独占。  
> 如果追求极致质量且内存充足，可选择 **Q8_K_XL**（8 位量化，几乎无损）。

详细对比请参考：[性能对比与量化指南.md](./性能对比与量化指南.md)

## 快速开始

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
| **24GB+** | **MLX nvfp4（MLX 原生版）**（推荐） | 18 GB | ~29.9 tok/s（12题A/B）/ ~40 tok/s（短基准） |
| 24GB+ | **Q5_K_M** | 18-20 GB | ~14.9 tok/s（12题A/B） |
| 24GB+ | GSQ IQ3_S | 12 GB | ~12.6 tok/s |
| 24GB+ | GSQ IQ3_XXS | 10 GB | ~12.5 tok/s |
| 36GB+ | Q6_K_XL | 23.56 GB | 未实测 |
| 48GB+ | Q8_K_XL | 29.30 GB | 未实测 |

> 速度列优先采用 2026-09-15 同条件 A/B（`temperature=0`、12 题）数据；MLX nvfp4 在短上下文基准下冲到 ~40 tok/s。IQ 系列为 ISTA-DASLab **GSQ-RCO** 混合精度量化，省显存、质量基本无损（IQ3_XXS 在大规模知识基准上有 ~1 分边际退化）。MLX nvfp4 与 GGUF Q5_K_M 均需在 Modelfile 写 `draft_num_predict 3` 开启 MTP 才达上表速度。

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

**nvfp4**：一种 4-bit 浮点量化格式，把 27B 权重从 50 多 GB 压到 18GB 出头，精度损失克制，是 MLX 版又小又快的基础。

**网络慢或 HuggingFace 访问不了，改用国内镜像：**

```bash
# 镜像 A：走 hf-mirror.com
export HF_ENDPOINT=https://hf-mirror.com
ollama pull qwen3.8:27b-mlx

# 镜像 B：ModelScope（魔搭社区）
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3.8-27B', cache_dir='./models')"
# 再用仓库内 Modelfile 创建本地模型（见第五步）
```

**更省显存（≥16GB）：GSQ-RCO IQ3_S / IQ3_XXS**

```bash
pip install -U "huggingface_hub[cli]"
hf download ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF \
  Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf mmproj-Qwen3.8-27B-BF16.gguf --local-dir .
# 用第五步的 Modelfile 创建（FROM 换成本地 .gguf 路径）
```

GSQ-RCO 是 ISTA-DASLab 的学习式混合精度量化：IQ3_S 把 27B 压到 ~12GB 且质量基本无损（GPQA 仅差 0.5 分），比 Q4_K_M 更小更稳；IQ3_XXS（~10GB）更省，但知识题有 ~1 分边际风险。MLX 原生版速度约为 GSQ 混合精度的 2.4 倍；同机还要跑 MiniMax H3 等视频模型、显存吃紧时，GSQ IQ3_S 是省显存均衡首选。

### 第五步：创建本地模型

MLX 原生版 `ollama pull` 后即为可用模型；GGUF（Q5 / GSQ IQ3）路线需显式写 Modelfile，挂上**多模态模板**与 **MTP 投机解码**——否则发图报错、且浪费模型自带的加速。

**MLX 原生版（FROM 官方标签）：**

```dockerfile
FROM qwen3.8:27b-mlx
PARAMETER num_ctx 131072
PARAMETER draft_num_predict 3     # MTP 投机解码（Qwen3.8 自带加速）
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
```

**GGUF Q5_K_M（FROM Ollama 标签，需补多模态模板 + MTP + 视觉投影）：**

```dockerfile
FROM unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q5_K_M
FROM ./mmproj-F16.gguf            # 视觉投影（多模态必需，需单独下载）
TEMPLATE """{{- if .System }}<|system|>
{{ .System }}
<|end|>
{{ end }}
{{- range .Messages }}
{{- if eq .Role "user" }}<|user|>
{{ .Content }}
<|end|>
{{ else if eq .Role "assistant" }}<|assistant|>
{{ if .Content }}{{ .Content }}{{ end }}{{ if .ReasoningContent }}<|reserved_special_token_145|>{{ .ReasoningContent }}<|end|>
{{ end }}
<|end|>
{{ end }}
{{- end }}
<|assistant|>
{{ if .ReasoningContent }}<|reserved_special_token_145|>{{ .ReasoningContent }}<|end|>
{{ end }}{{ .Response }}"""
PARAMETER num_ctx 131072
PARAMETER draft_num_predict 3
```

**GSQ-RCO IQ3_S / IQ3_XXS（FROM 本地 GGUF，结构同上，仅换 FROM 与 mmproj）：**

```dockerfile
FROM ./Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf   # 换成 IQ3_XXS 用同名 -IQ3_XXS- 文件
FROM ./mmproj-Qwen3.8-27B-BF16.gguf
TEMPLATE """（与上方 GGUF Q5 完全一致的多模态模板）"""
PARAMETER num_ctx 131072
PARAMETER draft_num_predict 3
```

```bash
# GGUF / GSQ 路线创建模型
ollama create qwen3.8-q5 -f Modelfile.q5
ollama create qwen3.8-gsq-iq3s -f Modelfile.gsq
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

**每个变量的作用：**

| 变量 | 作用 | 不设置的后果 |
|------|------|-------------|
| `OLLAMA_CONTEXT_LENGTH=131072` | 全局默认 128K 上下文 | 模型退回 4096 默认值，长文档被静默截断 |
| `OLLAMA_FLASH_ATTENTION=1` | 长上下文推理提速 30–50% | 速度慢 |
| `OLLAMA_KV_CACHE_TYPE=q8_0` | KV 缓存量化，内存占用减半 | 内存占用高，可能触发 swap |
| `OLLAMA_KEEP_ALIVE=30m` | 模型驻留内存 30 分钟 | 每次调用等约 6 秒冷启动 |

> KV 缓存：模型生成时为「已处理过的文字」记录的临时存储，上下文越长占用越大。q8_0 把这块也压缩一档，省显存且精度几乎无损。

> `launchctl setenv` 在重启 Mac 后会失效，重启后重跑一遍即可；想一劳永逸，把变量写进 Ollama 的 LaunchAgent plist。

### 第七步：验证安装

```bash
# 查看模型信息
ollama show qwen3.8:27b-mlx

# 确认上下文长度已生效（应输出 131072，不是 4096）
ollama show qwen3.8:27b-mlx | grep num_ctx

# 测试对话
ollama run qwen3.8:27b-mlx "你好，简单介绍一下你自己"
```

也可以用仓库内的自动化脚本一次性跑完上述检查：

```bash
./verify-ollama.sh
```

**测试图片理解（MLX 自带视觉；GGUF / GSQ 需 Modelfile 已挂 mmproj）：**

```bash
ollama run qwen3.8:27b-mlx "描述这张图片的内容" --images image.jpg
```

如需直接调用 `/v1` 接口验证（base64 编码图片）：

```bash
python3 -c "
import base64, json, urllib.request
b64 = base64.b64encode(open('/path/to/image.png','rb').read()).decode()
p = {'model':'qwen3.8:27b-mlx','messages':[{'role':'user','content':[
  {'type':'text','text':'描述这张图。'},
  {'type':'image_url','image_url':{'url':f'data:image/png;base64,{b64}'}}
]}], 'max_tokens':4000, 'stream':False}
r = urllib.request.urlopen(urllib.request.Request(
  'http://127.0.0.1:11434/v1/chat/completions', data=json.dumps(p).encode(),
  headers={'Content-Type':'application/json'}), timeout=300)
print(json.loads(r.read())['choices'][0]['message']['content'])
"
```

### 第八步：使用模型

> 下面以 MLX 原生版为例；若你选了 GGUF Q5 或 GSQ IQ3，把模型名换成 `qwen3.8-q5` / `qwen3.8-gsq-iq3s` 即可。

```bash
# 测试对话
ollama run qwen3.8:27b-mlx "你好，请用一句话介绍你自己"

# 测试代码生成
ollama run qwen3.8:27b-mlx "写一个 Python 快速排序算法"

# 测试图片理解（MLX 自带视觉；GGUF/GSQ 需 Modelfile 已挂 mmproj）
ollama run qwen3.8:27b-mlx "描述这张图片的内容" --images image.jpg
```

## API 调用

Ollama 提供 OpenAI 兼容的 API：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

response = client.chat.completions.create(
    model="qwen3.8:27b-mlx",  # 换成 qwen3.8-q5 / qwen3.8-gsq-iq3s 等你创建的模型名
    messages=[{"role": "user", "content": "你好"}],
    temperature=0.7,
    max_tokens=2000
)

print(response.choices[0].message.content)
```

## 性能数据与实测说明

完整速度、体积与质量对比见上方「四模型性能总表」。严格 12 题 A/B 的原始数据、逐题校验与硬件对照见 [A_B实测对比报告.md](./A_B实测对比报告.md)。

- MTP 接受率：约 0.6–0.85（runner 日志实测）
- 各代 Apple 芯片内存带宽差异大，以上均为 M5 Pro 实测，请勿直接套用，以自身硬件实测为准。

## GSQ-RCO 极致量化 A/B 实测（2026-09-15）

ISTA-DASLab 的 **GSQ-RCO** 把 Qwen3.8-27B 压到 IQ3_S（≈12 GB）/ IQ3_XXS（≈10 GB）且基本无损。我们在本机（M5 Pro / 48GB / Ollama 0.33.3）跑了 **4 模型严格对照**：`temperature=0`、统一 12 道题（agentic coding / 数学 / 知识 GPQA / 长上下文 / 严格 JSON / 中文写作），逐模型串行、跑完即卸载避免显存叠加。

| 模型 | 量化 | 体积 | 平均 decode | 质量（12 题严格校验） |
|------|------|------|-------------|----------------------|
| **MLX 4-bit**（现状） | NVFP4 均匀 4.0bpw | 18 GB | **29.9 tok/s** | 12/12 全对 |
| Q5_K_M | GGUF 5.6bpw 均匀 | 20 GB | 14.9 tok/s | 12/12 全对 |
| GSQ IQ3_S | 3.5bpw 混合 | 12 GB | 12.6 tok/s | 12/12 全对 |
| GSQ IQ3_XXS | 3.0bpw 混合 | 10 GB | 12.5 tok/s | 12/12 全对 |

> 注：上方「性能数据」里的 ~40.8 tok/s 是早期不同测法（短上下文/不同提示）的结果；本表为 temperature=0、12 题统一对照，更可控。两表都来自本机实测。

**三个维度的结论：**
- **更省内存**：IQ3_S 比 MLX 4-bit 省 6 GB，IQ3_XXS 省 8 GB——直接给 131K 上下文或同机 H3 视频模型腾地方。
- **更快**：你的 MLX 4-bit 约 **2.4×** 于 GSQ 混合精度。原因：NVFP4 是 GPU 友好的均匀 4-bit，IQ/GSQ 混合精度每个权重解量化开销大，在 Apple Silicon 的 Metal 后端 decode（memory-bound）反而更慢。
- **质量无损（vs 你的 MLX）**：小样本 12 题四档全对（JSON 严格可解析、数学最终答案一致、知识题选项一致）。DASLab 在 198 题 GPQA 上测得 IQ3_XXS 相对 BF16 差 ~1 分，需大题集才复现。

**选型建议（48GB Mac，主用 agentic coding + 长推理）：**
- 速度优先 → 保持 **MLX 4-bit**（现状）
- 均衡（推荐切换）→ **GSQ IQ3_S**：省 6 GB、质量不降
- 极致省显存 → **GSQ IQ3_XXS**（接受知识题 ~1 分边际风险）
- 并发安全网 → **Q5** 维持

完整数据见 [A_B实测对比报告.md](./A_B实测对比报告.md) 与 [性能对比与量化指南.md](./性能对比与量化指南.md)。

## 常见问题

> 按现象索引的完整排查手册（9 个常见问题 + 根因 + 修复命令）见 **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)**，以下为高频简答。

### Q1: 内存不足怎么办？
优先保持 `num_ctx 131072`（单跑稳定）；内存吃紧时下调到 65536，仍不足再换更小量化（Q4_K_M）。

### Q2: 生成速度很慢？
检查是否开启了 Swap，确保模型完全加载到内存。

### Q3: 图片理解报错？
MLX 原生版 `qwen3.8:27b-mlx` 自带视觉投影，直接发图即可，无需额外视觉模型。GGUF / GSQ 路线（Q5、GSQ IQ3 等）同属 GGUF 格式，需在 Modelfile 写入 Qwen 多模态模板并挂 mmproj（见弯路3）。

### Q4: 需要联网吗？
不需要。本地模型完全离线运行，无需联网。

### Q5: MLX 跑 128K 上下文会爆显存吗？
单跑不会。2026-09-10 的 A/B 实测中，MLX 在 131072 上下文 + MTP 下 5 维题 2 轮 **10/10 全过、零 OOM**；GSQ / GGUF 路线（Q5、IQ3 等）同属 llama.cpp 引擎，单跑 131K 上下文同样稳定。之前偶发的「间歇性显存溢出」，根因是**多个会话/进程同时调同一个 MLX 模型**，KV 缓存显存叠加——不是 128K 上下文太大。

- 日常单跑 / 短中交互：直接用 `qwen3.8:27b-mlx`（MLX，满血 131k + MTP），最快最稳。
- 长 agent 多会话并发：改用 `qwen3.8-q5`（GGUF + llama.cpp，并发更稳）；GSQ IQ3 同为 llama.cpp 路径，并发表现与 Q5 一致，但体积更小、速度更慢。
- 别让 Hermes 与 WorkBuddy 同时并发调 MLX，错峰即可。

## 参考文档

- Ollama 官方文档：https://ollama.com/docs
- Qwen3.8 模型卡片：https://huggingface.co/Qwen/Qwen3.8-27B
- 未适技术 GGUF 量化：https://huggingface.co/unsloth/Qwen3.8-27B-GGUF

## 致谢

感谢 Qwen 团队开源高质量模型；感谢 unsloth 提供优化的 GGUF 量化版本；特别感谢 ISTA-DASLab 的 **GSQ-RCO** 学习式混合精度量化，让 27B 模型在 ~12GB 显存下保持基本无损，是本文「省显存均衡」方案的基础。

## 配套文章

完整踩坑过程与选型思路叙述（含三个弯路的根因复盘），仓库内提供两种格式：
- 图文版（HTML）：[本地部署 Qwen3.8 全记录：从翻车到跑通](./公众号文章-本地部署Qwen3.8.html)
- Markdown 版：[本地部署 Qwen3.8 全记录：从翻车到跑通](./公众号文章-本地部署Qwen3.8.md)

> 欢迎提交 Issue / PR，补充其他硬件（M1–M4、不同内存档位）的实测数据，一起完善硬件对照表。

---

## 联系作者

- 微信公众号：**Jason 的落地思考**
- 稀土掘金：[Jason的落地思考](https://juejin.cn/user/1574156379368311)
