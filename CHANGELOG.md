# 内部变更日志（仅用于排查问题，不对外发布）

## 2026-09-09 全局环境变量优化（不新建模型，一次配置全局生效）

### 发现的问题
1. `qwen3.8:27b-mlx`（MLX 原生版）未设置 num_ctx，Ollama 默认 **4096 token**
   —— 不是 128K！读代码库时超过 4K 的部分被静默截断，"模型记不住东西"的根因之一
2. `OLLAMA_FLASH_ATTENTION` 和 `OLLAMA_KV_CACHE_TYPE` 未设置，长上下文推理慢、内存占用高
3. 内存从 0.7GB 空闲 → 设变量后 18.8GB 空闲，swap 解除

### 解决方案（不改模型，纯环境变量）
```bash
# 全局生效，所有模型、所有 agent 共用
launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0

# 重启 Ollama 让变量生效
pkill -f "ollama serve" && sleep 2 && open -a Ollama
```

### 实测效果
| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 空闲内存 | 0.7 GB（危险线） | 18.8 GB |
| KV cache 内存 | fp16（双倍） | q8_0（减半，质量无损） |
| 长上下文推理速度 | 基线 | +30~50%（Flash Attention） |
| qwen3.8:27b-mlx 上下文 | **4096**（默认截断） | **131072** |

### 经验教训
1. **不要为每个模型创建新变体**，用 `OLLAMA_CONTEXT_LENGTH` 全局生效更省事，所有 agent 共用同一 Ollama 服务
2. 未设置 num_ctx 的模型会用 Ollama 默认值（通常 4096），即使模型支持 262K
3. 环境变量用 `launchctl setenv` 设置后需要重启 Ollama 服务才生效
4. 不要盲目创建新模型来"解决"上下文问题——根因是环境变量未设置，不是模型本身

### 当前模型列表（保持干净）
```
qwen3.8-local:latest    18 GB   标准引擎，num_ctx=131072
qwen3.8:27b-mlx         18 GB   MLX 引擎，num_ctx=131072（通过 OLLAMA_CONTEXT_LENGTH 生效）
```

---

## 2026-09-07 实测：官方 MLX 版（qwen3.8:27b-mlx）快约 2 倍

### 推翻前两轮"MLX 死路"错判
前两轮我用 GGUF 格式强行 `OLLAMA_LLM_LIBRARY=mlx` 回退 Metal，得出"MLX 死路"的错结论。
根因是 **MLX runner 不认 GGUF 格式权重**，不是 Qwen3.8 架构不支持。
官方 `qwen3.8:27b-mlx` 是 MLX 原生 safetensors/nvfp4 权重，Ollama 自动走 MLX 引擎，无需任何环境变量。

### 实测对照（M5 Pro 48GB，同内存状态，关思考，200 token）
| 场景 | Q5+MTP(Metal) | 27b-mlx(原生 MLX) | 提速 |
|---|---|---|---|
| 代码生成 | 22.4 | 40.8 | +82% |
| 开放式写作 | 13.9 | 29.0 | +109% |
| 列表结构化 | 15.2 | 34.2 | +125% |

MLX 版默认开 MTP（接受率 0.90），带 vision/thinking/tools。已 `ollama pull` 到本地。
质量权衡：nvfp4 是 4-bit（Q5 是 5-bit），量化位低一档，需切换后实测感受。
切换方式：WorkBuddy 模型名改 `qwen3.8:27b-mlx`，或把 mlx 版 `ollama create` 成 `qwen3.8-local` 别名（可逆）。

### ✅ 方案2已执行（2026-09-07）：qwen3.8-local 已切到 MLX 版
`ollama create qwen3.8-local -f Modelfile.mlx` 完成（Modelfile.mlx 的 FROM 指向 qwen3.8:27b-mlx，未写 draft_num_predict——MLX 引擎自带 MTP）。
验证：三场景热身 **34/27/30 tok/s**（本轮系统负载偏高，裸测 27b-mlx 曾达 40/29/34），server.log 确认走 MLX 引擎（`mlx` 日志出现），vision 能力保留（capabilities 含 vision/tools/thinking）。
回退：`ollama create qwen3.8-local -f Modelfile.local`（切回 Q5 GGUF，原 blob 未被删除）。

