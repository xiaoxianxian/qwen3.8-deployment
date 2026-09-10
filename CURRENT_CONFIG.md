# Qwen3.8-27B 本地部署配置快照

## 模型信息

| 属性 | 值 |
|------|-----|
| 模型名称 | qwen3.8:27b-mlx |
| 类型 | MLX 原生格式 (nvfp4) |
| 文件大小 | ~18 GB |
| 下载源 | https://ollama.com/library/qwen3.8:27b-mlx |
| 国内镜像 | `HF_ENDPOINT=https://hf-mirror.com ollama pull qwen3.8:27b-mlx` |

## 环境变量配置 (全局生效)

```bash
OLLAMA_CONTEXT_LENGTH=131072    # 上下文长度：128K
OLLAMA_FLASH_ATTENTION=1        # 启用 FlashAttention
OLLAMA_KV_CACHE_TYPE=q8_0       # KV 缓存精度：Q8_0
OLLAMA_KEEP_ALIVE=30m           # 模型保持加载时间
```

**设置方式：**
```bash
launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_KEEP_ALIVE 30m
pkill -f "ollama serve" && sleep 2 && open -a Ollama
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
