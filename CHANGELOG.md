# Qwen3.8-27B 部署变更记录

## 2026-09-09

### 修正内容
- 更新模型推荐为 MLX 原生版 `qwen3.8:27b-mlx`（替代 GGUF + Q5_K_M）
- 修正文件大小：MLX 18GB nvfp4，非 GGUF 20.7GB
- 修正首 token 延迟描述：MLX 一直是 3-4 秒，GGUF 在 swap 时才分钟级
- 补充国内镜像方案（hf-mirror.com、ModelScope）
- 添加「走过的弯路」章节，包含 6 个常见问题及根因分析

### 新增内容
- 国内镜像下载指引
- MTP 投机解码配置说明（draft_num_predict=3）
- 全局环境变量说明（OLLAMA_CONTEXT_LENGTH 等）
- Agent 工具切换模型的真实命令示例

### 删除内容
- 废弃的 `deepseek-chat` 模型名引用
- 不存在的 CLI 命令（如 `workbuddy model add`）

## 2026-09-08

### 初始发布
- 创建公众号推文（Markdown + HTML 双版本）
- 提供 HuggingFace 官方下载链接
- 基础 Ollama 安装和配置指导
