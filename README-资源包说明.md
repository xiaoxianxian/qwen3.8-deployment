# 📦 Qwen3.8 本地部署资源包

解压后包含以下文件：

| 文件 | 说明 |
|------|------|
| `公众号文章-本地部署Qwen3.8.html` | **公众号推文 HTML 版本**，可直接复制到公众号编辑器 |
| `公众号文章-本地部署Qwen3.8.md` | Markdown 版本（备用） |
| `setup-guide.md` | 完整部署指南（图文版，含 MTP + MLX 提速章节） |
| `verify-ollama.sh` | 一键验证脚本 |
| `CURRENT_CONFIG.md` | 配置快照（参考用，已切到 MLX 原生版） |
| `Modelfile` | **主推配置**：官方 MLX 原生版（`qwen3.8:27b-mlx`） |
| `Modelfile.q5` | **备选配置**：Q5_K_M GGUF（质量略高半档，速度慢约一半） |

---

## 两种模型方案

| 方案 | 来源 | 速度 | 质量 | 复杂度 |
|------|------|------|------|--------|
| **主推：MLX 原生版** | `ollama pull qwen3.8:27b-mlx` | ~40 tok/s | 4-bit（官方优化，日常无感） | 极低，一条命令 |
| 备选：Q5_K_M GGUF | HuggingFace 下 GGUF + 手写模板 | ~20–22 tok/s | 5-bit（略高半档） | 较高，需配多模态模板 |

> 日常使用**直接上 MLX 版**即可；只在你非常在意极限质量、且机器内存宽裕时才考虑 Q5 GGUF 备选。

---

## 使用方式

### 方式一：复制部署包给 AI 一键部署

把压缩包发给任何 AI 编程助手（Claude、Codex、Hermes 等），说：

> "帮我按照 setup-guide.md 部署 Qwen3.8-27B（用 MLX 原生版）"

AI 会自动读取指南并完成部署。

### 方式二：自己阅读后手动部署（MLX 主推）

1. 安装 Ollama：`brew install ollama`
2. 拉取官方 MLX 原生版：`ollama pull qwen3.8:27b-mlx`
3. 用包内 `Modelfile`（已指向 MLX 版），按需改 num_ctx，运行：
   ```bash
   ollama create qwen3.8-local -f ~/models/Modelfile
   ```
4. 运行 `bash verify-ollama.sh` 验证

**若用 Q5 GGUF 备选**：从 <https://huggingface.co/unsloth/Qwen3.8-27B-GGUF> 下载
`Qwen3.8-27B-UD-Q5_K_M.gguf` 与 `mmproj-F16.gguf` 到 `~/models/`，
编辑 `Modelfile.q5` 改为你的实际路径，再 `ollama create qwen3.8-local -f ~/models/Modelfile.q5`。

### 方式三：直接发布公众号

打开 `公众号文章-本地部署Qwen3.8.html`，全选复制，粘贴到公众号编辑器。

---

## 硬件要求

| 配置 | 最低 | 推荐 |
|------|------|------|
| 内存 | 32 GB | 48 GB+ |
| 磁盘 | 30 GB | 50 GB+ |
| 平台 | Intel Mac | Apple Silicon（MLX 版仅 Apple 芯片受益） |

---

部署包获取方式：后台回复【qwen3.8】

有问题？欢迎交流！
