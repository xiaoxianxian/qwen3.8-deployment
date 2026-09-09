# GitHub 仓库内容规范

## 📌 核心原则

**GitHub 仓库只放部署相关文件，不包含：**
- ❌ 公众号文章（HTML/Markdown）
- ❌ 开发记录（CHANGELOG.md）
- ❌ 开发想法（IDEA.md）
- ❌ 调试脚本（scripts/, docs/）
- ❌ 内部测试文档（调优与避坑指南.md）
- ❌ 备份文件（Modelfile.*.bak-* 等）

**用户可以获取的内容：**
- ✅ 完整部署教程（README.md）
- ✅ 配置模板（Modelfile）
- ✅ 验证脚本（verify-ollama.sh）
- ✅ 参数速查（CURRENT_CONFIG.md）
- ✅ 部署包（Qwen3.8本地部署指南.tar.gz）

## 📂 仓库结构

```
qwen3.8-local-deployment/
├── README.md                     # ⭐ 完整部署教程（主文档）
├── setup-guide.md                # 详细步骤说明（备选参考）
├── CURRENT_CONFIG.md             # 本机配置快照
├── Modelfile                     # Ollama 模型配置模板
├── verify-ollama.sh              # 一键验证脚本
├── README-资源包说明.md          # 资源包说明
├── Qwen3.8本地部署指南.tar.gz    # 部署包（下载即用）
└── .gitignore                    # Git 忽略规则
```

## 📝 README.md 编写规范

GitHub 的 README.md 应该是**完整的技术教程**，包含：
- 适用对象和环境要求
- 快速开始步骤
- 详细的安装命令
- API 调用示例
- 性能数据
- 常见问题解答

**不要包含：**
- 个人感受或评价
- 踩坑故事
- 口语化表达

## 📰 公众号文章定位

公众号文章是**口语化的经验分享**，包含：
- 个人心路历程
- 踩坑填坑过程
- 主观评价和建议
- 与读者的互动感

**不与 GitHub README 重复**，而是作为补充和延伸。

## 📦 部署包内容

部署包（.tar.gz）只包含：
- README.md（部署教程）
- setup-guide.md（详细步骤）
- CURRENT_CONFIG.md（参数速查）
- Modelfile（配置模板）
- verify-ollama.sh（验证脚本）
- README-资源包说明.md（使用说明）

**不包含：**
- 公众号文章（HTML/Markdown）
- 任何开发记录或内部文档

## 🔍 验证清单

发布前检查：
- [ ] GitHub 仓库无公众号文章
- [ ] GitHub 仓库无开发记录
- [ ] README.md 是纯技术教程
- [ ] 部署包只含部署文件
- [ ] 用户只能获取到部署相关内容

## 📚 参考案例

参考其他开源项目的写法：
- GitHub README：技术文档风格，步骤清晰
- 项目博客/公众号：经验分享风格，有故事有感受
- 两者分工明确，互不替代
