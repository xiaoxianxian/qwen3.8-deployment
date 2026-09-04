# API 参考：Ollama 的 OpenAI 兼容接口

本地 Qwen3.8-27B 经 Ollama 暴露 OpenAI 兼容接口，所有主流 Agent / SDK（WorkBuddy、Claude Desktop、Trae、Hermes、OpenAI SDK、LangChain 等）底层都走这套。

## 1. 端点与鉴权

| 项 | 值 |
|----|----|
| Base URL | `http://localhost:11434/v1`（OpenAI 兼容协议） |
| 原生 Ollama 地址 | `http://localhost:11434`（仅 Ollama 原生 `/api/chat`；客户端有「Ollama」专属选项时用这个，不带 `/v1`） |
| Chat 端点 | `POST /v1/chat/completions` |
| Models 列表 | `GET /v1/models` |
| Authorization | `Bearer <任意非空串>`（Ollama 不校验 Key，如 `not-needed`） |
| Content-Type | `application/json` |

> 若客户端有专门的 **「Ollama」服务商** 选项，填 `http://localhost:11434`（不带 `/v1`）；选 **「OpenAI」** 兼容协议时才填 `http://localhost:11434/v1`（必须带 `/v1`）。

## 2. 请求体（Chat Completions）

```json
{
  "model": "qwen3.8-local",
  "messages": [
    {"role": "system",    "content": "你是一个本地助手"},
    {"role": "user",      "content": "你好"},
    {"role": "assistant", "content": "你好，我是本地 Qwen3.8。"},
    {"role": "user",      "content": "继续"}
  ],
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 2048,
  "stream": false,
  "tools": []
}
```

字段说明：

- `model`：**必须与 `ollama list` 输出逐字一致（大小写敏感）**，否则 `404 model not found`。
- `messages[].role`：`system` / `user` / `assistant` / `tool`。
- `messages[].content`：字符串，或「多模态内容数组」（见下）。
- `stream`：`true` 时按 SSE 流式返回（`data: {json}\n\n`，结束为 `data: [DONE]`）。
- `tools`：函数调用声明（见 §5）。

## 3. 多模态（发图片）

客户端开启 `supportsImages` 后，把图片以 base64 放进 `content` 数组：

```json
{
  "model": "qwen3.8-local",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "图里写了什么文字？"},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,<BASE64>"}}
    ]
  }]
}
```

- 支持 `image/png`、`image/jpeg` 等；`url` 用 `data:` 内联 base64（也可直接给本地 `http(s)://` 图片 URL）。
- Qwen3.8 原生支持**图像 + 视频**输入、文本输出；当前 Ollama 兼容接口主要走 `image_url` 通道，视频输入依赖客户端/Ollama 版本支持。**不支持音频输入**。
- 不挂 mmproj 时发图会报 `500 image input is not supported` —— 确认 Modelfile 已 `PROJECTOR` 挂载 `mmproj-F16.gguf`。

## 4. 流式示例（curl）

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.8-local",
    "stream": false,
    "messages": [{"role": "user", "content": "用一句话介绍自己"}]
  }'
```

返回（节选）：

```json
{
  "model": "qwen3.8-local",
  "choices": [{
    "message": {"role": "assistant", "content": "我是运行在你本地的 Qwen3.8-27B 模型……"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 12, "completion_tokens": 38, "total_tokens": 50}
}
```

## 5. 工具调用 / 函数调用（tools）

Qwen3.8 原生支持 `tools`，按 OpenAI 规范声明即可，无需服务端额外配置：

```json
{
  "model": "qwen3.8-local",
  "messages": [{"role": "user", "content": "北京现在天气如何？"}],
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "查询某城市天气",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"]
      }
    }
  }]
}
```

模型命中工具时，返回 `choices[].message.tool_calls`（含 `function.name` 与 `arguments`）；你把执行结果以 `role: "tool"` 回传即可。

## 6. 推理 / 思考（thinking）

Qwen3.8 带 `thinking` 能力。经 Ollama 时，思考过程通常随响应返回（字段实现随版本可能出现在 `message.reasoning_content` 或合并进内容）。客户端开启「支持推理 / supportsReasoning」即可透传，无需特殊请求参数。

## 7. 常见错误映射

|| HTTP | 含义 | 排查 |
||------|------|------|
|| 404 | `model not found` | 模型名与 `ollama list` 不一致；或权重 blob 丢失（见 guide.md 第七节 #5） |
|| 500 | `image input is not supported` | 未挂 mmproj（见 guide.md 第七节 #6） |
|| 400 | `exceeds the available context` | 对话超 `num_ctx`；已设 131072，仍超则缩短历史或启代理截断（见 #7） |
|| 502 | 连接被拒绝 | Ollama 未运行，或前置代理进程被回收（launchd 未托管） |

## 8. 性能参考

以下为 Apple M5 Pro / 48GB + Q5_K_M 实测数据：

|| 量化版本 | 文件大小 | 内存占用 | 生成速度 | 质量 |
||---------|---------|---------|---------|------|
|| IQ2_XXS | 6.77 GB | 11–13 GB | ~12–15 tok/s | 中低 |
|| Q3_K_XL | 12.24 GB | 13–16 GB | ~11–13 tok/s | 中 |
|| Q4_K_M | 15.33 GB | 17–19 GB | ~10–11 tok/s | 高 |
|| **Q5_K_M** | **18.41 GB** | **~28 GB** | **~9.7 tok/s** | **很高** |
|| Q6_K_XL | 23.56 GB | 28–30 GB | ~8–9 tok/s | 高 |
|| Q8_K_XL | 29.30 GB | 35–40 GB | ~7–8 tok/s | 最高 |

**实测备注：** Q5_K_M 首次加载约 6s，上下文 65536 时性能稳定，超过 100K 时速度下降明显。

## 8. 客户端三件套速查

- **Base URL**：`http://localhost:11434/v1`（OpenAI 协议）或 `http://localhost:11434`（Ollama 原生选项）
- **API Key**：任意非空串（如 `not-needed`）
- **Model**：`qwen3.8-local`（与 `ollama list` 完全一致）

## 9. 验证脚本

运行 `~/models/verify-ollama.sh` 进行一键验证，检查：
- Ollama 服务状态
- 已安装模型列表
- API 连通性
- 多模态能力
