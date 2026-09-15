# 本地部署 Qwen3.8 全记录：从翻车到跑通

Jason 的落地思考  
2026年9月9日 12:30（2026-09-11 增补 A/B 稳定性实测）

最近Qwen3.8很火，本地化部署的效果评价很高，但是很多人纠结自己的电脑是否能够跑得起来，不知道应该部署哪个版本。

我也查了不少博主分享的部署教程，要么步骤不够清晰，要么按步骤来但是问题不断。作为一个坚信实践出真知的产品人，经过几天的全方位试错和对比，我亲手摸索出来了一套本地部署 Qwen3.8-27B 的方案，配合 AI Agent 工具链使用。

今天把完整经验分享出来，技术背景强的朋友和想本地跑大模型的门外汉都能照着做。

---

## 一、为什么选 Qwen3.8-27B？

先说结论：**Qwen3.8-27B 是目前本地部署性价比最高的模型之一。**

我选它，主要是因为它在四个方面做得挺平衡的：

**1. 开源免费，商用也没问题**

阿里通义团队出的，Apache 2.0 协议，你想怎么用就怎么用，不用交智商税。这在本地部署的场景下特别重要，毕竟谁也不想用的是个盗版或者随时可能被收费的模型。

**2. 多模态，能看图**

这个对我来说挺关键的。Qwen3.8 支持图片输入，配合 Ollama 的视觉投影，你可以直接在对话框里发图给模型看。我之前让它看了几张工作场景的照片，识别准确率还挺高的。

**3. 本地运行，隐私安全**

你的聊天记录、文档、截图，全部留在本地，不会上传到任何云端。做 B 端产品的人最怕的就是数据泄露，这个方案彻底解决了这个问题。

**4. 速度够用**

M5 Pro + 48GB 统一内存，跑 Qwen3.8-27B（MLX 原生版），实测约 40 tok/s。生成一段代码或者分析报告，基本能接受，不会有那种让人窒息的等待感。

赶时间的话，就记一句：**内存够就直接上 MLX 原生版，别绕弯。**剩下的都是细节。

---

## 二、硬件门槛——我的配置

我用的是 **Apple M5 Pro + 48GB 统一内存**。

说实话，内存真的很关键。因为 Qwen3.8-27B 全精度模型要 54GB，量化后大概 18~28GB（取决于量化档位和引擎）。统一内存的好处是 CPU 和 GPU 共享，不需要像 NVIDIA 那样考虑显存够不够。

**最低配置建议：**

| 方案 | 内存要求 | 说明 |
|------|---------|------|
| MLX 原生版 | ≥ 24GB | 约 18GB，速度最快 |
| GGUF Q5_K_M | ≥ 32GB | 约 20GB，质量略高 |
| GGUF Q4_K_M | ≥ 24GB | 约 15GB，速度略慢 |

硬盘空间至少留 50GB（模型文件 + 缓存），必须用 Apple Silicon（M1/M2/M3/M4/M5），这是当前最优路径。

再多说一句实话：上面表格里的「≥」都是能跑起来的下限，不是跑得舒服的标准。24GB 内存跑 MLX，权重加 KV 缓存就占掉 21GB 左右，贴着上限飞，得把上下文长度降下来才稳；想跑得从容，32GB 起步。这篇文章的所有实测数据都来自 48GB 机器，你机器比我小的，照这个梯度往下调预期。

> **MLX 与 GGUF**：同一个模型在 Mac 上有两种主流打包格式。GGUF 是 llama.cpp 生态的通用格式，Q4_K_M、Q5_K_M 这类后缀是量化档位——数字越大越接近原版精度、体积也越大；MLX 原生版是苹果自家机器学习框架的格式，配专用推理引擎。后文说的「MLX 路线」「GGUF 路线」指的就是这两者。

---

## 三、部署全流程（含国内镜像）

### 第一步：安装 Ollama

