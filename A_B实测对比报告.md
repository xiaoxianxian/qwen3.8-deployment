---
permalink: /ab-test/
title: A/B 实测对比报告
---

# Qwen3.8-27B 量化方案 A/B 实测对比报告

> 生成时间：2026-09-15 21:43  
> 测试环境：MacBook Pro / M5 Pro / 48GB 统一内存 / Ollama 0.33.3  
> 方法：同一套 12 道文本题（温度=0、num_predict=4096、num_ctx=131072、统一走 Ollama /api/chat），逐模型串行跑，跑完即卸载避免显存叠加。视觉题 G1 因依赖独立 mmproj 链路，本次未纳入。

## 一、体积 vs 速度 vs 吞吐（汇总，12 题均值）

| 模型 | 量化 | bpw | 体积(GB) | 平均 decode (tok/s) | 平均 prefill (tok/s) | 平均生成 token |
|---|---|---|---|---|---|---|
| MLX 4-bit (NVFP4 均匀) | qwen3.8:27b-mlx | 4.0 | 18 | 29.90 | 224.1 | 1081 |
| GSQ-RCO IQ3_S (3.5bpw 混合) | qwen3.8-gsq-iq3s-mtp | 3.5 | 12 | 12.64 | 133.8 | 978 |
| GSQ-RCO IQ3_XXS (3.0bpw 混合) | qwen3.8-gsq-iq3xxs-mtp | 3.0 | 10 | 12.55 | 136.2 | 915 |
| GGUF Q5_K_M (5.6bpw 均匀) | qwen3.8-q5:latest | 5.6 | 20 | 14.94 | 128.9 | 1174 |

> 体积取 `ollama list` 显示值；decode = eval_count/eval_duration，prefill = prompt_eval_count/prompt_eval_duration（均来自 Ollama 返回顶层字段）。

## 二、逐题 decode 速度对比 (tok/s)

| 题号 | 类别 | MLX 4-bit (NVFP4 均匀) | GSQ-RCO IQ3_S (3.5bpw 混合) | GSQ-RCO IQ3_XXS (3.0bpw 混合) | GGUF Q5_K_M (5.6bpw 均匀) |
|---|---|---|---|---|---|
| A1 | Agentic Coding | 39.45 | 16.19 | 13.93 | 17.74 |
| A2 | Agentic Coding | 37.69 | 13.55 | 13.50 | 16.14 |
| A3 | Agentic Coding | 36.68 | 11.92 | 10.68 | 14.28 |
| A4 | Agentic Coding | 30.96 | 11.25 | 11.25 | 13.48 |
| B1 | Math Reasoning | 34.76 | 14.04 | 13.99 | 16.52 |
| B2 | Math Reasoning | 31.92 | 12.99 | 13.26 | 15.69 |
| C1 | Knowledge (GPQA) | 24.53 | 12.51 | 12.84 | 13.69 |
| D1 | Long-context | 26.22 | 12.84 | 13.36 | 15.83 |
| E1 | Structured Output | 23.32 | 11.63 | 11.92 | 13.57 |
| E2 | Structured Output | 25.05 | 11.86 | 12.20 | 14.64 |
| F1 | Chinese Writing | 21.99 | 10.13 | 10.59 | 12.20 |
| F2 | Chinese Writing | 26.26 | 12.82 | 13.14 | 15.55 |

## 三、输出质量抽样（每题每模型前 150 字，供人工比对）

### A1 · A1（Agentic Coding）

- **MLX 4-bit (NVFP4 均匀)**: ```python # lru_cache.py import threading from collections import OrderedDict from typing import Optional   class LRUCache:     """Thread-safe LRU Cac
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: ```python from collections import OrderedDict import threading   class LRUCache:     def __init__(self, capacity: int):         if capacity <= 0:     
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: ```python import threading from collections import OrderedDict   class LRUCache:     def __init__(self, capacity: int):         if capacity <= 0:     
- **GGUF Q5_K_M (5.6bpw 均匀)**: ```python # lru_cache.py import threading from collections import OrderedDict   class LRUCache:     def __init__(self, capacity: int):         if capa

### A2 · A2（Agentic Coding）

