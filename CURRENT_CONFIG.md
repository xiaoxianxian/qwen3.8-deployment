---
permalink: /config/
title: 当前配置与验证
---

# Qwen3.8-27B 本地部署配置快照

> **⚠️ 2026-11-01 引擎状态（先看这里）**：macOS 27.2 自动更新后，Ollama 的 MLX runner 在本机 `qwen3.8:27b-mlx` 上病态（0.40.13 / 0.40.12 / 0.40.11 三版本同病，病态 prefill 池 36k→74k 逐请求增长、前缀缓存命中 0.4%，单请求 2-5 分钟）。**当前主用 = MTPLX 引擎**（同份 MLX 权重，OpenAI 兼容端点 `http://127.0.0.1:8000/v1`，model id `mtplx-qwen38-27b-optimized-speed`，LaunchAgent 常驻，实测 1.7s / ~28 tok/s）；**Ollama 保持停**（两引擎绝不同跑，48GB 装不下）。下方 Ollama 配置在 Ollama 修复回用后继续有效。完整配方与 11-01 事件实录：`TROUBLESHOOTING.md` §10（自含完整判定链 + MTPLX 顶替步骤）；本地另有详细取证档案 `docs/references/macos-27-mlx-stall.md`（内部档案，不进公开仓）。

## 模型信息

| 属性 | 值 |
|------|-----|
| 模型名称 | qwen3.8:27b-mlx |
| 类型 | MLX 原生格式 (nvfp4) |
| 文件大小 | ~18 GB |
| 下载源 | https://ollama.com/library/qwen3.8:27b-mlx |
| 国内镜像 | `HF_ENDPOINT=https://hf-mirror.com ollama pull qwen3.8:27b-mlx` |

## 环境变量配置（实测核对：2026-10-23）

> ⚠️ **文档与实机曾不一致，已校正。** 下述四项通过 `launchctl getenv` 实测**当前均为空**：
> `OLLAMA_CONTEXT_LENGTH` / `OLLAMA_FLASH_ATTENTION` / `OLLAMA_KV_CACHE_TYPE` / `OLLAMA_KEEP_ALIVE`。
> 原因：`launchctl setenv` **不跨重启持久化**，重启后失效。本机当前实际配置完全由 `Modelfile.mlx` 驱动，见下。

### 当前实际生效配置（来自 Modelfile.mlx，2026-10-23 核对）

| 项 | 值 | 说明 |
|----|-----|------|
| num_ctx | 131072 | 上下文上限（等同文档想设的 128K，但由 Modelfile 而非环境变量提供） |
| draft_num_predict | 3 | **MTP 投机解码开着**（thr3e 对照实验里为隔离变量专门关掉的；本机实测接受率 0.6–0.85） |
| temperature | **1.0** | ⚠️ 原 0.7，已对齐官方模型卡（卡值=1.0）。thr3e 结论：temp 过低会让 Qwen 卡 THINK 循环 |
| top_p / top_k / min_p | 0.95 / 20 / 0.0 | 与官方卡一致 |
| KV 缓存精度 | **默认 f16（未压缩）** | 文档曾写 `q8_0`，但 `OLLAMA_KV_CACHE_TYPE` 实测为空 → **KV 实际未量化**。这反而更安全：thr3e 实测 int8 KV 会翻转（可恢复）、int4 不恢复 |

### 若确实需要全局环境变量（注意持久化）

`launchctl setenv` 重启即丢。要持久化需写 plist 或在 Modelfile 里逐模型设。且：
- `OLLAMA_KV_CACHE_TYPE=q8_0` 会**主动引入** int8 KV 量化——thr3e 证明这档会翻转 token（虽可恢复）。当前 f16 无压缩是更稳的默认，**不建议为省显存盲目开 q8_0**，除非真有显存压力。
- FlashAttention 在 Apple Silicon MLX 路径通常默认开启，无需该变量强制。
- `num_ctx` 已由 Modelfile 覆盖，环境变量非必需。

```bash
# 仅当确有需求时。重启不持久，需另配 plist。
launchctl setenv OLLAMA_KEEP_ALIVE 30m
```

## 硬件需求

| 配置项 | 要求 |
|--------|------|
| 内存 | ≥ 24 GB (MLX)，≥ 32 GB (GGUF) |
| 芯片 | Apple Silicon (M 系列) |
| 磁盘空间 | 建议 30 GB+ (含 Ollama 运行时) |

## 性能基准 (M5 Pro 48GB)

| 指标 | MLX 原生版 | GGUF Q5_K_M |
|------|------------|-------------|
| 生成速度 | 40.8 tok/s | 22.4 tok/s |
| 首 token 延迟 | 3-4 秒 | 分钟级 (swap) |
| 内存占用 | ~18 GB | ~20.7 GB |

## 已安装工具

| 工具 | 状态 | 版本 |
|------|------|------|
| Ollama | ✅ 运行中 | 0.33.3 |
| Python | ✅ | 3.11.x |
| pip | ✅ | 24.x |

## 注意事项

1. **MLX 不识别 GGUF**：必须使用原生 MLX 格式 (`ollama pull qwen3.8:27b-mlx`)
2. **MTP 投机解码默认关闭**：需在 Modelfile 中设置 `draft_num_predict 3`
3. **keep_alive 对 /v1 API 无效**：用全局环境变量 `OLLAMA_KEEP_ALIVE`
4. **使用 127.0.0.1 而非 localhost**：避免代理路由问题