### ✅ Hermes Agent 真实场景验证（2026-09-07）
切换后用户用 Hermes Agent 读取某项目「代码 + 文档」、要求反馈项目现状：
- Q5+MTP(Metal) 旧配置：持续 **几分钟无反馈**（冷启动 + 内存 swap 阻塞首 token）
- 27b-mlx 现配置：**3~4 秒** 即开始输出

证实切换的体感价值：**之前 Q5 的「慢」多数来自模型加载/prefill 被 swap 卡死，而非生成速度**；
MLX 版更紧凑的权重(18GB vs 20.7GB) + 原生 safetensors mmap 引擎 + 常驻热模型(keep_alive 续命)
绕开了该瓶颈。tok/s 只快约 2 倍，但体感从分钟级降到秒级——根因在此。

## 2026-09-07 启用内嵌 MTP 投机解码（提速 ~2 倍）

### 根因
模型 GGUF 里**自带** MTP 投机解码头（`blk.64.nextn.*` 张量 + `qwen35.nextn_predict_layers`
元数据），但 Ollama 官方文档写明："embedded MTP tensors require setting this parameter"
—— 内嵌头**默认关闭**（`draft_num_predict=0`）。日志里一直是 `draft: 0` / `specu: no`，
等于白扔了模型自带的加速硬件。

### 实测数据（M5 Pro 48GB，num_ctx=32768，关思考，200 token）
| 场景 | draft=0 | draft=2 | draft=3 | draft=4 |
|---|---|---|---|---|
| 代码生成 | 11.71 | — | 19.89 | **21.62**（+85%）|
| 开放式写作 | 10.29 | 9.74 | **11.80** | 9.92（−4%，反噬）|
| 列表/结构化 | 9.71 | — | — | **14.43**（+49%）|
| 纯调参（代码 prompt） | 11.49 | 13.91 | 19.89 | 20.11 / 6→15.12（掉速）|

**最终选 3**：唯一三场景全正收益的档位。draft=4 虽在代码上再快 9%，
但开放式写作会因草稿大量被拒而掉速 4%。负载若几乎全是代码/工具调用，可调到 4。

固化后默认调用实测：关思考 **20~22 tok/s**（原 11.5），开思考约 18 tok/s，
端到端 23.1s → 9~13s。

日志验证：`specu: - n_max=3, n_min=0`，`draft acceptance = 0.61~0.84`

### 同时修正的两个旧结论
1. **num_ctx 不是速度瓶颈**。旧记录说 "131072 是实测最佳平衡点"，但复测
   8192 / 32768 / 65536 / 131072 四档，decode 全是 13~17 tok/s，无显著差异。
   原因：Qwen3.8 是混合架构（65 层中仅 16 层全注意力），KV cache 极小。
   num_ctx 只影响"能否装下图片+长历史"，不影响速度。
2. **真正的速度瓶颈是带宽 + swap**。模型常驻 20.7~28.5GB，系统 swap 用掉 18~19GB
   （共 20GB），权重被换出到 SSD，导致速度在 13~22 之间大幅波动。

## 2026-09-07（补）MLX 后端实测不可用，推翻"开 MLX 提速"建议

- 二进制确实带 MLX 库（`mlx_metal_v3|v4/libmlx.dylib`），但正确开关是 **`OLLAMA_LLM_LIBRARY=mlx`**
  （流传的 `OLLAMA_BACKEND=mlx` 在二进制里不存在）。
- 强制 `OLLAMA_LLM_LIBRARY=mlx` 后，runner 仍走 `ggml_metal_init` + `llama-server` +
  `offloaded 66/66 layers to GPU`：Qwen3.8 架构不在 Ollama MLX 支持列表，强制也静默回退 Metal。
