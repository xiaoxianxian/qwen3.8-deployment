---
permalink: /troubleshooting/
title: 踩坑排查手册
---

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
| 系统更新后 Ollama MLX 版全挂（探针 0 字节 / 每请求 2-5 分钟），小 GGUF 正常 | [10](#10-macos-27-系统更新后-ollama-mlx-runner-卡死) |

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

## 10. macOS 27 系统更新后 Ollama MLX runner 卡死

**现象**：系统自动更新（macOS 27.x 点版本）+ 重启完成后，本地 `qwen3.8:27b-mlx` 全挂：探针 0 字节，或每请求 2-5 分钟；客户端报 `Provider has been unresponsive ... stale attempts`。注意 `/api/version` 秒回、`/api/ps` 显示模型已加载**都不证明推理活着**，必须实测一次 chat 探针下结论。

**判定链（照序做，哪步通了就停）**：

1. **先排除 swap**：`sysctl vm.swapusage`——打满（free 个位数 GB）就先杀大户进程 / 重启清空，再复测；重启清完仍 0 字节才进第 2 步。
2. **引擎隔离（关键一步）**：清重启 Ollama（`pkill -f Ollama && open -a Ollama`）后，测同机走 llama.cpp/Metal 引擎的小 GGUF 模型（1-4B 档，现成没有就 pull 一个）。**测前必须清重启**——27b MLX runner 还占着 GPU、runner 串行时小模型会排在爬行后面，第一次测必假阳性。
   - 小模型正常 + 27b-mlx 卡 = **只坏 Ollama MLX runner，系统 Metal 没全挂** → 版本线整条排除、sysctl 线（27.2 起）排除，直接上第 4 步 MTPLX 顶替。
   - 小模型也慢 = 系统层 Metal 问题，先取证：`softwareupdate --history` + `last reboot` 对时间（重启落在某次 OS 更新装完后几分钟内 = 这次更新完成时 Metal 运行时回归高度可疑）。
3. **日志指纹**（前台起 `ollama serve` 看，Ollama.app 会吞掉 runner 的 stderr）：`MLX engine initialized` + `Loaded tensors` 正常，但 `Prompt processing progress` 几百 tok/s 爬行 + GIN 500 = 推理层被 GPU 层拖死；`prefix_cache.go` 的 `cache miss total=N matched=M` 行——**total 逐请求增长（数万且越滚越大）+ matched 占比 <1% = 病态重放 prefill**（前缀缓存子系统整个失效，每请求重算全池，单请求 2-5 分钟）。别去反推「total 数万 token 的 prompt 是哪来的」，它不是 prompt 长度。
4. **版本隔离（可选，确认 Ollama 无责后省时间）**：旧版 Ollama DMG 复测，新旧同病 = 根因不在 Ollama 版本；`sudo sysctl iogpu.disable_wired_collector=1` 在 **macOS 27.2 起已实测无效**（27.0/27.1 老事件仍可试，验证标准 = 重启 Ollama 后第 2 次探针秒级出 token），别再在这条线上花时间。

**顶替：MTPLX 引擎（同权重、独立引擎，实测不受 Ollama runner 缓存病影响）**：

```bash
# 起 MTPLX（OpenAI 兼容端点 8000）
<你的-mtplx-venv>/bin/mtplx serve --model Youssofal/Qwen3.8-27B-MTPLX-Optimized-Speed --port 8000
# ready 判定轮询 /health（{"ok":true,...}），别 grep 启动日志（日志提前打 ready 但端口没监听）
```

- 端点 `http://127.0.0.1:8000/v1`，model id `mtplx-qwen38-27b-optimized-speed`。
- **两引擎绝不同跑**（Ollama 27b ~34GB 常驻 + MTPLX peak ~23GB > 48GB）：起 MTPLX 前把 Ollama 全停（含 app 的 serve 子进程）；回 Ollama 时 `pkill -f 'mtplx serve'`（杀不掉就 `lsof -nP -iTCP:8000 -sTCP:LISTEN -t | xargs kill -9`）再 `open -a Ollama`。
- 字段差异：MTPLX 思考关不掉（思考进 `reasoning_content`），但**正文仍在 `content`**，OpenAI 形态客户端读 content 正常。
- 验收基线（M5 Pro 48GB 对拍值）：Ollama 档 ttft 0.17s / ~27-30 tok/s；MTPLX 档 ttft ~1.1s / ~23 tok/s。MTPLX 短探针 e2e ~2s、decode ≥20 tok/s = 顶替到位。
- 要重启自动拉起：挂 LaunchAgent（Label `com.user.mtplx`、RunAtLoad + KeepAlive，ProgramArguments 指 mtplx venv 的 `mtplx serve --model ... --port 8000`，日志写 `~/models/mtplx_serve.{out,err}.log`），`launchctl load` 后 `launchctl list | grep mtplx` 验。

**2026-11-01 事件实录（M5 Pro 48GB / macOS 27.2 可对照）**：0.40.13 / 0.40.12 / 0.40.11 三版本 300s 探针全零字节 → 版本线排除；`qwen3:4b`（GGUF）14s 正常 → 病在 Ollama MLX runner；serve 日志 prefill 池 36k→74k 逐请求增长、`cache miss total=74246 matched=287`（命中 0.4%）；sysctl 无效；MTPLX 同机 1.7s 出「收到」/ ~28 tok/s 正常 → 切 MTPLX（LaunchAgent 常驻）、Ollama 保持停。待 Ollama 后续版本或 27.2.x 修复后：Ollama 重启 + 探针验收 → 停 MTPLX → 端点切回，并更新本页与 `CURRENT_CONFIG.md`。

---

## MLX 与 GGUF / GSQ 并发稳定性（补充）

MLX 单跑极稳：131072 上下文 + MTP 下，5 维质量题 2 轮 10/10 全过、零 OOM（2026-09-10 A/B 实测）。GSQ / GGUF 路线（Q5、IQ3 等）同属 llama.cpp 引擎，单跑 131K 上下文也稳定。此前偶发的"间歇性显存溢出"根因是**多个会话/进程同时调用同一个 MLX 模型**，KV 缓存显存叠加溢出，与 128K 上下文无关。

**部署建议**：

- 日常单跑 / 短中交互：`qwen3.8:27b-mlx`（MLX，满血 131k + MTP）
- 长 agent 多会话并发：`qwen3.8-q5`（GGUF + llama.cpp，并发更稳）；GSQ IQ3 同为 llama.cpp 路径，并发表现与 Q5 一致，只是更省显存、速度更慢
- 避免多个客户端同时并发调同一个 MLX 模型，错峰使用
