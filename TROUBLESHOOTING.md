# Qwen3.8 本地部署排查手册（TROUBLESHOOTING）

> 按现象索引的排查手册，内容来自 M5 Pro 48GB / macOS 实测踩坑记录（2026-09）。
> 每个问题包含：现象 → 根因 → 解决。

## 快速索引

| 现象 | 跳转 |
|------|------|
| 读长文档报 `context length exceeded`，或模型"记不住" | [1](#1-上下文长度默认只有-4096) |
| MLX 推理大上下文时报 500 + `context canceled` | [2](#2-mlx-超时-500-context-canceled) |
| 设了 `OLLAMA_LLM_LIBRARY=mlx` 想让 GGUF 走 MLX，没效果 | [3](#3-gguf-无法走-mlx-引擎) |
| 发图报 `400 ... No data iterator found for token: <|video_pad|>` | [4](#4-图片识别-400no-data-iterator) |
| 速度不达预期，日志显示 `specu: no` | [5](#5-mtp-投机解码默认关闭) |
| 设了 keep_alive，每次调用仍要等冷启动 | [6](#6-keep_alive-对--v1-端点不生效) |
| `curl localhost:11434` 通，但程序连接失败 | [7](#7-localhost-代理与-ipv6-陷阱) |
| 调用成功但回复内容为空 | [8](#8-回复内容为空) |
| 响应慢（整句蹦出，一个字一个字往外挤变慢） | [9](#9-响应速度慢) |

---

## 1. 上下文长度默认只有 4096

**现象**：读长文档时报 "context length exceeded"，或者模型表现得像"记不住东西"。

**根因**：模型支持 262K 上下文，但 Ollama 默认值只有 4096。超过部分被**静默截断**——不报错，只是模型"看不见"后面的内容。

**解决**：全局设置并重启 Ollama：

```bash
launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
pkill -f "ollama serve" && sleep 2 && open -a Ollama
```

验证：`ollama show qwen3.8:27b-mlx` 应输出 `num_ctx 131072`（或 Modelfile 中 `PARAMETER num_ctx 131072`）。

---

## 2. MLX 超时 500 `context canceled`

**现象**：MLX runner 处理大上下文（32k+）时，推理中途进程被杀，报 `context canceled` 和 500 Internal Server Error。

**根因**：已知回归 bug，[GitHub Issue #16081](https://github.com/ollama/ollama/issues/16081)。机理：服务器每 10 秒对 runner 做一次健康检查，该检查排队在漫长的推理任务之后；大上下文推理忙起来时，检查等满 10 秒等不到响应，进程被判"失联"强杀。回归自 **v0.23.1/v0.23.2**（实测 0.22.1 正常）。

**解决**：升级 Ollama。修复为 [PR #16086](https://github.com/ollama/ollama/pull/16086)（commit `2b9e024`，2026-05-11 合入）——健康检查改为读缓存的内存快照，不再阻塞等待推理线程。**v0.30+ 已包含修复**；本项目实测 v0.33.3 正常。

---

## 3. GGUF 无法走 MLX 引擎

**现象**：设置了 `OLLAMA_LLM_LIBRARY=mlx` 想强制 GGUF 模型用 MLX 引擎提速，结果完全无效，模型仍走 Metal。

**根因**：MLX runner 不认 GGUF 格式权重。GGUF 只能用 llama.cpp（Metal 后端）。

**解决**：按格式选引擎，不要强设环境变量：

- GGUF 格式 → 走 Metal（`OLLAMA_LLM_LIBRARY` 保持默认）
- MLX 原生格式（如 `qwen3.8:27b-mlx`）→ 自动走 MLX 引擎，无需任何环境变量

> 注：早期结论"Ollama 的 MLX 引擎对该模型不可用"仅指 GGUF 强制走 MLX 这条路；MLX 原生格式走原生 MLX 引擎正常且更快（约 2×）。

---

## 4. 图片识别 400：No data iterator

**现象**：走 `/v1` 端点发图时报 `400 BadRequestError: No data iterator found for token: <|video_pad|>`。

**根因**：Qwen3.8 的 GGUF 版本不内嵌 chat template，Ollama 退回裸模板 `{{ .Prompt }}`，不懂图像 token 处理逻辑。

**解决**：在 Modelfile 中显式写入 Qwen 多模态模板。关键点：用 `{{ .Content }}` 让 Ollama 自动渲染多模态内容；**不能用 `{{ .Content[0] }}`**——Ollama 模板引擎不支持数组索引/切片。完整模板见仓库 [Modelfile](./Modelfile) 或部署文章。

MLX 原生版（`qwen3.8:27b-mlx`）自带视觉投影，无需此步骤。

---

## 5. MTP 投机解码默认关闭

**现象**：速度不达预期。`ollama show` 或服务日志显示 `specu: no`。

**根因**：Qwen3.8 自带 MTP 投机解码头，但 GGUF 与 MLX 两条路**默认都是 `draft_num_predict=0`（关）**，需要显式开启。

**解决**：Modelfile 中设置：

```dockerfile
PARAMETER draft_num_predict 3
```

- 实测（Q5 GGUF 基线）：代码生成 11.7 → 21.6 tok/s（+85%）；建议取值 3，>6 反而掉速
- 验证：日志出现 `specu: n_max=3`，draft acceptance 0.6~0.85
- 输出无损，属免费提速

---

## 6. keep_alive 对 /v1 端点不生效

**现象**：设置了 `OLLAMA_KEEP_ALIVE=30m`，但每次调用仍等约 6 秒冷启动（模型重新加载）。

**根因**：OpenAI 兼容端点 `/v1/chat/completions` **忽略请求里的 keep_alive 参数**；服务端环境变量对该端点的按请求控制同样不生效。keep_alive 默认 5 分钟，超时即卸载模型。

**解决**：

```bash
# 服务端全局基线（用户级，无需 sudo）
launchctl setenv OLLAMA_KEEP_ALIVE 30m
# 重启 Ollama 生效
```

- 需要按请求控制时，用 Ollama 原生 API `/api/chat`（支持 `keep_alive` 参数）
- /v1 端点依赖上面的全局环境变量

---

## 7. localhost 代理与 IPv6 陷阱

**现象**：`curl localhost:11434` 能访问，但程序连接失败或返回异常数据。

**根因**：

1. 系统代理（`http_proxy` 等环境变量）会拦截 `localhost` 请求
2. `localhost` 可能解析到 IPv6 `::1`，而 Ollama 只监听 IPv4

**解决**：

- 一律用 `127.0.0.1:11434`，不用 `localhost:11434`
- 本地探测加 `--noproxy '*'`（curl）或清掉代理变量再启动 `ollama serve`

---

## 8. 回复内容为空

**现象**：调用成功（HTTP 200），但 `content` 为空字符串。

**根因**：Qwen3.8 默认开启推理思考（thinking），先消耗 token 预算；`max_tokens` 偏小时思考阶段就把预算吃光，正文输出为空。

**解决**：任选其一：

- 传 `max_tokens: 2000` 或更大
- 传 `think: false` 关闭思考模式

---

## 9. 响应速度慢

**排查顺序**：

```bash
# 1. 确认模型常驻（避免冷启动）
ollama ps

# 2. 检查是否触发 swap（有用量说明内存不够，会出现分钟级首 token 延迟）
sysctl vm.swapusage

# 3. 确认 MTP 已开启（见第 5 节）
grep "specu" ~/.ollama/logs/server.log | tail
```

内存紧张的缓解手段：下调 `num_ctx`（131072 → 65536），或换更小量化档（Q4_K_M）。

---

## MLX 与 GGUF / GSQ 并发稳定性（补充）

MLX 单跑极稳：131072 上下文 + MTP 下，5 维质量题 2 轮 10/10 全过、零 OOM（2026-09-10 A/B 实测）。GSQ / GGUF 路线（Q5、IQ3 等）同属 llama.cpp 引擎，单跑 131K 上下文也稳定。此前偶发的"间歇性显存溢出"根因是**多个会话/进程同时调用同一个 MLX 模型**，KV 缓存显存叠加溢出，与 128K 上下文无关。

**部署建议**：

- 日常单跑 / 短中交互：`qwen3.8:27b-mlx`（MLX，满血 131k + MTP）
- 长 agent 多会话并发：`qwen3.8-q5`（GGUF + llama.cpp，并发更稳）；GSQ IQ3 同为 llama.cpp 路径，并发表现与 Q5 一致，只是更省显存、速度更慢
- 避免多个客户端同时并发调同一个 MLX 模型，错峰使用