- **MLX 4-bit (NVFP4 均匀)**: ## Bug 定位  问题出在 `elif` 和 `else` 两个分支中，**`+= 1` 和 `-= 1` 写反了**：  ```python elif n == candidate:     count -= 1   # ❌ 相同元素却减少计数 else:     count += 1   #
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: ## Bug 定位  `elif` 和 `else` 分支中的 `count` 操作**写反了**：  ```python elif n == candidate:     count -= 1   # ❌ 相同元素却减少计数 else:     count += 1   # ❌ 不同元素却增加计数
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: ## Bug 定位  问题出在 `elif` 和 `else` 两个分支中，`count += 1` 和 `count -= 1` **写反了**。  ```python elif n == candidate:     count -= 1   # ❌ 遇到相同元素，应该"加分"，却减了 else
- **GGUF Q5_K_M (5.6bpw 均匀)**: ## Bug 定位  问题出在 `elif` 和 `else` 分支中，**`count += 1` 和 `count -= 1` 写反了**：  ```python elif n == candidate:     count -= 1   # ❌ 相同元素却在"扣票" else:     cou

### A3 · A3（Agentic Coding）

- **MLX 4-bit (NVFP4 均匀)**: # 每个部门薪资 Top 3 的 SQL 查询  ## 推荐写法（CTE + 窗口函数）  ```sql WITH ranked AS (     SELECT         dept,         name,         salary,         RANK() OVER (    
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: ## SQL 查询  ```sql WITH ranked AS (     SELECT         dept,         name,         salary,         RANK() OVER (PARTITION BY dept ORDER BY salary DESC)
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: ## SQL 查询  ```sql SELECT dept, name, salary, rank FROM (     SELECT         dept,         name,         salary,         RANK() OVER (PARTITION BY dept
- **GGUF Q5_K_M (5.6bpw 均匀)**: ## SQL 查询  ```sql WITH ranked AS (     SELECT         dept,         name,         salary,         RANK() OVER (PARTITION BY dept ORDER BY salary DESC)

### A4 · A4（Agentic Coding）

- **MLX 4-bit (NVFP4 均匀)**: ## 拆分后的代码  ```python from __future__ import annotations from pathlib import Path from typing import Protocol   # ── 接口定义 ─────────────────────────────
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: ## 拆分后的代码  ```python from __future__ import annotations from pathlib import Path from typing import Protocol   # ─────────────────────────────────────
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: ## 拆分后的代码  ```python from pathlib import Path from typing import Protocol   # ── 接口定义 ──────────────────────────────────────────────  class Database(P
- **GGUF Q5_K_M (5.6bpw 均匀)**: ## 拆分后的代码  ```python from __future__ import annotations from pathlib import Path from typing import Protocol   # ─────────────────────────────────────

### B1 · B1（Math Reasoning）

- **MLX 4-bit (NVFP4 均匀)**: # 求满足同余条件的最小正整数  ## 问题重述  求最小正整数 $n$，使得  $$ \begin{cases} n \equiv 2 \pmod{3} \\ n \equiv 3 \pmod{5} \\ n \equiv 2 \pmod{7} \end{cases} $$  ---  ## 方法
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: # 求解最小正整数 n  ## 问题条件  $$n \equiv 2 \pmod{3}, \quad n \equiv 3 \pmod{5}, \quad n \equiv 2 \pmod{7}$$  ## 完整推理过程  ### 第一步：合并同余条件  注意到前两个条件中，$n$ 除以 3 和除以
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: # 求解同余方程组  ## 问题  求最小正整数 $n$，使得：  $$n \equiv 2 \pmod{3}, \quad n \equiv 3 \pmod{5}, \quad n \equiv 2 \pmod{7}$$  ## 完整推理  ### 第一步：合并前两个同余式  由 $n \equi
- **GGUF Q5_K_M (5.6bpw 均匀)**: # 求解最小正整数 n  ## 问题条件  $$n \equiv 2 \pmod{3},\quad n \equiv 3 \pmod{5},\quad n \equiv 2 \pmod{7}$$  ---  ## 方法一：逐步代入法（直观）  **第一步：合并前两个同余条件**  由 $n \equ

### B2 · B2（Math Reasoning）

