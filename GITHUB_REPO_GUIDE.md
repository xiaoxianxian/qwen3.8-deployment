# GitHub 仓库内容规范

## 📌 核心原则

**GitHub 仓库只放部署相关文件，不包含：**
- ❌ 公众号文章（HTML/Markdown）
- ❌ 开发记录（CHANGELOG.md）
- ❌ 开发想法（IDEA.md）
- ❌ 调试脚本（scripts/, docs/）
- ❌ 内部测试文档（调优与避坑指南.md）
- ❌ 备份文件（Modelfile.*.bak-* 等）
- ❌ .DS_Store 等系统文件（见 .gitignore）

## 📦 部署包说明

**部署包（.tar.gz）的定位：**
- 国内镜像站点的下载链接（hf-mirror、ModelScope）
- 微信公众号文章里的"一键下载"方案
- 不想注册GitHub账号的用户替代方案
- 离线使用场景

**部署包不包含在GitHub仓库内**，但本地保留，用于上述场景。

**部署包内容：**
- README.md（部署教程）
- setup-guide.md（详细步骤）
- CURRENT_CONFIG.md（参数速查）
- Modelfile（配置模板）
- verify-ollama.sh（验证脚本）
- README-资源包说明.md（使用说明）
- 性能对比与量化指南.md（量化选择参考）

## 📂 仓库结构

```
qwen3.8-local-deployment/
├── README.md                     # ⭐ 完整部署教程（主文档）
├── setup-guide.md                # 详细步骤说明（备选参考）
├── CURRENT_CONFIG.md             # 本机配置快照
├── Modelfile                     # Ollama 模型配置模板
├── verify-ollama.sh              # 一键验证脚本
├── 性能对比与量化指南.md         # 量化版本选择参考
├── README-资源包说明.md          # 资源包说明（可选参考）
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

## 💡 经验教训（2026-09-09）

### 问题
最初将公众号文章、开发记录等文件也上传到了 GitHub 仓库，导致仓库内容混乱，用户可能获取到不必要的信息。

### 解决
1. 明确区分 GitHub 仓库的定位：只放部署相关文件
2. 公众号文章保留在本地，供分享使用
3. 编写 GITHUB_REPO_GUIDE.md 作为规范文档
4. 使用 `git rm --cached` 从 git 追踪中移除文件（本地保留）

### 命令
```bash
# 从 git 追踪中移除文件（保留本地）
git rm --cached 公众号文章-本地部署Qwen3.8.html
git rm --cached 公众号文章-本地部署Qwen3.8.md

# 提交并推送
git add -A
git commit -m "chore: 从GitHub仓库移除公众号文章"
git push origin main
```

---

## 📋 仓库内容规范

| 文件类型 | GitHub 仓库 | 本地保留 | 部署包 |
|---------|-------------|---------|--------|
| README.md（教程） | ✅ | ✅ | ✅ |
| setup-guide.md | ✅ | ✅ | ✅ |
| CURRENT_CONFIG.md | ✅ | ✅ | ✅ |
| Modelfile | ✅ | ✅ | ✅ |
| verify-ollama.sh | ✅ | ✅ | ✅ |
| 性能对比与量化指南.md | ✅ | ✅ | ✅ |
| README-资源包说明.md | ✅ | ✅ | ✅ |
| 部署包 .tar.gz | ❌ | ✅ | ✅ |
| 公众号文章 | ❌ | ✅ | ❌ |
| 开发记录 | ❌ | ✅ | ❌ |
| 调试脚本 | ❌ | ✅ | ❌ |
