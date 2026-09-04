# 📦 Qwen3.8 本地部署资源包

解压后包含以下文件：

| 文件 | 说明 |
|------|------|
| `公众号文章-本地部署Qwen3.8.html` | **公众号推文 HTML 版本**，可直接复制到公众号编辑器 |
| `公众号文章-本地部署Qwen3.8.md` | Markdown 版本（备用） |
| `setup-guide.md` | 完整部署指南（图文版） |
| `verify-ollama.sh` | 一键验证脚本 |
| `CURRENT_CONFIG.md` | 配置快照（参考用） |
| `Modelfile` | 模型配置文件模板 |

---

## 使用方式

### 方式一：复制部署包给 AI 一键部署

把压缩包发给任何 AI 编程助手（Claude、Codex、Hermes 等），说：

> "帮我按照 setup-guide.md 部署 Qwen3.8-27B"

AI 会自动读取指南并完成部署。

### 方式二：自己阅读后手动部署

1. 安装 Ollama：`brew install ollama`
2. 下载模型文件到 `~/models/`
   - 主模型：https://huggingface.co/unsloth/Qwen3.8-27B-GGUF
   - 选择 `Qwen3.8-27B-UD-Q5_K_M.gguf`
   - 投影器：`mmproj-F16.gguf`
3. 编辑 `Modelfile`，修改为你的实际路径
4. 运行 `ollama create qwen3.8-local -f ~/models/Modelfile`
5. 运行 `bash verify-ollama.sh` 验证

### 方式三：直接发布公众号

打开 `公众号文章-本地部署Qwen3.8.html`，全选复制，粘贴到公众号编辑器。

---

## 硬件要求

| 配置 | 最低 | 推荐 |
|------|------|------|
| 内存 | 32 GB | 48 GB+ |
| 磁盘 | 30 GB | 50 GB+ |
| 平台 | Intel Mac | Apple Silicon |

---

部署包获取方式：后台回复【qwen3.8】

有问题？欢迎交流！
