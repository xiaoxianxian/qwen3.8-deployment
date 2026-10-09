# Shimmy 引擎实测：同 GGUF 同机器，比 Ollama 慢两个数量级

日期：2026-10-06 · 机器：M5 Pro 48GB · 项目：`Michael-A-Kuykendall/shimmy` v2.6.1
背景：公众号「AI练技箱」2026-10-05 推文《5.1MB 启动 <100ms，这个 LLM 神器，正试图重新定义 Ollama》，评估它对我本地模型栈的价值，于是实跑一轮 A/B。

## 结论先行

**不用换。** 同一份 GGUF、同一台机器、同一条 prompt、同一温度：

| 指标 | Ollama | Shimmy | 差距 |
|---|---|---|---|
| 端到端耗时（3 轮中位） | **0.42 s** | **158.3 s** | 慢约 **377 倍** |
| 首 token 延迟（中位） | **0.067 s** | **17.1 s** | 慢约 **256 倍** |
| 输出字符数 | 149 | 971 | Shimmy 超量生成 |
| 输出内容 | 完整、切题 | 退化乱码 | — |

Shimmy 不只慢，它解出来的 token 序列本身是错的。

## 测试条件

- **模型两边完全同源**：同一个 `Qwen3-0.6B-Q8_0.gguf`（609 MB，Qwen 官方 GGUF 仓库唯一量化档 Q8_0）
  - Ollama 侧：`FROM ./Qwen3-0.6B-Q8_0.gguf` 建 `qwen3-0.6b-q8:latest`
  - Shimmy 侧：`--model-path` 直指同一文件
- **prompt**：`Write a short paragraph about why local model inference matters for privacy. Keep it under 80 words.`
- 参数：`temperature=0`、`num_predict=96`、Ollama 加顶层 `think: false` 关掉 Qwen3 思考模式（否则 Ollama 侧会生成 1085 token 思考链，两边不可比）
- 3 轮，Ollama 先跑、Shimmy 后跑，中间 sleep 1s
- 跑之前先 `ollama stop qwen3.8:27b-mlx`（当时占着 35.63 GB VRAM），避免内存争抢污染计时

## 实测数据（原始）

| 轮次 | 引擎 | 端到端 s | 首 token s | 输出字符 | eval_count |
|---|---|---|---|---|---|
| 1 | Ollama | 0.16 | 0.037 | 149 | 26 |
| 1 | Shimmy | 152.32 | 18.562 | 971 | 不返回 |
| 2 | Ollama | 0.53 | 0.071 | 149 | 26 |
| 2 | Shimmy | 158.27 | 12.468 | 1017 | 不返回 |
| 3 | Ollama | 0.42 | 0.067 | 149 | 26 |
| 3 | Shimmy | 244.89 | 17.125 | 724 | 不返回 |

csv 原文：`bench/shimmy_ab/results/ab_summary.csv`，逐轮输出 `results/{engine}_r{N}.txt`。

## 输出质量对照

Ollama（r1，149 字符）：

> Local model inference is crucial for privacy because it minimizes data exposure, protects user data, and ensures compliance with privacy regulations.

Shimmy（r1 前 400 字符）：

> ` > | im > | im  to | > <  | > # i < | Think  the  user ,  to  > << | >>  The so o  |  - me # | > Okay ,  let 's  me  in  my  knowledge  you  know  >  **  the  first  starting  with  that  i  am  for  now . : < | >  I  have  something  ... >  here  is  not I  this  is  about  there So  let  me  to  start  <  or  the  about  the  user  said  maybe  not  -  this  part ,  and  but  what  so  to  m  af`

注意 ` > | im`、` << | >>` 这种碎片——这是**分词/反量化错位**的特征，不是简单的"模型小"。Ollama 侧同一份权重输出的是干净英文。同一份权重，两个引擎，结论只有一个：Shimmy 的 Airframe 引擎在这个 GGUF 上没有正确解码。

## 顺带验实的三件事

1. **文章里"零配置模型发现"是真的**。`shimmy list` 自动扫到 3 个：手动指定的 GGUF、一个 `mmproj-f16`，以及**我刚用 Ollama 建的 `qwen3-0.6b-q8`**（它列成 `registry.ollama.ai/library/qwen3-0.6b-q8/latest`）。跨工具复用模型目录这个承诺兑现了。
2. **最新三个 release 没有二进制**。v2.6.0 / v2.6.1 有 `shimmy-macos-arm64`（6.82 MB），**v2.6.2 / v2.6.3 / v2.6.4 全空**，只能退到 v2.6.1。跟文章自己承认的"Release 偶尔缺失"对上了，也跟最后 commit 停在 2026-08-30、37 天没动是同一回事。
3. **Shimmy 不返回 token 计数字段**。`/api/generate` 流式 chunk 是裸文本 `data: </`，`/v1/chat/completions` 即使不传 `stream` 也强制返回 SSE（不符合 OpenAI 规范的流式语义）。想做成本统计、想算 tok/s 都拿不到数。

## 复现

```bash
cd ~/Documents/AI项目/本地部署Qwen3.8/bench/shimmy_ab

# 起服务（端口 11435 被旧的 python 代理占着，用 11436）
./shimmy serve --model-path "$PWD/Qwen3-0.6B-Q8_0.gguf" --bind 127.0.0.1:11436

# 另一终端跑基准
python3 ab_shimmy.py
```

脚本 `ab_shimmy.py` 已含交错跑 3 轮、双格式 chunk 解析、结果落 csv。

> **环境状态更新（2026-10-06）**：测完已清理——Ollama 临时 tag `qwen3-0.6b-q8:latest` 已 `ollama rm`，占着 11435 的旧 python 分流代理已连同其 LaunchAgent（`com.user.ollama-strip-proxy.plist`）一并移除，11435 现空闲；`bench/shimmy_ab/` 下的 shimmy 二进制与 `Qwen3-0.6B-Q8_0.gguf`（共 617MB）已移入回收站——**引擎既已判死，脚本 `ab_shimmy.py` 与 `Modelfile` 留着也跑不起来，本目录只剩 36K 的 `results/` 原始输出作证据备份**。想复跑得重新下载 v2.6.1 二进制（走代理 7897）与 GGUF（610MB），以及重建 Ollama 侧同权重 tag。

## 回到那篇文章的说法

那张「5.1MB / <100ms / 50MB vs Ollama 680MB / 5-10s / 200MB+」的对比表，测的是 TinyLlama 级别的加载开销。落到我这台机器上实测：

- 启动：Shimmy 进程随起随用，Ollama 侧这次 0.16 s 已经热；冷启动差值确实存在，但不是 27B 场景的瓶颈
- 运行：27B 常驻 18–20 GB，服务端 200 MB 占比不到 1%；跑 0.6B 时 Ollama 总耗时 0.42 s，Shimmy 158 s
- 结论那句「追求开箱即用就继续用 Ollama」是对的，但真实原因是**引擎解码正确性都有问题**，不只是生态成熟度

「Shimmy will be free forever. No asterisks」这种话术不用当作技术依据。项目本身 5928 star、代码是真的、README 的技术描述（v2.0 删 llama.cpp 后端、改 Airframe 纯 Rust WebGPU 引擎）也确实属实——问题不在真实性，在于它现在跑不出正确结果。

## 一句话判断

小而快是设计目标，但当前版本在 Apple Silicon 上的实现既慢又错。等它把 release 流程修回来、认证清单里加上 27B 级别模型再说。