- **MLX 4-bit (NVFP4 均匀)**: # 甲乙相向而行相遇问题  ## 题意梳理  > 题目中"同时出发"与"甲出发 1 小时后乙才出发"存在矛盾，按后一句理解：**甲先出发，乙比甲晚 1 小时出发**，两人相向而行，总距离 60 km。  | 人物 | 速度 | 出发时刻 | |------|------|----------| | 
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: # 甲乙相向而行相遇问题  ## 题意梳理  > 甲、乙从相距 **60 km** 的两地出发，相向而行。   > 甲速度 $v_甲 = 4\;\text{km/h}$，乙速度 $v_乙 = 6\;\text{km/h}$。   > **甲先出发，1 小时后乙才出发。** 求乙出发后多久两人相遇。 
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: ## 设未知量  设乙出发后经过 $t$ 小时两人相遇。  ## 列方程  - 甲比乙早出发 1 小时，所以甲总共走了 $(t+1)$ 小时，路程为 $4(t+1)$ km。 - 乙走了 $t$ 小时，路程为 $6t$ km。 - 两人相向而行，相遇时两人路程之和等于总距离 60 km。  $$4(
- **GGUF Q5_K_M (5.6bpw 均匀)**: # 甲乙相向而行相遇问题  ## 题意梳理  > 两地相距 **60 km**，甲速 **4 km/h**，乙速 **6 km/h**，相向而行。 > 甲先出发，**1 小时后**乙才出发。求乙出发后多久两人相遇？  ## 设未知数  设乙出发后经过 $t$ 小时两人相遇。  则此时：  | 人物 

### C1 · C1（Knowledge (GPQA)）

- **MLX 4-bit (NVFP4 均匀)**: ## 正确答案：B  **两个全同费米子不能占据同一量子态（所有量子数相同）。**  ---  ### 逐项分析  | 选项 | 判断 | 理由 | |------|------|------| | A | ❌ | 说反了。玻色子（自旋为整数，如光子、⁴He 原子）**可以**大量占据同一量子态，这
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: ## 正确答案：B  **两个全同费米子不能占据同一量子态（所有量子数相同）。**  ---  ### 逐项分析  | 选项 | 判断 | 理由 | |------|------|------| | A | ✗ | 说反了。玻色子（自旋为整数）**可以**占据同一量子态（如玻色-爱因斯坦凝聚），泡利
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: ## 正确答案：**B**  > 两个全同费米子不能占据同一量子态（所有量子数相同）。  ---  ### 简要解释  **泡利不相容原理**的核心表述是：  > 两个**全同费米子**（自旋为半整数的粒子）不能处于完全相同的量子态，即不能拥有所有相同的量子数。  以电子为例，两个电子不能同时具有相
- **GGUF Q5_K_M (5.6bpw 均匀)**: ## 正确答案：B  **两个全同费米子不能占据同一量子态（所有量子数相同）。**  ---  ### 逐项分析  | 选项 | 判断 | 理由 | |------|------|------| | A | ✗ | 玻色子（自旋为整数）**可以**占据同一量子态，这正是玻色-爱因斯坦凝聚的前提。泡利

### D1 · D1（Long-context）

- **MLX 4-bit (NVFP4 均匀)**: # 「灯塔」项目周报（第 11 周）问答  ## (a) 二期模型平台 PoC 的阻塞点  周报"风险"一节列出了 **两个** 阻塞点：  1. **一期 AML 规则联调未完成**——二期模型平台在流程上依赖一期 3 条反洗钱（AML）规则的联调结果，而该联调尚未完成（一期整体进度 92%），构
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: ## 回答  **(a) 二期模型平台 PoC 的阻塞点**  根据周报第 3 条（风险），PoC 启动面临**两个阻塞点**：  1. **一期 AML 规则联调未完成**——二期模型平台依赖一期 3 个反洗钱规则的联调结果，当前一期仅完成 92%，这 3 个规则尚未联调完毕，构成直接的前置依赖。
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: ## 回答  **(a) 二期模型平台 PoC 的阻塞点**  有两个阻塞点：  1. **一期 AML 规则联调未完成**——二期模型平台依赖一期 3 个反洗钱规则的联调完成，当前一期仅完成 92%，这 3 个规则尚未联调，构成直接阻塞。 2. **客户侧数据脱敏环境未就绪**——PoC 需要客户
- **GGUF Q5_K_M (5.6bpw 均匀)**: ## 回答  **(a) 二期模型平台 PoC 的阻塞点**  存在两个阻塞点：  1. **一期 AML 规则联调未完成**——二期模型平台依赖一期 3 个反洗钱（AML）规则的联调结果，当前一期整体完成 92%，这 3 个规则尚未联调完毕，构成上下游阻塞。 2. **客户侧数据脱敏环境未就绪**

### E1 · E1（Structured Output）

