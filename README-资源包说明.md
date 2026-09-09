# 本地部署 Qwen3.8 资源包说明

## 本资源包包含

```
Qwen3.8本地部署指南.tar.gz
├── 公众号文章-本地部署Qwen3.8.md      # 文章 Markdown 源文件
├── 公众号文章-本地部署Qwen3.8.html     # 文章 HTML 版本（可直接复制发布）
├── setup-guide.md                    # 部署操作指南
├── verify-ollama.sh                  # 验证脚本
├── CURRENT_CONFIG.md                 # 当前配置快照
├── Modelfile                         # Ollama 模型配置模板
└── CHANGELOG.md                      # 变更记录
```

## 文件用途

| 文件 | 用途 |
|------|------|
| `公众号文章-本地部署Qwen3.8.html` | 公众号发布用，复制全文粘贴即可 |
| `setup-guide.md` | 部署操作手册，逐步指导 |
| `verify-ollama.sh` | 验证安装是否成功 |
| `CURRENT_CONFIG.md` | 当前配置参数速查 |
| `CHANGELOG.md` | 变更记录，了解优化过程 |

## GitHub 仓库

部署方案已开源：https://github.com/xiaoxianxian/qwen3.8-local-deployment

## 使用方法

1. 解压：`tar -xzf Qwen3.8本地部署指南.tar.gz`
2. 阅读 `setup-guide.md` 按步骤部署
3. 使用 `verify-ollama.sh` 验证安装
4. 参考 `公众号文章-本地部署Qwen3.8.html` 了解完整方案

## 注意事项

- 国内用户建议使用 hf-mirror.com 或 ModelScope 镜像下载模型
- 模型推荐：MLX 原生版 `qwen3.8:27b-mlx`（速度快 2 倍）
- 硬件要求：≥ 24GB 内存（MLX），≥ 32GB 内存（GGUF）