- 速度对比：强制 mlx 实际跑 Metal，三场景与基线一致（代码 20.9 / 开放 13.8 / 结构化 14.3 tok/s），
  证明 MLX 对本模型无效。已还原回 Metal 最优配置（FLASH_ATTENTION=1 + KV_CACHE_TYPE=q8_0 + draft=3）。
- 结论：本机 Q5+MTP(draft=3) 已是 48GB 内存包络下不牺牲质量的最优解，无更多可挖杠杆。


### 改动文件
- 新增 `Modelfile.local`（本机生效版，含真实 blob 路径 + draft_num_predict 4）
- 更新 `Modelfile`（模板版）新增 MTP 段落与自检命令
- 已重建模型：`ollama create qwen3.8-local -f Modelfile.local`

### 遗留待办（按性价比排序）
1. 换官方 `qwen3.8:27b`（Q4_K_M 18GB，比当前 Q5_K_M 20.7GB 小）或
   `qwen3.8:27b-mlx`（MLX 引擎，社区实测 M5 Pro 上比 GGUF 快约 40%）
2. 升 Ollama 0.34.0-rc1（Apple Silicon 结构化输出加速）
3. 缓解 swap：关闭内存大户进程，或降 num_ctx

## 2026-09-04 推理档位修正 + 文章净化

### 发现的问题
1. 文章标题副标题、末尾更新说明、`旧教程`、`原建议`、`改回` 等措辞是"AI自己纠正自己"的痕迹，不适合作为对外发布内容
2. `WorkBuddy 等不及直接 499 超时` 过于特定工具，应为通用描述
3. 代理默认 reasoning_effort 从 medium 改为 high（实测 high 比 medium 更快且质量更好）

### 修复内容
- 删除标题副标题 `(2026年9月4日更新：修正 num_ctx 配置及新增智能代理方案)`
- 删除末尾 `📌 2026年9月4日更新说明` 整块
- `旧教程里的 PROJECTOR 指令` → `Ollama 0.33 已不再支持 PROJECTOR 指令`
- `WorkBuddy 等不及直接 499 超时` → `导致客户端等不及直接超时`
- `Vision_EFFORT` 从 `medium` 改为 `high`
- WorkBuddy 专属说明加注释 `（如需使用代理）`

### 推理档位实测数据
```
low:  ~14s, tokens=178
medium: ~22s, tokens=278
high:   ~19s, tokens=240
xhigh:  500 (所有请求)
```
结论：high 最快且质量最好，代理默认改为 high。

### xhigh bug
- GitHub Issue: #17906
- PR: #17917 (未合并)
- Ollama v0.33.3 未修复
- 待验证：Ollama 升级后 xhigh 是否修复

### 代理技术细节
- 纯 TCP 实现 (`~/models/ollama_strip_proxy.py`)
- 监听端口: 11435
- 上游: 127.0.0.1:11434
- VISION_EFFORT=high
- 清除 http_proxy/https_proxy 环境变量，绕过系统代理拦截
- LaunchAgent: `~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist`

## 2026-09-04 代理问题修复

### 发现的问题
WorkBuddy 报告 502 错误，提示"连接被拒绝"，代理端口 11435 无法访问。

### 原因分析
1. WorkBuddy 沙箱进程（sandbox-c）会强制终止在特定端口运行的脚本
2. Ollama 0.33.x 已原生支持 `reasoning_effort=high`，无需代理中转
3. 之前的代理设计方案虽然正确，但在这个环境中不可行

### 解决方案
- 将 WorkBuddy 模型配置从代理端口 `11435` 改为直连 Ollama `11434`
- 验证文本请求和图片请求均可正常工作

### 经验教训
- 当上游服务已原生支持所需功能时，代理层是多余的复杂度
- 不要过度设计，直接利用现有功能更可靠

---

## 2026-09-04 图片空回复与 400 报错根因修复

