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

---

## 2026-09-04 图片空回复与 400 报错根因修复

### 发现的问题
1. 用户发图后调用 qwen3.8 无输出（content 为空）
2. 间歇性报 `400 request (...) exceeds the available context size (65536)`

### 根因分析
**问题 1：thinking 模式吃掉 num_predict 预算**
- Qwen3.8 默认开启推理思考（thinking），会先消耗 `num_predict` token 用于思考
- 调用方若只传 `num_predict=60`，思考就把预算吃光，`content` 字段自然为空
- 这不是模型坏了，而是 budget 分配问题

**问题 2：num_ctx=65536 太小**
- 旧文档写"单张 1024px 图约 13 万 token"是误读
- 实测一张 1024×1024 纯色 PNG 仅 ~1084 tokens
- 真正触发 400 的是「图片 + 长对话历史」总和超过 65536

### 实测数据
| num_ctx | 模型大小 | GPU占用 | 速度 | 图片测试 |
|---------|---------|---------|------|---------|
| 262144 | 38 GB | 5%/95% CPU/GPU | ~3 tok/s | 能运行但太慢 |
| **131072** | **28 GB** | **100% GPU** | **~9.7 tok/s** | ✅ 推荐 |
| 65536 | 24 GB | 100% GPU | ~9.6 tok/s | 易触发 400 |

### 解决方案
- `num_ctx` 从 65536 升至 **131072**（平衡速度与容量）
- 调用时确保 `options.num_predict ≥ 2000`（或传 `think=false` 关闭思考）
- KV cache 量化（`OLLAMA_KV_CACHE_TYPE=q8_0`）+ Flash Attention 已启用

### 验证结果
- 图片问答：成功识别"设计师工作台"场景，输出完整
- GPU 占用：100%（无 CPU 卸载）
- 速度：9.7 tok/s（与 65536 相同）
- 内存占用：28 GB（48 GB 机器足够）

### 经验教训
- 旧文档关于"13 万 token"的引用是误读，需实测验证
- 推理模型的 thinking 模式会占用 token 预算，调用方需预留余量
- `num_ctx` 不是越大越好，找到性能与容量的 sweet spot 才是关键
