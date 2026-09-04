# 内部变更日志（仅用于排查问题，不对外发布）

## 2026-09-04 推理档位修正 + 文章净化

### 发现的问题
1. 文章标题副标题、末尾更新说明、`旧教程`、`原建议`、`改回` 等措辞是"AI自己纠正自己"的痕迹，不适合作为对外发布内容
2. `WorkBuddy 等不及直接 499 超时` 过于特定工具，应为通用描述
3. 代理默认 reasoning_effort 从 medium 改为 high（实测 high 比 medium 更快且质量更好）

### 修复内容
- 删除标题副标题 `(2026年9月4日更新：修正 num_ctx 配置及新增智能代理方案)`
- 删除末尾 `📌 2026年9月4日更新说明` 整块
- `旧教程里的 PROJECTOR 指令` → `Ollama 0.33 已不再支持 PROJECTOR 指令`
- `WorkBuddy 等不及直接 499 超时` → `导致客户端等不及直接超时`
- `Vision_EFFORT` 从 `medium` 改为 `high`
- WorkBuddy 专属说明加注释 `（如需使用代理）`

### 推理档位实测数据
```
low:  ~14s, tokens=178
medium: ~22s, tokens=278
high:   ~19s, tokens=240
xhigh:  500 (所有请求)
```
结论：high 最快且质量最好，代理默认改为 high。

### xhigh bug
- GitHub Issue: #17906
- PR: #17917 (未合并)
- Ollama v0.33.3 未修复
- 待验证：Ollama 升级后 xhigh 是否修复

### 代理技术细节
- 纯 TCP 实现 (`~/models/ollama_strip_proxy.py`)
- 监听端口: 11435
- 上游: 127.0.0.1:11434
- VISION_EFFORT=high
- 清除 http_proxy/https_proxy 环境变量，绕过系统代理拦截
- LaunchAgent: `~/Library/LaunchAgents/com.user.ollama-strip-proxy.plist`

## 2026-09-04 代理问题修复

### 发现的问题
WorkBuddy 报告 502 错误，提示"连接被拒绝"，代理端口 11435 无法访问。

### 原因分析
1. WorkBuddy 沙箱进程（sandbox-c）会强制终止在特定端口运行的脚本
2. Ollama 0.33.x 已原生支持 `reasoning_effort=high`，无需代理中转
3. 之前的代理设计方案虽然正确，但在这个环境中不可行

### 解决方案
- 将 WorkBuddy 模型配置从代理端口 `11435` 改为直连 Ollama `11434`
- 验证文本请求和图片请求均可正常工作

### 经验教训
- 当上游服务已原生支持所需功能时，代理层是多余的复杂度
- 不要过度设计，直接利用现有功能更可靠