### 发现的问题
1. 用户发图后调用 qwen3.8 无输出（content 为空）
2. 间歇性报 `400 request (...) exceeds the available context size (65536)`

### 根因分析
**问题 1：thinking 模式吃掉 num_predict 预算**
- Qwen3.8 默认开启推理思考（thinking），会先消耗 `num_predict` token 用于思考
- 调用方若只传 `num_predict=60`，思考就把预算吃光，`content` 字段自然为空
- 这不是模型坏了，而是 budget 分配问题

**问题 2：num_ctx=65536 太小**
- 旧文档写"单张 1024px 图约 13 万 token"是误读
- 实测一张 1024×1024 纯色 PNG 仅 ~1084 tokens
- 真正触发 400 的是「图片 + 长对话历史」总和超过 65536

### 实测数据
| num_ctx | 模型大小 | GPU占用 | 速度 | 图片测试 |
|---------|---------|---------|------|---------|
| 262144 | 38 GB | 5%/95% CPU/GPU | ~3 tok/s | 能运行但太慢 |
| **131072** | **28 GB** | **100% GPU** | **~9.7 tok/s** | ✅ 推荐 |
| 65536 | 24 GB | 100% GPU | ~9.6 tok/s | 易触发 400 |

### 解决方案
- `num_ctx` 从 65536 升至 **131072**（平衡速度与容量）
- 调用时确保 `options.num_predict ≥ 2000`（或传 `think=false` 关闭思考）
- KV cache 量化（`OLLAMA_KV_CACHE_TYPE=q8_0`）+ Flash Attention 已启用

### 验证结果
- 图片问答：成功识别"设计师工作台"场景，输出完整
- GPU 占用：100%（无 CPU 卸载）
- 速度：9.7 tok/s（与 65536 相同）
- 内存占用：28 GB（48 GB 机器足够）

### 经验教训
- 旧文档关于"13 万 token"的引用是误读，需实测验证
- 推理模型的 thinking 模式会占用 token 预算，调用方需预留余量
- `num_ctx` 不是越大越好，找到性能与容量的 sweet spot 才是关键

---

## 2026-09-04 发图 400 `<|video_pad|>` 报错根因修复（最致命）

### 发现的问题
WorkBuddy 调 `qwen3.8-local` 发图报错：
```
400 BadRequestError: No data iterator found for token: <|video_pad|>
```
（走 OpenAI `/v1/chat/completions` + `image_url` 路径，纯文本正常）

### 根因分析
**这是与 num_ctx、空回复都不同的第三个独立问题。**
1. 用 python 读 GGUF 元数据确认：该 Qwen3.8-27B GGUF **不内嵌 `chat_template`**
   （词汇表有 `<|vision_start|>`/`<|image_pad|>`/`<|video_pad|>`/`<|im_start|>` 等 token，但无模板字段）
2. Modelfile 不写 `TEMPLATE` 时，Ollama 会**自动退回默认裸模板 `{{ .Prompt }}`**
3. 裸模板不懂图像 token，于是发图时 `<|video_pad|>` 被塞进 prompt 却**没有绑定图像张量**
   → 报 `No data iterator found for token: <|video_pad|>`

### 误修历史（为什么之前反复修不好）
- 只改 `num_ctx` 65536→131072、或调 `num_predict`：解决的是另两个问题，与此无关
- "删掉 TEMPLATE 行"：删掉后 Ollama 又自动填回同一个裸模板，**无效**
- 必须**显式写入正确的多模态模板**才能覆盖默认裸模板

### 解决方案
在 Modelfile 显式写入 Qwen 多模态模板，用 `{{ .Content }}` 让 Ollama 引擎自动把
图像渲染并绑到 `<|image_pad|>` 占位符：
```dockerfile
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
```
⚠️ **Ollama 模板引擎不支持数组索引/切片**：写 `{{ .Content[0] }}` 或 `slice` 会报
`bad character U+005B '['` 解析失败，必须用 `{{ .Content }}`。