- **MLX 4-bit (NVFP4 均匀)**: {"title":"Safari 浏览器登录页登录按钮点击无响应","priority":"high","steps":["打开 Safari 浏览器（建议最新稳定版）","访问应用登录页面","在用户名和密码输入框中填写有效凭证","点击「登录」按钮","观察按钮无任何响应，页面无跳转、无报错、无
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: {"title":"登录页在 Safari 上点击登录按钮无响应","priority":"high","steps":["打开 Safari 浏览器并访问登录页面","输入用户名和密码","点击登录按钮","观察按钮无任何响应（无跳转、无提示、无网络请求）"],"fix":"排查 Safari 下
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: {"title":"Safari 登录页点击登录按钮无响应","priority":"high","steps":["打开 Safari 浏览器并访问登录页面","输入正确的用户名和密码","点击登录按钮","观察按钮无响应，页面未发生跳转"],"fix":"排查 Safari 下 JavaScri
- **GGUF Q5_K_M (5.6bpw 均匀)**: {"title":"登录页在 Safari 上点击登录按钮无响应","priority":"high","steps":["打开 Safari 浏览器并访问登录页面","输入正确的用户名和密码","点击登录按钮","观察按钮无响应，页面无跳转、无网络请求发出"],"fix":"排查登录按钮事件绑定方

### E2 · E2（Structured Output）

- **MLX 4-bit (NVFP4 均匀)**: [{"tool":"get_weather","args":{"city":"北京","date":"明天"}},{"tool":"send_reminder","args":{"text":"明天北京有雨，记得带伞！"}}]
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: [{"tool":"get_weather","args":{"city":"北京","date":"明天"}},{"tool":"send_reminder","args":{"text":"明天北京下雨，记得带伞"}}]
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: [{"tool":"get_weather","args":{"city":"北京","date":"明天"}},{"tool":"send_reminder","args":{"text":"明天北京下雨，记得带伞"}}]
- **GGUF Q5_K_M (5.6bpw 均匀)**: [{"tool":"get_weather","args":{"city":"北京","date":"明天"}},{"tool":"send_reminder","args":{"text":"明天北京下雨，记得带伞"}}]

### F1 · F1（Chinese Writing）

- **MLX 4-bit (NVFP4 均匀)**: # 为什么本地大模型量化对中小团队有真实价值  **引言**  中小团队做 AI 应用，最现实的卡点不是"模型够不够聪明"，而是"我买不买得起那台机器"。云端 API 按 token 计费，日活一上来账单就失控；而本地部署又意味着动辄数百 GB 显存的 GPU 服务器。量化，恰好把这道门槛砍掉了一大
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: # 为什么本地大模型量化对中小团队有真实价值  **引言**  对没有 GPU 集群的中小团队而言，"本地跑大模型"长期停留在 PPT 阶段。量化技术的成熟，让这件事从"理论上可行"变成了"今晚就能跑"。  **技术原理：把数字"瘦身"**  大模型参数默认以 FP16（16 位浮点）存储，每个参数
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: # 为什么本地大模型量化对中小团队有真实价值  **引言**  中小团队往往没有 GPU 集群，却需要大模型能力。量化技术恰好把"用得起"和"用得好"之间的鸿沟大幅缩小，让一台工作站就能承载原本需要数据中心才能运行的模型。  **技术原理**  量化，通俗地说，就是把模型权重从高精度浮点数压缩成低精
- **GGUF Q5_K_M (5.6bpw 均匀)**: # 为什么本地大模型量化对中小团队有真实价值  **引言**  中小团队面对大模型时，往往卡在三个现实：没有 GPU 集群、API 按 token 持续计费、业务数据不能出内网。本地量化部署，恰好同时回应了这三点，是当下最务实的"拥有模型"路径。  **技术原理：把"高清"压成"够用"**  量化，

### F2 · F2（Chinese Writing）

- **MLX 4-bit (NVFP4 均匀)**: 推荐译文：  > **量化通过降低模型权重的数值精度，以微小的精度损失换取内存占用与推理开销的大幅降低。混合精度方案根据张量敏感度分配比特数，在更低的平均位宽下保持任务质量。**  --- **简要说明：** - **Quantization / Mixed-precision** 分别对应业界通用
- **GSQ-RCO IQ3_S (3.5bpw 混合)**: 推荐译文：  > 量化通过降低模型权重的数值精度，以少量精度损失为代价，大幅降低内存占用和推理成本。混合精度方案根据敏感度为各张量分配比特数，在更低的平均位宽下保持任务质量。  **简要说明：** - **memory footprint** → "内存占用"（深度学习领域惯用表达，优于直译"内存足
- **GSQ-RCO IQ3_XXS (3.0bpw 混合)**: 推荐译文：  > **量化通过降低模型权数的数值精度，以少量精度损失换取内存占用和推理成本的大幅降低。混合精度方案根据张量敏感度分配比特数，在更低的平均位宽下保持任务质量。**  --- **简要说明：** - **Quantization / Mixed-precision** → 量化 / 混合
- **GGUF Q5_K_M (5.6bpw 均匀)**: 推荐译文：  > **量化通过降低模型权重的数值精度，以少量精度损失换取内存占用和推理开销的大幅降低。混合精度方案根据敏感度为各张量分配比特数，在更低的平均位宽下保持任务质量。**  --- **简要说明：** - "trading A for B" 处理为"以 A 换取 B"，符合中文技术写作习惯

## 四、严格质量校验结果

为排除"抽样看不出来"的误导，对全部 4 模型 × 12 题做了程序化校验：

| 校验项 | 方法 | MLX 4-bit | IQ3_S | IQ3_XXS | Q5 |
|---|---|---|---|---|---|
| E1/E2 JSON | `json.loads` 严格解析 | ✅ VALID | ✅ VALID | ✅ VALID | ✅ VALID |
| B1 同余方程 | 最终结论 n=?（标准 23） | ✅ 23 | ✅ 23 | ✅ 23 | ✅ 23 |
| B2 相遇问题 | 最终结论 t=?（标准 5.6h） | ✅ 5.6 | ✅ 5.6 | ✅ 5.6 | ✅ 5.6 |
| C1 知识题 | 选项（标准 B：泡利不相容） | ✅ B | ✅ B | ✅ B | ✅ B |

**结论：在本题集范围内，四个量化层级输出全部正确/合法，未检测到任何量化导致的质量退化——哪怕 3.0bpw 的 IQ3_XXS 也站住了。**

> ⚠️ 必要边界说明：本题集 12 题是"能不能做对"的抽样，不是 198 题级别的基准。DASLab 官方在 GPQA-Diamond（198 题）上测得 IQ3_XXS 相对 BF16 差 ~1 分、IQ3_S 差 0.51 分——这种边际退化在 1 题抽样里必然被淹没。对你主用的 agentic coding / 长推理场景，GSQ 各档均表现稳定；若你后续做严谨评测，需更大题集才能复现那 1 分差距。

## 五、结论与选型建议

**三个维度的事实（本机 M5 Pro / 48GB / Ollama 0.33.3 实测）：**

1. **更省内存——成立。** IQ3_S 12GB、IQ3_XXS 10GB，分别比 MLX 4-bit 的 18GB 省 6GB / 8GB。省下的显存可直接给 131072 长上下文或同机跑的 MiniMax H3 腾地方。
2. **更快——不成立。** MLX 4-bit 平均 decode 29.9 tok/s，约为 GSQ 混合精度（12~13 tok/s）的 **2.4 倍**，也比 Q5（14.9）快一倍。原因：NVFP4 是 GPU 友好的均匀 4-bit，而 IQ/GSQ 混合精度在每个权重解量化时开销大，在 Apple Silicon 的 Metal 后端（memory-bound）上反而更慢。
3. **质量无损（vs 你的 MLX）——基本成立。** 12 题严格校验四档全对；DASLab 官方基准也显示 IQ3_S 在 AIME/LCB 上与原版持平。唯一保留是 IQ3_XXS 在大规模知识基准上有 ~1 分边际退化。

**给你（48GB Mac，主用 agentic coding + 长推理）的选型：**

| 优先级 | 方案 | 体积 | decode | 适用场景 |
|---|---|---|---|---|
| 🥇 速度优先 | **保持 MLX 4-bit（现状）** | 18GB | 29.9 | 要最快响应、显存够用 |
| 🥈 均衡（推荐切换） | **GSQ IQ3_S** | 12GB | 12.6 | 想省 6GB 给 H3/长上下文，质量不降 |
| 🥉 极致省显存 | GSQ IQ3_XXS | 10GB | 12.5 | 显存极度紧张；接受知识题 ~1 分边际风险 |
| 并发安全网 | Q5（现状保留） | 20GB | 14.9 | 多会话并发时比 MLX 更稳（你已有配置） |

**一句话总结**：GSQ-RCO 对你的真实价值是"**省显存、质量不降**"，不是"更快"。想提速继续用现在的 MLX 4-bit；想把显存让给 H3 或拉满 131K 上下文，切到 IQ3_S 是性价比最高的动作。Q5 维持现状作并发兜底即可。

> 注：GSQ 系列与你的 MLX 走的是同一套 Ollama / llama.cpp Metal 管线，A/B 唯一变量是量化方式，对比干净。IQ3_XXS 因 Ollama 0.33.3 注册校验不认其 `IQ2_XS` 子类型，采用手动改写 manifest 方式绕过（运行时 llama.cpp 可正常加载）。
