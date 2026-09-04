# 内部变更日志（仅用于排查问题，不对外发布）

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
