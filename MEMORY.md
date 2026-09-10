# 项目长期记忆：本地部署 Qwen3.8-27B

> 本文件记录跨会话、跨 agent 可复用的项目事实与约定。迭代前先读此文件，避免重复踩坑。
> 同步副本：WorkBuddy 工作区记忆 `~/.workbuddy/memory/MEMORY.md` 与本文件口径一致（改动后两边同步）。
> 最后更新：2026-09-11
> 2026-09-11 同步：公众号文章（md/html）+ GitHub（README/Modelfile/CURRENT_CONFIG）已刷新为 MLX 原生主推，并补入 2026-09-10 A/B 稳定性结论（单跑 131k+MTP 稳、并发才是 OOM 真凶、MLX 与 Q5 质量打平）。

## 一、项目定位
- 在 Mac（Apple Silicon）本地部署 **Qwen3.8-27B** 大模型，通过 OpenAI 兼容端点（`/v1`）接入各类 Agent 工具：WorkBuddy、Claude Desktop、Hermes Agent、Codex 等。
- 当前主要角色：① 兜底模型（API 速率限制时的本地退路）；② h3web 二期对话编排层的「导演 LLM」（见 H3 项目 MEMORY.md）。

## 二、模型与部署（已固化）
- **模型名**：`qwen3.8:27b-mlx`
  - **实际指向官方 `qwen3.8:27b-mlx` 原生 MLX 量化版（18GB）**，原生 MLX 引擎 + 自带 MTP 投机解码 + 多模态 vision。
  - ⚠️ 旧 `qwen3:27b Q5_K_M` GGUF 已弃用。
- **推理服务**：Ollama **0.33.3**，监听 `http://localhost:11434`。
- **WorkBuddy 配置**：`~/.workbuddy/models.json` → `qwen3.8:27b-mlx.url = http://localhost:11434/v1`（直连，不走代理）。
- **num_ctx**：**131072**（实测最佳平衡：28GB 内存、100% GPU、~9.7 tok/s 裸速基线）。
- **多模态**：含 mmproj 视觉支持，可走 `/v1` 端点发图（需 Modelfile 显式模板，见第四节）。

## 三、提速与关键开关
- **MTP 投机解码（已启用）**：Modelfile 含 `PARAMETER draft_num_predict 3`；代码生成实测 ~21 → **37.8 tok/s decode**（约 3.9×）。
  - ⚠️ 旧值 65536 会触发 400 报错（图片+长历史溢出）；262144 太慢（~3 tok/s），不推荐。
- ⚠️ **MLX 后端不可用（已验证 2026-09-07）**：Ollama 0.33.3 二进制虽编译了 MLX 库，但正确开关是 `OLLAMA_LLM_LIBRARY=mlx`（不是 `OLLAMA_BACKEND`）；实测强制后 runner 仍走 `ggml_metal` + llama.cpp，**Qwen3.8 架构不在 MLX 支持列表，静默回退 Metal**。结论：对 qwen3.8 提速只有 MTP 一条路，别再试 MLX。
- **推理档位实测**：high(~19s, 质量最好) > medium(~22s) > low(~14s, 质量一般)；xhigh 完全不可用（见坑）。

## 四、致命坑（必读，少踩一个都是赚）
1. **最致命（2026-09-04 修复）**：该模型不内嵌 chat_template，Ollama 退回裸 `{{ .Prompt }}`，导致走 `/v1` 发图报 `No data iterator found for token: <|video_pad|>`。必须在 Modelfile **显式写 Qwen 多模态模板**（用 `{{ .Content }}` 让 Ollama 自动渲染多模态内容）。
   - ⚠️ Ollama 模板引擎**不支持数组索引/切片**（`{{ .Content[0] }}` 会报 `bad character U+005B '['`）。
2. **xhigh bug**：Ollama 0.33.x 中 xhigh 对所有请求（含纯文字）报 500（GitHub #17906，PR #17917 未合并，v0.33.3 未修复）。用 high 档。
3. **thinking 模式空回复**：Qwen3.8 默认开启 thinking，调用方需传 `options.num_predict ≥ 2000` 或 `think=false`，否则会空回复。
4. **代理陷阱**：本地探测必加 `--noproxy localhost` 并用 127.0.0.1（shell 有 `http_proxy=127.0.0.1:62635` 透明代理陷阱）。

## 五、运维要点（本地 Qwen3.8）
- 服务若 502：端口 11434 无人监听，用 `nohup env -u http_proxy ... /usr/local/bin/ollama serve &` 重启（清代理变量）。
- 冷启动：keep_alive 默认 5m，重载+推理约 23s > WorkBuddy 超时 → 表现「首次失败/重试成功」。重试时模型已热。
- `/v1` 端点忽略 keep_alive；原生 `/api/chat` 的 keep_alive 才有效（可每 25min 续命 30m）。
- **智能分流代理已弃用**：原计划 `~/models/ollama_strip_proxy.py` 走 11435，但 WorkBuddy 沙箱会强制杀 11435 端口；且 Ollama 0.33.x 已原生支持 `reasoning_effort=high`，无需代理中转。

## 六、关键环境变量
`OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`

## 七、项目目录导航（~/Documents/AI项目/本地部署Qwen3.8/）
- `Modelfile` / `Modelfile.local` / `Modelfile.mlx` — 当前与历史模板
- `CURRENT_CONFIG.md` — 当前固化配置总览
- `CHANGELOG.md` — 变更记录
- `README.md` — 部署指南
- `调优与避坑指南.md` / `性能对比与量化指南.md` — 详细优化文档
- `公众号文章-本地部署Qwen3.8.md/.html` — 对外推文（双版本）
- `verify-ollama.sh` — 自检脚本
- `.git` 已初始化（commit 549b46c 等）

## 八、参考仓库
- `t64c6d7mc5-debug/qwen3.8-27b-apple-silicon-agent`：用 mlx-serve + Qwen3.8-27B-MLX-Serve-8bit + Native MTP depth 8，M5 Max 64GB 实测 18.9→65.9 tok/s（~3.5×）。MTP 必须用绝对 --model 路径否则静默 mtp_loaded:false。
