---
permalink: /guide/
title: 完整部署方案
---

# Mac 本地部署 Qwen3.8-27B 完整指南（Apple Silicon / Ollama）

面向 macOS Apple Silicon 用户的本地大模型部署教程：基于 M5 Pro / 48GB 实测，覆盖 Ollama + MLX 与 GGUF 量化方案对比、MTP 投机解码加速、国内镜像下载与完整避坑。

> **最后验证：2026-11-02** · Ollama 0.40.13 · macOS 27.2（M5 Pro / 48GB 实测）
> 适用版本：**Ollama ≥ 0.30**。更早版本存在 MLX 大上下文超时 bug（[问题 2](./TROUBLESHOOTING.md#2-mlx-超时-500-context-canceled)），动手前先确认版本。
>
> **0.40 起有三处行为变化，照更早的教程抄会踩坑**（2026-11-02 实测）：
> ① 上下文长度的**真正开关是 Ollama.app 的设置**（`db.sqlite` 里的 `settings.context_length`），优先级**高于** Modelfile 的 `num_ctx`——改 Modelfile 不生效是常态；
> ② MLX 路线**不要再手写 `draft_num_predict`**，0.40 已自适应投机解码，手动指定反而从 34.9 掉到 28.0 tok/s（[问题 5](./TROUBLESHOOTING.md#5-mtp-投机解码gguf-手动开--mlx-040-已自适应)）；
> ③ 本机 48 GB **实测 262144 稳定**（MLX KV 动态分配，idle ~18–31GB，不预占满窗）；早前"262144 必然 evict"是对争用日志的误读，已作废。日常把单轮输入压在 ~1 万 token 以内最稳。

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

### 四模型性能总表（M5 Pro 48GB，测量口径 num_ctx=131072）

| 模型 | 量化 | 体积 | 早期短基准·代码生成¹ | 严格 12 题·平均 decode² | 12 题质量 | 内存占用 |
|------|------|------|--------------------|------------------------|----------|---------|
| **MLX 4-bit** | NVFP4 | 18 GB | 40.8 tok/s | **29.9 tok/s** | 12/12 全对 | ~21 GB |
| **Q5_K_M** | GGUF 5.6bpw | 20 GB | 22.4 tok/s | 14.9 tok/s | 12/12 全对 | ~20 GB |
| **GSQ IQ3_S** | 3.5bpw 混合 | 12 GB | 16.2 tok/s | 12.6 tok/s | 12/12 全对 | ~12 GB |
| **GSQ IQ3_XXS** | 3.0bpw 混合 | 10 GB | — | 12.5 tok/s | 12/12 全对 | ~10 GB |

¹ 早期短基准：短上下文、未统一温度、不含 MTP 叠加效应，单任务峰值速度（MLX 早期分项：写作 29.0 / 结构化 34.2 tok/s）。
² 严格 12 题 A/B：temperature=0、12 题统一对照、四模型均开 MTP、串行跑完即卸载，更可控。两种测法口径不同，倍数不能直接相除，仅作量级参考。
补充：首 token 延迟均 3-4 秒（常驻）；图片理解 MLX ~17s / Q5 ~24s（GGUF 需挂 mmproj）。

> **MLX 原生版（qwen3.8:27b-mlx）** 是当前最优选择：速度快约 2 倍，首字延迟秒级。**0.40 起 MLX 路线不必手动开 MTP**（runner 已自适应，手写 `draft_num_predict 3` 反而更慢）；只有 GGUF 路线仍需手动设。  
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
PARAMETER num_ctx 262144           # 本机 48GB 实测稳定（MLX KV 动态分配）；GUI 设置会覆盖
# 不要加 draft_num_predict：0.40+ 的 MLX runner 已自适应投机解码，手写反而更慢
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
```

> ⚠️ `num_ctx` 写在这里只是「模型默认值」，**Ollama.app 设置里的上下文长度会覆盖它**。以 `ollama ps` 的 `CONTEXT` 列为准。

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
PARAMETER num_ctx 262144
PARAMETER draft_num_predict 3
```

**GSQ-RCO IQ3_S / IQ3_XXS（FROM 本地 GGUF，结构同上，仅换 FROM 与 mmproj）：**

```dockerfile
FROM ./Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf   # 换成 IQ3_XXS 用同名 -IQ3_XXS- 文件
FROM ./mmproj-Qwen3.8-27B-BF16.gguf
TEMPLATE """（与上方 GGUF Q5 完全一致的多模态模板）"""
PARAMETER num_ctx 262144
PARAMETER draft_num_predict 3
```

```bash
# GGUF / GSQ 路线创建模型
ollama create qwen3.8-q5 -f Modelfile.q5
ollama create qwen3.8-gsq-iq3s -f Modelfile.gsq
```

### 第六步：设置上下文长度（0.40 起别再用环境变量）

**先认清谁说了算**——这一步 90% 的人会做错：

| 设置位置 | 优先级 |
|---|---|
| **Ollama.app「设置」→ `db.sqlite` 的 `settings.context_length`** | **最高，会覆盖下面两项** |
| Modelfile / 请求体 `num_ctx` | 次之 |
| `OLLAMA_CONTEXT_LENGTH` 环境变量 | 再次（`launchctl setenv` 重启即丢） |

```bash
# 1. 先查 GUI 里实际是多少
sqlite3 "file:$HOME/Library/Application Support/Ollama/db.sqlite?mode=ro" \
  "select context_length from settings;"

# 2. 改它必须先「完全退出」Ollama.app（只 pkill serve 不够，GUI 会写回旧值）
osascript -e 'quit app "Ollama"'
sqlite3 "$HOME/Library/Application Support/Ollama/db.sqlite" \
  "update settings set context_length=32768 where id=1;"

# 3. 重启并校验（CONTEXT 列才是实际生效值）
open -a Ollama && sleep 10 && ollama ps
```

**按内存选值（仅作无 agent 的长对话参考）**：48 GB → **32768**；32 GB → 16384；≥64 GB 才考虑 131072。**但凡接 agent（Hermes / Claude Desktop / Cursor / Codex 等带工具调用的客户端），64K 在真实长会话下仍会溢出截断，直接开到模型上限 262144**（本机实测 65536 不够、262144 才稳定）。**"262144 必然 evict" 是早前对争用日志的误读，单模型实跑正常。**

> **接 agent 客户端必须开到最大 262144（不是 65536）。** Hermes Agent 把 64K 做成硬门槛（`MINIMUM_CONTEXT_LENGTH = 64_000`），低于它就拒绝启动，报 `below the minimum 64,000 required by Hermes Agent`——所以 32768 不可用。但 64K 只是"能启动"的下限，**真实 agent 长会话（工具输出 + 多轮历史）会突破 64K 被静默截断、工具调用崩**，本机实测 65536 仍不够、开到模型上限 262144 才稳定。这类客户端要同步改两处：`model.context_length` + `model.ollama_num_ctx`（都取 262144）。注意 **`/v1` 端点会忽略请求里的 `num_ctx`**，所以客户端改完服务端窗口仍是旧的——两边都得改。完整排查见 `TROUBLESHOOTING.md` §12。

> 为什么不是越大越好：窗口是**容量**旋钮，不是**速度**旋钮。本机预填充 348–383 tok/s，32 K prompt 光读入就要 88 秒、78 K 要 217 秒。日常对话和改代码根本用不到 1 万以上。

**环境变量参考（本机实测大部分没必要设）：**

| 变量 | 作用 | 建议 |
|------|------|------|
| `OLLAMA_CONTEXT_LENGTH` | 全局默认上下文 | **不推荐**：被 GUI 设置覆盖，设了也白设 |
| `OLLAMA_FLASH_ATTENTION=1` | 长上下文提速 | MLX 后端内置常开，变量基本 no-op，写上无妨 |
| `OLLAMA_KV_CACHE_TYPE=q8_0` | KV 缓存量化省内存 | 🔴 **MLX 路线不必设（2026-11-04 三组 A/B 定案：同请求 KV 增量 2.87 vs 2.85GB，纯 no-op）**。262144 在 MLX 下靠 KV 动态分配（≈53 KiB/token）稳定，无需量化；**GGUF/llama.cpp 路线仍真实有效**（qwen3:4b 实测省 2.16GB） |
| `OLLAMA_KEEP_ALIVE=30m` | 模型驻留 30 分钟再卸载 | 免每次对话重载（冷重载本身仅 2.5–6 s）。**2026-11-03 老板定 30m**（与公众号文章一致），不用 `-1`（永久占 25GB 显存不释放）。改值时注意：`launchctl setenv` 旧值会残留，改 plist 后要 `launchctl unload`+`load` 或重新 `setenv`（见 TROUBLESHOOTING §6） |

> 想让环境变量持久化：走 `launchctl setenv`（在本人终端里直接跑即成功，`getenv` 立即返回；重启 Ollama 生效）或写 LaunchAgent plist `~/Library/LaunchAgents/com.user.ollama-env.plist`（登录自动注入、跨重启持久）。**别走 shell 的 `.zshrc`**——Ollama.app 是独立 GUI 进程，不读 shell 环境，写在 shell 里等于没设。

### 第七步：验证安装

```bash
# 查看模型信息
ollama show qwen3.8:27b-mlx

# 确认上下文长度已生效：看 ollama ps 的 CONTEXT 列（这才是实际生效值）
# 注意 ollama show 里的 num_ctx 只是模型标签自带值，不等于运行时实际值
ollama ps

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

## 引擎选型实测：MTPLX vs Ollama（2026-10-03）

> 这是**补充实测，不是主推荐路线**。结论：继续用 Ollama。

有读者问「本地推理工具里那个投机解码引擎（MTPLX）能不能把 Ollama 换掉」。
我们把它装进来跟 Ollama 硬碰了一场：同一份 27B MLX 权重、同一条 900 字长文 prompt、`max_tokens=1200`、各 3 轮取中位数。

| 引擎 | 首 token | 解码 tok/s | 峰值内存 |
|---|---|---|---|
| **Ollama 0.34.1**（`qwen3.8:27b-mlx`） | **0.17 s** | **26.61** | ~32 GB |
| MTPLX 2.12.2 `turbo` + MTP | 1.10 s | 23.04 | 22.7 GB |
| MTPLX 2.12.2 `turbo` **`--no-mtp`** | 2.17 s | **11.41** | 21.4 GB |

（口径：长文生成、单并发、num_ctx 131072。跟上面「四模型性能总表」的 ~30 tok/s 不冲突，那个是短上下文短输出的测法。）

**关键在最后一行。** 把投机解码关掉，MTPLX 只剩 11.41 tok/s，是 Ollama 的四成 —— 它裸解码比 Ollama 慢 57%；
全靠 MTP 拉回 23.04，还是差 14%。所以：

- **MTP 是赚的**：对 MTPLX 自己 +102%，别信「投机解码是负资产」这种说法；
- **换引擎是亏的**：总账仍然落后 Ollama。

MTPLX 只吃 MLX 档案、Apple Silicon 专用；官方标的 87.6 tok/s 本机复现不出来（人家是 M5 Max + "重写刚写完的文件" + stock 设置）。

什么时候值得考虑它：**内存紧张时**（峰值低 10 GB），以及**短输出 + 高接受率**的 workload（代码续写、固定格式生成）。
长文生成用它基本白给。

完整数据、机制拆解（一个验证轮 84.6 ms 换 3 个 token = 28 ms/token，跟裸解码 30 ms/token 打平）
和六个部署坑（含「分片下坏了但文件大小完全正确 → 全词表 NaN」）见
**[MTPLX引擎实测-vs-Ollama.md](./MTPLX引擎实测-vs-Ollama.md)**。想自己复现用 `local_bench.py`。

## 在 agent 框架里跑本地模型：会话语境膨胀避坑（2026-10-10）

把本地模型接进 Hermes / Claude Code / Codex 这类 **agent 框架**（长会话、多工具调用）时，很多人会撞上一个怪现象：

> 随便聊 1-2 轮，会话体积就涨到 **1MB+**、触发上下文超限告警；换远程 API 模型聊好几轮才 300KB，稳得很。

这**不是模型笨，也不是 thinking 开关的错**——是「拿不到真实 token 计数 + 窗口分母偏小 + 压缩摘要自己压自己超时失败 + 旧工具返回不裁」四个机制叠加。**关掉 thinking 治不了超限**（thinking 默认不进入发送账本），真正要修的是压缩和裁剪。

修法分两档：
- **方案 A（推荐，纯本地零隐私代价）**：开 `micro_compact` 每轮折叠旧工具结果 + 把压缩超时放宽到 300s。
- **方案 B（兜底，摘要外发）**：本地仍压不动时，把**摘要模型**单独指一个云端快档（注意：只摘要外发，主对话仍本地）。

诊断顺序（换任何本地模型都通用：Qwen / GLM / Llama / Mistral…）：
1. `ollama ps` 看真实 `num_ctx`；2. 框架发的是流式吗（流式 Ollama 不返 usage）；3. 框架配置里的 `context_length` 是**真键还是死键**；4. 压缩摘要是 `auto` 还是外部模型、有没有 `summary failed` 日志；5. 有没有开裁剪旧工具结果。

完整根因、实测证据、可直接复制的 config 键、自检清单见
**[本地模型会话语境膨胀避坑.md](./本地模型会话语境膨胀避坑.md)**。

## 常见问题

> 按现象索引的完整排查手册（9 个常见问题 + 根因 + 修复命令）见 **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)**，以下为高频简答。

### Q1: 内存不足怎么办？
按内存定上下文：**本机 48 GB 实测 262144 稳定**（MLX KV 动态分配，idle ~18–31GB，不预占满窗；多引擎同驻时才需下调到 32768/65536）。早期文档写"262144 必然 evict"是对争用日志的误读，已作废（见 `CURRENT_CONFIG.md`）。仍不足再换更小量化（IQ3_S / Q4_K_M），并顺手确认**没有第二个推理引擎在同时跑**。

### Q2: 生成速度很慢？
检查是否开启了 Swap，确保模型完全加载到内存。

### Q3: 图片理解报错？
MLX 原生版 `qwen3.8:27b-mlx` 自带视觉投影，直接发图即可，无需额外视觉模型。GGUF / GSQ 路线（Q5、GSQ IQ3 等）同属 GGUF 格式，需在 Modelfile 写入 Qwen 多模态模板并挂 mmproj（见弯路3）。

### Q4: 需要联网吗？
不需要。本地模型完全离线运行，无需联网。

### Q5: MLX 跑 128K 上下文会爆显存吗？
单跑不会。2026-09-10 的 A/B 实测中，MLX 在 131072 上下文下 5 维题 2 轮 **10/10 全过、零 OOM**；本机后续在 **262144** 上下文（模型上限）下也单跑稳定（idle ~18–31GB，MLX KV 动态分配）。GSQ / GGUF 路线（Q5、IQ3 等）同属 llama.cpp 引擎，单跑 131K+ 上下文同样稳定。之前偶发的「间歇性显存溢出」，根因是**多个会话/进程同时调同一个 MLX 模型**，KV 缓存显存叠加——不是上下文太长。

> ⚠️ **「装得下」不等于「快」**：容量上限与速度无关，真实等待时间由 **单轮 prompt token 数** 决定。本机预填充 348–383 tok/s，**32 K prompt 光读入就要 88 秒、78 K 要 217 秒、156 K 要 ~7 分钟**。所以窗口开到 262144 给长会话留缓冲是对的，但**单轮输入仍要压在 ~1 万 token 以内**（控制 file_read_max_chars / tool_output / 历史裁剪），否则一次 prefill 就几分钟，Ollama 单并发会把后续请求全堵死。

- 日常单跑 / 短中交互：直接用 `qwen3.8:27b-mlx`（MLX），窗口沿用 GUI 的 262144（本机实测稳定）；只有多引擎同驻、内存吃紧时才临时下调到 32768/65536。
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

## 外部收录与推广（信任票）

到 2026-10-05 为止，本仓库主动提进社区目录列表的 PR 一共 3 个，**3 个都还没被合并**：

| 列表 | PR | 状态 | 列表活跃度 |
| --- | --- | --- | --- |
| [rafska/awesome-local-llm](https://github.com/rafska/awesome-local-llm) | [#229](https://github.com/rafska/awesome-local-llm/pull/229) | 待合并 | ★2.9k，2 天前还在更新 |
| [awesome-ai-tools/curated-local-ai](https://github.com/awesome-ai-tools/curated-local-ai) | [#5](https://github.com/awesome-ai-tools/curated-local-ai/pull/5) | 待合并 | ★7，2026-03 后无人维护 |
| [iCHAIT/awesome-macOS](https://github.com/iCHAIT/awesome-macos) | [#1139](https://github.com/iCHAIT/awesome-macos/pull/1139) | 待合并 | ★19k，43 天前更新 |

另外两条实测结论，记录在此免得后来人重踩：

- **别往主仓库贴**。GitHub 上最火的那个 awesome 主仓库（`sindresorhus/awesome`），仓库描述里自己写着「Pull requests are temporarily disabled until I have a chance to catch up with the existing ones」——PR 入口是关着的，星再高也不收。
- **贴之前先看列表收不收「文档/指南类」**。有的目录列表是 bot 自动生成的，只收可运行软件，提文档类进去会被拒（awesome-selfhosted 就是这类，别白跑）。

顺带一句：PR 进目录只是「多一条外链」的信任票，不是「被权威认证」。`gh pr create` 用的是你自己账号，代提、代撤都行，但结果要自己盯。

## 联系作者

- 微信公众号：**Jason 的落地思考**
- 稀土掘金：[Jason的落地思考](https://juejin.cn/user/1574156379368311)
