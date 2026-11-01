---
permalink: /config/
title: 当前配置与验证
---

# Qwen3.8-27B 本地部署配置快照

> **✅ 2026-11-02 实测状态（先看这里）**：**Ollama 0.40.11 + `qwen3.8:27b-mlx` 正常可用**。M5 Pro 48GB 上实测 100% GPU、上下文 32768、常驻 20–22 GB、解码 23–35 tok/s、冷启动 2.5–6 s。不需要任何第三方引擎顶替。
>
> ⚠️ **本页 11-01 版本写的是「Ollama MLX runner 病态，主用 MTPLX 顶替」，该结论已于 11-02 推翻并被本页删除。** 真正原因是三件事叠加：① 上下文被设成 262144（不是 Modelfile 的 131072）；② 两个 27B 引擎同时驻留，48 GB 装不下；③ 单轮 prompt 高达 7.8 万 token。完整判定链与推翻过程见 `TROUBLESHOOTING.md` §10。
>
> ⚠️ **48 GB 机器的一条硬边界**：上下文窗口能设多大，不等于能干活。本机预填充实测 348–383 tok/s，所以 32K token 的 prompt 光读入就要 88 秒。**日常压在 32768，单轮输入控制在 1 万 token 以内**，别按 262K 宣传值去塞。

## 模型信息

| 属性 | 值 |
|------|-----|
| 模型名称 | qwen3.8:27b-mlx |
| 类型 | MLX 原生格式，量化 nvfp4（4-bit） |
| 体积 | ~18 GB（运行时常驻 20–22 GB） |
| 参数量 | 27.8B / 架构 qwen3_5 / 模型内置上下文上限 262144 |
| 能力 | tools + vision + thinking |
| 下载源 | https://ollama.com/library/qwen3.8:27b-mlx |
| 国内镜像 | `HF_ENDPOINT=https://hf-mirror.com ollama pull qwen3.8:27b-mlx` |

## 上下文由谁决定（最容易踩的一处）

| 项 | 说明 |
|----|------|
| **权威来源** | `~/Library/Application Support/Ollama/db.sqlite` → `settings.context_length`（即 Ollama.app「设置」里的上下文长度） |
| **优先级** | GUI 设置 **高于** Modelfile 的 `num_ctx`。改了 Modelfile 不生效，先查这里 |
| 本机当前值 | **32768** |
| 查看命令 | `sqlite3 "file:$HOME/Library/Application Support/Ollama/db.sqlite?mode=ro" "select context_length from settings;"` |
| 修改前提 | 必须先**完全退出 Ollama.app**（只 `pkill ollama serve` 不够，GUI 会写回旧值） |
| 校验 | `ollama ps` 的 `CONTEXT` 列，应与上面的值一致 |

> 262144 在 48 GB 机器上必然失败。日志判据：`predicted="24.8 GiB" predicted_num_ctx=262144 available="11.9 GiB" system_limited=true` → `evicting`，表现为「点了没反应 / 模型加载不上」。

## 环境变量配置

本机实测（2026-11-02）：`OLLAMA_CONTEXT_LENGTH` / `OLLAMA_FLASH_ATTENTION` / `OLLAMA_KV_CACHE_TYPE` / `OLLAMA_KEEP_ALIVE` 经 `launchctl getenv` **全为空**，即当前完全没靠环境变量，配置由 GUI 设置 + 模型自带默认值驱动。

需要设时的注意事项：

| 事项 | 说明 |
|------|------|
| `launchctl setenv` 不持久 | 重启即丢，本机已多次验证 |
| plist 更不可靠 | `~/Library/LaunchAgents/com.ollama.serve.plist` 是 `RunAtLoad=false` / `KeepAlive=false`，从未生效；实际 server 由 Ollama.app 拉起 |
| `OLLAMA_KV_CACHE_TYPE=q8_0` | 会**主动引入** int8 KV 量化（有翻转 token 的实测记录），当前 f16 未压缩是更稳的默认，不建议为省内存盲开 |
| `OLLAMA_KEEP_ALIVE` | 本机冷重载实测只需 2.5–6 s，5 分钟默认值够用，不必改 |

## 硬件需求

| 配置项 | 要求 |
|--------|------|
| 内存 | ≥ 32 GB 可跑（上下文 16K～32K）；**≥ 64 GB 才建议把 num_ctx 提到 131072** |
| 芯片 | Apple Silicon（M 系列） |
| 磁盘空间 | 建议 30 GB+（含 Ollama 运行时） |

## 性能基准（M5 Pro 48GB / Ollama 0.40.11 / macOS 27.2 实测）

| 指标 | 实测值 |
|------|--------|
| 解码（200 token 代码生成） | 34.9 tok/s |
| 解码（20–30 token 短答） | 23–24 tok/s |
| 预填充 | 348–383 tok/s（已压到 M5 Pro GPU 算力上限） |
| 冷启动加载 | 2.5–6 s（keep_alive 存续期内热态 0 s） |
| 常驻内存 | 20–22 GB，100% GPU |
| 空闲 60 s 后首请求 | 0.46 s（`iogpu.disable_wired_collector=1` 时） |
| 工具调用 | `finish_reason: tool_calls`，参数正确 |
| 视觉 | 正常（单张图约 100–130 prompt token） |

**上下文成本（按 360 tok/s 预填充折算，这是选窗口大小的唯一依据）**

| 单轮 prompt | 光读入耗时 | 能否干活 |
|---|---|---|
| 2 K | ~6 s | 顺畅 |
| 4 K | ~14 s | 可以 |
| 10 K | ~29 s | 勉强 |
| 32 K（吃满 32768 窗口） | ~88 s | 不能 |
| 78 K | ~217 s | 物理上不行 |

## 已安装工具

| 工具 | 状态 | 版本 |
|------|------|------|
| Ollama（Ollama.app 托管，GUI 拉起 server） | ✅ 运行中 | 0.40.11 |
| Python | ✅ | 3.11.x |
| pip | ✅ | 24.x |

> 本机**不要**再装第二个 27B 引擎（MTPLX / 其他）与 Ollama 同跑：48 GB 装不下两份，会直接把两个都拖成 swap。MTPLX 已于 2026-11-02 彻底卸载。

## 注意事项

1. **MLX 不识别 GGUF**：必须用原生 MLX 格式（`ollama pull qwen3.8:27b-mlx`）。
2. **不要手动加 `draft_num_predict`**：0.40.11 的 MLX runner **已默认自适应投机解码**，官方标签原样最快。本机对拍：官方标签 34.9 tok/s vs 手动加 `draft_num_predict 3` 只有 28.0 tok/s。此项仅对 GGUF 路线仍需显式开启（见 `TROUBLESHOOTING.md` §5）。
3. **`iogpu.disable_wired_collector=1` 重启失效**：治「空闲后首个请求要重新从 swap 页入权重」，开机需重跑一次 `sudo sysctl iogpu.disable_wired_collector=1`。
4. **使用 127.0.0.1 而非 localhost**：避免代理与 IPv6 路由问题。
5. **跨版本测试 Ollama 必须隔离模型目录**：旧版二进制启动 GC 会清空新版模型库，见 `TROUBLESHOOTING.md` §11。