**国外官网**：https://ollama.com  
**国内镜像**：如果官网下载慢，可以用 [hf-mirror](https://hf-mirror.com/models?q=ollama) 或者直接下载安装包。

直接下载安装，一路 Next 就行。安装完后在终端输入：

```bash
ollama --version
```

如果输出版本号（建议 0.33+），说明装好了。

---

### 第二步：下载模型（国内镜像方案）

**关键：直接用 Ollama 标签，不要手动下 GGUF！**

```bash
ollama pull qwen3.8:27b-mlx
```

这会自动从 HuggingFace 下载 MLX 原生量化版本（nvfp4，约 18GB）。

> **nvfp4**：一种 4-bit 浮点量化格式，把 27B 模型的权重从 50 多 GB 压到 18GB 出头，精度损失控制得比较克制，是 MLX 版又小又快的基础。

**如果内存紧张或想更省显存，还有两条路线（都需要补一个 Modelfile 才能用）：**

**方案 B：GGUF Q5_K_M（并发更稳，≥32GB）**
```bash
ollama pull unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q5_K_M
```
GGUF 路线需要补 Modelfile（挂多模态模板 + 开 MTP + 视觉投影），否则发图报错、且浪费模型自带的加速，见下方「创建本地模型」。

**方案 C：GSQ-RCO IQ3_S（省显存均衡，≥16GB，≈12GB 基本无损）**
```bash
# 从 HuggingFace 下载（国内走 hf-mirror.com 镜像）
pip install -U "huggingface_hub[cli]"
hf download ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf mmproj-Qwen3.8-27B-BF16.gguf --local-dir .
# 再用下方 Modelfile 创建 Ollama 模型
```
> **GSQ-RCO** 是 ISTA-DASLab 的学习式混合精度量化，IQ3_S 把 27B 压到 ~12GB 而质量基本无损（GPQA 仅差 0.5 分），比 Q4_K_M 还小还稳；IQ3_XXS（~10GB）更省显存，但知识题有 ~1 分边际风险。

**创建本地模型（GGUF / GSQ 路线必需）**

MLX 版 `ollama pull` 完就能用；GGUF / GSQ 需要写 Modelfile 挂多模态模板与 MTP：

```dockerfile
FROM unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q5_K_M   # GSQ 换成 ./Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf
FROM ./mmproj-F16.gguf                                  # 视觉投影（多模态必需）
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

```bash
ollama create qwen3.8-q5 -f Modelfile.q5       # GGUF Q5
ollama create qwen3.8-gsq-iq3s -f Modelfile.gsq # GSQ IQ3_S（换 FROM 即可）
```

**如果网络慢或者 HuggingFace 访问不了，可以试试国内镜像：**

**国内镜像 A：设置环境变量，走 hf-mirror.com**
```bash
export OLLAMA_MODELS=/usr/local/var/lib/ollama/models
export HF_ENDPOINT=https://hf-mirror.com
ollama pull qwen3.8:27b-mlx
```

**国内镜像 B：直接用 ModelScope（魔搭社区）**
```bash
# 先用 python 从 ModelScope 下载（官方模型 ID）
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3.8-27B', cache_dir='./models')"
# 然后用本地文件创建 Ollama 模型
ollama create qwen3.8:27b-mlx -f ./Modelfile
```

注意：方案 B 要下的是 **MLX 量化版权重**，不是全精度；`ollama create` 用的 Modelfile 直接用文末 GitHub 仓库里那份，别自己手写。这条路比方案 A 多几步，优先试方案 A。

**为什么要用 MLX 原生版？**

我试过 GGUF 方案，但 MLX 原生版有两处实打实的优势：

1. **速度快约 2 倍**：M5 Pro 上代码生成 40.8 tok/s vs GGUF 22.4 tok/s
2. **首 token 延迟低**：3-4 秒即出字（GGUF 方案在内存紧张时会触发 swap，首 token 可能要等几分钟）

> **想省显存怎么办？** 如果你同机还要跑 MiniMax H3 这类视频模型、显存吃紧，GSQ-RCO IQ3_S 是另一个好选择：体积只有 ~12GB、质量基本无损（12 题严格校验全对），只是生成速度约为 MLX 的一半（同条件 A/B 实测 12.6 vs 29.9 tok/s）。IQ3_XXS（~10GB）更省，但知识题有 ~1 分边际风险。

---

### 第三步：配置全局环境变量

这是最关键的一步，决定了你能否顺利跑长上下文。

```bash
# 全局设置，所有模型受益
launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_KEEP_ALIVE 30m

# 重启 Ollama 生效
pkill -f "ollama serve" && sleep 2 && open -a Ollama
```

提醒：`launchctl setenv` 设置在**重启 Mac 后会失效**，重启后重跑一遍即可；想一劳永逸，把变量写进 Ollama 的 LaunchAgent plist 里。

**每个变量的作用，我简单解释一下：**

| 变量 | 作用 | 不设置的后果 |
|------|------|-------------|
| `OLLAMA_CONTEXT_LENGTH=131072` | 全局默认 128K 上下文 | 未设置的模型用 4096 默认值，长文档被静默截断 |
| `OLLAMA_FLASH_ATTENTION=1` | 长上下文推理提速 30-50% | 速度慢 |
| `OLLAMA_KV_CACHE_TYPE=q8_0` | KV 缓存量化，内存减半 | 内存占用高，可能触发 swap |
| `OLLAMA_KEEP_ALIVE=30m` | 模型驻留内存 30 分钟 | 每次调用等 6 秒冷启动 |

> **KV 缓存**：模型生成时给「已处理过的文字」记的草稿本，上下文越长这块占用越大。q8_0 就是把这个草稿本也压缩一档，省显存，精度几乎无损。

---

### 第四步：验证安装

```bash
# 查看模型信息
ollama show qwen3.8:27b-mlx

# 确认上下文长度生效
ollama show qwen3.8:27b-mlx | grep num_ctx
# 应输出 131072，不是 4096

# 测试对话
ollama run qwen3.8:27b-mlx "你好，简单介绍一下你自己"

# 测试图片识别（需要 base64 编码图片）
python3 -c "
import base64, json, urllib.request
b64 = base64.b64encode(open('/path/to/image.png','rb').read()).decode()
p = {'model':'qwen3.8:27b-mlx','messages':[{'role':'user','content':[
  {'type':'text','text':'描述这张图。'},
  {'type':'image_url','image_url':{'url':f'data:image/png;base64,{b64}'}}
]}],
  'max_tokens':4000, 'stream':False}
r = urllib.request.urlopen(urllib.request.Request(
  'http://127.0.0.1:11434/v1/chat/completions', data=json.dumps(p).encode(),
  headers={'Content-Type':'application/json'}), timeout=300)
print(json.loads(r.read())['choices'][0]['message']['content'])
"
```

看到全部正常就说明装好了。

---

## 四、配合 AI Agent 工具使用

Qwen3.8 本地跑起来后，就可以配合各种 Agent 工具使用了。

### 4.1 切换到本地模型

**以 Trae 为例：**

要在 Trae 里用本地 Qwen，它的「添加自定义模型」走 OpenAI 兼容格式，直接把 Base URL 指向本机 Ollama 即可：

设置 → 模型 → 添加自定义模型（选 OpenAI 兼容格式）
- Base URL：`http://127.0.0.1:11434/v1`
- 模型 ID：与 `ollama list` 一致（如 `qwen3.8:27b-mlx`）
- API Key：必填但可任意填（Ollama 不校验）

注意：Ollama 暴露的是 OpenAI 兼容接口，所以 Trae 这类支持 OpenAI 格式的工具能直接接；走 Anthropic 协议的工具（如 Claude Code）则必须加一层网关把协议翻成 Ollama，否则直连会报错。

**其他主流 Agent 工具的接法：**

| 工具 | 接本地模型的方式 |
|------|------|
| OpenCode | `opencode --model ollama/qwen3.8:27b-mlx` |
| Codex | 经 cc-switch 网关中转，不能直接指向 Ollama |
| Hermes Agent | 在会话中使用 `/model` 命令切换 |
| Claude Code | 走 Anthropic 协议，需经协议翻译网关（如 claude-code-router / one-api）转成 Ollama 的 OpenAI 兼容接口，再 `claude --model qwen3.8:27b-mlx` |

### 4.2 切回云端（以下以 Trae 为例）

> 注意：下面以 Trae 为例。其它 agent 的切回方式见 4.1 表格——OpenCode 改 `opencode --model` 参数、Codex 取消 cc-switch 网关指向、Hermes 用 `/model`、Claude Code 清空 `ANTHROPIC_BASE_URL` 并设回 `ANTHROPIC_API_KEY`。

在 Trae 里切回云端模型，只需把模型选择从本地自定义模型换回内置云端模型：

1. 打开 设置 → 模型
2. 模型下拉里选择内置云端模型（Trae 默认提供的云端模型）
3. 若之前添加了本地自定义模型，可将其删除，或切回内置供应商

这样就不再走本地 Ollama，恢复调用云端模型。

---

## 五、项目走过的弯路

这部分是我踩过的坑，大家可以直接跳过，但如果遇到问题可以参考排查思路。

### 弯路1：MLX 折腾记——超时 bug 和引擎误区

MLX 我前后踩了两回坑，合在一起说。

**第一坑：超时 bug。**

一开始我先试的 MLX 原生版 `qwen3.8:27b-mlx`，赶上 Ollama 一个已知回归 bug——[GitHub Issue #16081](https://github.com/ollama/ollama/issues/16081)。机理说穿了不复杂：v0.23.1/v0.23.2 起引入，服务器每 10 秒对 runner 做一次健康检查，而这个检查要排在漫长的推理队列后面；大上下文推理一忙起来，检查等满 10 秒等不到响应，进程就被判「失联」强杀，报 `context canceled` 和 500 错误。

我那时候刚好踩到。试了好几种办法都超时，只能放弃 MLX，转走 GGUF + Metal 路线。

> **Metal**：苹果的 GPU 计算接口。llama.cpp 在 Mac 上跑 GGUF 全靠它调 GPU，属于和 MLX 并列的另一条引擎路线。

**第二坑：给 GGUF 强开 MLX 引擎。**

转 GGUF 之后又不甘心——听说 MLX 快嘛，就设了 `OLLAMA_LLM_LIBRARY=mlx`，想让 Ollama 用 MLX 引擎跑手头的 GGUF 文件。结果完全没用，模型还是走的 Metal。

根因是 MLX runner 根本不认 GGUF 格式的权重。GGUF 只能用 llama.cpp（Metal 后端），想上 MLX 引擎就得换 MLX 原生格式（safetensors/nvfp4）。

**转机：**

今年 5 月社区把这个 bug 修了（PR #16086，commit 2b9e024——健康检查改成读缓存的内存快照，不再傻等推理线程，现在的 0.30+ 都已包含），我升级后切回 MLX 原生版：超时没了，速度还比 GGUF 快将近 2 倍，前面两回折腾都值回来了。

**教训：**

- 遇到 MLX 超时，先查是不是已知 bug，可能升个版本就解决
- GGUF 走 Metal（LLM_LIBRARY 保持默认），MLX 原生格式走 MLX 引擎（无需任何环境变量）——别为了用 MLX 而 MLX

---

### 弯路2：上下文长度默认只有 4096

**现象：**

读长文档时报错 "context length exceeded"，或者模型表现得像"记不住东西"。

**根因：**

我检查 `ollama show` 输出才发现，虽然模型支持 262K 上下文，但**默认值只有 4096**。表现有两种：有的客户端会直接报 "context length exceeded"；更坑的是 Ollama 对超长部分直接静默截断，不报错，只是模型"看不见"后面的内容。

**教训：**

一定要全局设置 `OLLAMA_CONTEXT_LENGTH=131072`，否则每个新拉的模型都会用默认值。

---

### 弯路3：图片识别报错 400

**现象：**

用 WorkBuddy 发图时，报 `400 BadRequestError: No data iterator found for token: <|video_pad|>`。

**根因：**

Qwen3.8 的 GGUF 版本不内嵌 chat template，Ollama 会自动退回裸模板 `{{ .Prompt }}`。这个裸模板不懂图像 token 的处理逻辑。

**教训：**

在 Modelfile 里显式写入 Qwen 多模态模板：
```dockerfile
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
```

**注意：** 必须用 `{{ .Content }}`，不能用 `{{ .Content[0] }}`，Ollama 模板引擎不支持数组索引。

---

### 弯路4：MTP 投机解码默认关闭

**现象：**

性能不够快，以为模型本身的问题。

**根因：**

Qwen3.8 的 GGUF 文件自带 MTP 投机解码头，但默认是关闭的（`draft_num_predict=0`）。日志里一直是 `specu: no`，等于白扔了模型自带的加速功能。

**解决：**

在 Modelfile 里设置：
```dockerfile
PARAMETER draft_num_predict 3
```

实测效果：代码生成从 11.7 tok/s 提升到 21.6 tok/s（+85%；与第七节表格的 22.4 是不同批次实测，有正常浮动）。

---

### 弯路5：keep_alive 对 /v1 API 不生效

**现象：**

设置了 `OLLAMA_KEEP_ALIVE=30m`，但每次调用还是要等 6 秒冷启动。

**根因：**

WorkBuddy 走的是 OpenAI 兼容的 `/v1/chat/completions` 端点，这个端点**会忽略请求里单独传的 keep_alive 参数**。注意别混两件事：请求参数被忽略，不等于服务端环境变量没用——`OLLAMA_KEEP_ALIVE` 是服务端全局默认值，所有端点都吃它。我一开始把这两件事搅在一起，白折腾了好一阵。

**教训：**

两条路二选一：要全局省心，就 `launchctl setenv OLLAMA_KEEP_ALIVE 30m`（重启 Ollama 生效）；要按请求精细控制，就走原生 API（`/api/chat`），它支持在请求里带 keep_alive。

---

### 弯路6：localhost 代理陷阱

**现象：**

用 `curl localhost:11434` 能访问，但程序连接失败。

**根因：**

系统代理会拦截 `localhost` 的请求，导致返回假数据或连接失败。另外，`localhost` 可能解析到 IPv6 `::1`，但 Ollama 只监听 IPv4。

**解决：**

始终用 `127.0.0.1:11434` 而不是 `localhost:11434`。

---

## 六、常见问题排查

### 问题1：读长文档时报 "context length exceeded"

**解决：**
```bash
launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
pkill -f "ollama serve" && sleep 2 && open -a Ollama
```

### 问题2：响应速度慢

先分清是哪种慢：每次调用第一次都卡，是冷启动；生成中途越写越慢，是内存不够。

**冷启动，让模型常驻：**
```bash
launchctl setenv OLLAMA_KEEP_ALIVE 30m
```

**内存不够，查 swap（有用量就是真在用 swap）：**
```bash
sysctl vm.swapusage
```

### 问题3：图片识别失败或 400 错误

**MLX 原生版**：自带视觉投影，无需额外配置。

**GGUF 版**：需要在 Modelfile 中显式写入多模态模板（见上文弯路3）。

确保调用时传 `max_tokens: 2000` 或更大，避免 thinking 模式吃光预算。

### 问题4：回复内容为空

**根因**：Qwen3.8 默认开启推理思考（thinking），会先消耗 token 预算。

**解决**：调用时传 `max_tokens: 2000` 或更大，或传 `think: false` 关闭思考。

---

## 七、实测性能数据

下面用本机（M5 Pro / 48GB / Ollama 0.33.3）的实测数据，先给一张四模型总表（含两种测法的速度），再讲首 token 延迟，最后回答「MLX 跑 128K 会不会爆显存」这个高频疑问。

### 四模型速度、体积与质量总表

表中 GSQ 两档来自 ISTA-DASLab 的 **GSQ-RCO** 学习式混合精度量化，把 27B 压到 12 GB / 10 GB 且基本无损；四模型均开 MTP（`draft_num_predict 3`），串行跑完即卸载避免显存叠加。

| 模型 | 量化档位 | 体积 | 短上下文基准 (tok/s)¹ | 12 题严格 A/B 平均 decode (tok/s) | 12 题质量 |
|------|---------|------|----------------------|-----------------------------------|-----------|
| **MLX nvfp4**（MLX 原生版） | NVFP4 4.0bpw | 18 GB | 代码 40.8 / 写作 29.0 / 结构化 34.2 | **29.9** | 全对 |
| Q5_K_M | GGUF 5.6bpw | 20 GB | 代码 22.4 / 写作 13.9 / 结构化 15.2 | 14.9 | 全对 |
| GSQ IQ3_S | 3.5bpw 混合 | 12 GB | 代码 16.2 / 写作 ~12.6 / 结构化 ~12.6 | 12.6 | 全对 |
| GSQ IQ3_XXS | 3.0bpw 混合 | 10 GB | — | 12.5 | 全对 |

¹ 短上下文基准为 2026-09-07 单场景实测（代码生成 / 开放式写作 / 列表结构化）；12 题严格 A/B 为 2026-09-15 同条件对照（temperature=0，统一 12 题）。两列测法不同，倍数不可直接相除比较。GSQ IQ3_XXS 未做短上下文分项基准，以「—」表示。

以上速度为 M5 Pro 实测；MLX 速度受内存带宽影响大，M1–M4 各代芯片会明显不同，请以本机实测为准。

> **关于「MLX 快约 2 倍」**：MTP 投机解码是 Qwen3.8 模型自带加速，GGUF 与 MLX 都需在 Modelfile 写 `draft_num_predict 3` 才生效（输出无损），是两个版本共有的提速项，不是 MLX 独占。MLX 的约 2 倍速度主要来自原生引擎，MTP 再叠加约 +85%（代码类）——两个杠杆叠加，实测才冲到 40 tok/s 上下。

**三个维度的结论（本机 M5 Pro / 48GB / Ollama 0.33.3 实测）：**

- 更省内存：IQ3_S 比 MLX 4-bit 省 6 GB，IQ3_XXS 省 8 GB，可直接给 131K 上下文或同机 MiniMax H3 视频模型腾地方。
- 更快：MLX 4-bit 平均 decode 29.9 tok/s，约为 GSQ 混合精度的 2.4 倍。NVFP4 是 GPU 友好的均匀 4-bit，IQ/GSQ 混合精度每个权重解量化开销大，在 Apple Silicon 的 Metal 后端（memory-bound）反而更慢。
- 质量无损（vs MLX）：12 题四档全对（JSON 严格可解析、数学最终答案一致、知识题选项一致）。ISTA-DASLab 在 198 题 GPQA 上测得 IQ3_XXS 相对 BF16 差 ~1 分，需大题集才复现。

**选型建议（48GB Mac，主用 agentic coding + 长推理）：**

- 速度优先 → 保持 **MLX nvfp4**（现状）
- 均衡（推荐切换）→ **GSQ IQ3_S**：省 6 GB、质量不降
- 极致省显存 → **GSQ IQ3_XXS**（接受知识题 ~1 分边际风险）
- 并发安全网 → **Q5** 维持

### 首 token 延迟（TTFT）

> **TTFT**：Time To First Token，从发出请求到吐出第一个字的等待时间。它决定聊天「跟不跟手」——生成速度再快，首字等三分钟也难受。

| 配置 | 首次加载 | 常驻期间 |
|------|---------|---------|
| Q5_K_M + MTP | ~2-3 分钟（swap 时） | ~0 秒 |
| qwen3.8:27b-mlx | **3-4 秒** | ~0 秒 |
| GSQ IQ3_S / IQ3_XXS + MTP | 同 Q5（GGUF 路径） | ~0 秒 |

MLX 原生版不光生成快，更重要的是绕开了 swap 地狱：首 token 从分钟级降到秒级，体感的提升主要来自这里。

### MLX 稳定性 A/B 实测（2026-09-10）

MLX 跑 128K 上下文，到底会不会爆显存？我专门做了一次对照测试：

- **质量没掉**：同一套 5 维题（代码生成 / 逻辑推理 / 20k 字长文档检索 / 看图读值 / 中文表达），MLX 原生版和 Q5 的回答质量打平，肉眼分不出差别，感受不到降智。网上「MLX 质量≈Q4 档」的说法，至少在 M5 Pro 上不成立。
- **单跑很稳**：确认 `ollama ps` 干净、没有后台并发之后，MLX 跑满 131072 上下文加 MTP，5 维题连跑两轮，10/10 全过，一次 OOM 都没有。
- **之前的锅在并发**：早前偶发的显存溢出，是几个会话同时调同一个 MLX 模型，KV 缓存的显存叠加起来撑爆的，单跑没这问题。
- **我现在的用法**：日常主力 `qwen3.8:27b-mlx`（满血 131k + MTP）；要开一堆 agent 会话的时候切 `qwen3.8-q5`，llama.cpp 对并发更扛造。

> **OOM**：Out Of Memory，显存/内存耗尽。轻则请求报错，重则 Ollama 进程被系统直接砍掉，是本地跑大模型最常见的翻车方式。

> 实操就一条：别让多个会话同时调同一个 MLX 模型，错开用就没事。

---

## 八、总结

这套方案的核心思路是：

1. **模型选型**：Qwen3.8-27B，性能强、免费开源、多模态支持
2. **引擎选择**：MLX 原生版，比 GGUF 快约 2 倍，首 token 延迟更低
3. **全局配置**：4 个环境变量一次设置，所有模型受益
4. **工具配合**：Ollama + AI Agent 工具，即插即用

从翻车到跑通，大概花了 2-3 天时间，主要是被以下几个问题卡住过：
- 上下文默认只有 4096，长文档被静默截断
- 图片识别报错 400，因为模板没写对
- MTP 投机解码默认关闭，浪费了模型自带的加速功能
- keep_alive 对 /v1 API 不生效，每次都要冷启动

现在这套方案已经稳定运行，每天陪我写代码、分析文档、整理思路，效率提升明显。
---