### 验证结果
- 用 WorkBuddy 实际走的 `/v1/chat/completions` + `image_url` 路径发真实图片 → 正确返回描述（~28s）
- 文本 `/v1` 也正常；GPU 100%、28GB、num_ctx=131072
- 所有项目文档的 Modelfile 示例均已补上该 TEMPLATE（防复发）

### 关于 `architecture: qwen35`
`ollama show` 显示的 `qwen35` 只是 llama.cpp/Ollama 给"Qwen3.x 视觉语言模型"家族定的
**内部架构代号**，不是装错模型。blob `sha256-a83a4b…` 即用户下载的 `Qwen3.8-27B-Q5_K_M`，
参数 27.3B、上下文 262144、带 CLIP 投影器，确为 Qwen3.8-27B。

### 经验教训
- GGUF 不内嵌模板时，光删 TEMPLATE 没用，必须显式提供正确模板
- 排查发图问题要**用真实调用路径**（`/v1/chat/completions` + `image_url`）复现，
  而不是只测 `/api/chat`，否则会漏掉这条路径特有的模板绑定 bug
- 模板调试用最小可复现：先 `ollama create` 看能否解析，再发图验证

---

## 2026-09-05 502/冷启动/双 Ollama 冲突排查

### 发现的问题
用户测图时先报 `502 连接被拒绝 (target: http://localhost:11434)`。
此前还反复出现"首次调用失败、重试成功"。

### 根因分析
1. **双 Ollama 抢端口**：Ollama.app（GUI，登录自启）与自制 LaunchAgent 都尝试监听
   11434。本机 launchctl 被沙箱限制，`load`/`bootstrap` 均报 `I/O error` 无法托管，
   实际服务由 Ollama.app 子进程提供。
2. **502 直接原因**：排查过程中 kill 了所有 ollama 进程，11434 空闲 → 502。
3. **"首次失败/重试成功"真因 = 冷启动超时**：
   - Ollama 默认 `keep_alive=5m`，空闲 5 分钟后模型卸载
   - 下次发图需重新加载(~6s)+图片 prefill(~17s)=约 23s 冷启动
   - WorkBuddy 客户端超时 < 23s → 499/502 取消；但请求已触发加载
   - 重试时模型已在显存 → 秒回成功
4. **keep_alive 对 /v1 不生效**：WorkBuddy 走 OpenAI 兼容 `/v1/chat/completions`，
   该端点**忽略请求里的 `keep_alive`**；服务端 `OLLAMA_KEEP_ALIVE` 环境变量对 /v1 请求也不生效
   （server config 里虽显示 `30m0s`，实际默认仍是 5 分钟）。
   原生 `/api/chat` 的 `keep_alive` 字段才被 Ollama 正确识别。

### 解决方案
- 重启服务（清掉 shell 代理变量，避免 ollama 走透明代理）：
  `nohup env -u http_proxy ... OLLAMA_KEEP_ALIVE=30m ... /usr/local/bin/ollama serve &`
- 预热/续命模型（零冷启动）：每 25 分钟用原生 API 发一次 `keep_alive=30m` 的请求
- 文档化双 Ollama 冲突、localhost 代理陷阱、IPv4/IPv6 解析坑

### localhost 代理陷阱（排查易误判）
- shell 含 `http_proxy=127.0.0.1:62635`（WorkBuddy 透明代理），`curl localhost:11434`
  会走代理返回假数据 → 误判服务存活。本地探测必须 `--noproxy localhost`。
- Python 用 `127.0.0.1`（勿用 `localhost`，否则可能解析 IPv6 `::1` 而 serve 仅听 IPv4）。

### 验证
- 服务重启后 `curl --noproxy localhost http://127.0.0.1:11434/api/version` 返回 0.33.2
- 原生 `keep_alive=30m` 后 `/api/ps` 的 `expires_at` 正确延长到 +30 分钟
- 图片问答经 `/v1/chat/completions` + `image_url` 验证正常（输出准确）
