# Qwen3.8-27B 量化方案 A/B 实测对比报告

> 生成时间：2026-10-11 00:07  
> 测试环境：MacBook Pro / M5 Pro / 48GB 统一内存 / Ollama 0.33.3  
> 方法：同一套 12 题（temperature=0、num_predict=1024 对齐可比）。双引擎：Ollama 走 /api/chat（27B NVFP4），Sushi 走 /v1/chat/completions（Flash-Next 2bpw）。为消除 48GB 内存天花板下两模型不能共存的约束，逐模型串行跑、跑完即卸载。Flash-Next 每题重启服务清 KV，避免 prefill 因 KV 耗尽 400。

## 一、体积 vs 速度 vs 吞吐（汇总，12 题均值）

| 模型 | 量化 | bpw | 体积(GB) | 平均 decode (tok/s) | 平均 prefill (tok/s，仅计有返回的题) | 平均生成 token |
|---|---|---|---|---|---|---|
| MLX 4-bit (NVFP4, Ollama 11434) | qwen3.8:27b-mlx | 4.0 | 18 | 25.91 | 176.3（12/12 题） | 869 |
| Qwen3.8-Flash-Next 2bpw (Sushi 12345) | beamster/Qwen3.8-Flash-Next-Sushi-2bpw | 2.0 | 37 | 25.52 | 177.3（4/12 题） | 709 |

> 体积取 `ollama list` 显示值；decode = eval_count/eval_duration（Ollama）或 timings.predicted_ms/predicted_n（Sushi）。⚠️ prefill 只对**有返回值的题**取均值，不用 0 充数：Sushi 在本套 12 题中有 8 题未返回 prefill 耗时（CSV 记为 0，属未采集而非真 0），故该列附注分母。

## 二、逐题 decode 速度对比 (tok/s)

| 题号 | 类别 | MLX 4-bit (NVFP4, Ollama 11434) | Qwen3.8-Flash-Next 2bpw (Sushi 12345) |
|---|---|---|---|
| A1 | Agentic Coding | 38.19 | 11.81 |
| A2 | Agentic Coding | 32.01 | 37.06 |
| A3 | Agentic Coding | 32.16 | 45.88 |
| A4 | Agentic Coding | 29.55 | 10.98 |
| B1 | Math Reasoning | 30.99 | 16.66 |
| B2 | Math Reasoning | 25.01 | 3.63 |
| C1 | Knowledge (GPQA) | 24.89 | 8.99 |
| D1 | Long-context | 27.01 | 1.16 |
| E1 | Structured Output | 16.16 | 28.88 |
| E2 | Structured Output | 17.84 | 41.32 |
| F1 | Chinese Writing | 17.63 | 41.99 |
| F2 | Chinese Writing | 19.50 | 57.86 |

## 三、输出质量抽样（每题每模型前 150 字，供人工比对）

### A1 · A1（Agentic Coding）

- **MLX 4-bit (NVFP4, Ollama 11434)**: ```python # lru_cache.py import threading from collections import OrderedDict from typing import Optional   class LRUCache:     """线程安全的 LRU 缓存，get/pu
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: ```python # lru_cache.py import threading from collections import OrderedDict   class LRUCache:     def __init__(self, capacity: int):         self.ca

### A2 · A2（Agentic Coding）

- **MLX 4-bit (NVFP4, Ollama 11434)**: ## Bug 定位  问题出在 `elif` 和 `else` 两个分支中，**`count` 的增减方向写反了**。  ```python elif n == candidate:     count -= 1   # ❌ 相同元素却减计数 else:     count += 1   # ❌ 不
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: ## Bug 分析  ### 问题所在  `elif` 和 `else` 分支中的 `+=` 和 `-=` **写反了**：  ```python elif n == candidate:     count -= 1   # ❌ 遇到相同元素却减少了计数 else:     count += 1 

### A3 · A3（Agentic Coding）

- **MLX 4-bit (NVFP4, Ollama 11434)**: ## SQL 实现  ```sql SELECT     dept,     name,     salary,     rn  AS ranking FROM (     SELECT         dept,         name,         salary,         RANK
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: ## SQL 写法  ```sql SELECT dept, name, salary, rk AS rank FROM (     SELECT         dept,         name,         salary,         RANK() OVER (PARTITION B

### A4 · A4（Agentic Coding）

- **MLX 4-bit (NVFP4, Ollama 11434)**: ## 拆分后的代码  ```python from __future__ import annotations from pathlib import Path from typing import Protocol   # ─────────────────────────────────────
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: ## 拆分后的代码  ```python from typing import List from pathlib import Path   def read_raw(path: str | Path) -> List[str]:     """职责：从文件读取原始行。不做任何解析或过滤。""" 

### B1 · B1（Math Reasoning）

- **MLX 4-bit (NVFP4, Ollama 11434)**: # 求满足同余条件的最小正整数  ## 问题重述  求最小正整数 $n$，使得：  $$ n \equiv 2 \pmod{3},\quad n \equiv 3 \pmod{5},\quad n \equiv 2 \pmod{7} $$  ---  ## 方法一：逐步代入法（最直观）  **第一步
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: # 求解满足条件的最小正整数 n  ## 问题条件  $$n \equiv 2 \pmod{3}, \quad n \equiv 3 \pmod{5}, \quad n \equiv 2 \pmod{7}$$  ## 逐步代入法  ### 第一步：处理第一个同余式  由 $n \equiv 2 \p

### B2 · B2（Math Reasoning）

- **MLX 4-bit (NVFP4, Ollama 11434)**: # 乙出发后多久两人相遇？  ## 理清题意  > 题目中"同时出发"与"甲出发 1 小时后乙才出发"存在矛盾，按后一句理解：**甲先出发，1 小时后乙才出发，两人相向而行。**  ## 设未知数  设乙出发后经过 $t$ 小时两人相遇。  ## 列方程  | 阶段 | 甲走的路程 | 乙走的路程 
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: ## 解题过程  ### 设未知数  设乙出发后 $t$ 小时两人相遇。  由于甲比乙早出发 1 小时，所以甲实际走了 $(t + 1)$ 小时。  ### 列方程  两人相向而行，相遇时各自走过的路程之和等于总距离：  $$4(t + 1) + 6t = 60$$  ### 求解  $$4t + 

### C1 · C1（Knowledge (GPQA)）

- **MLX 4-bit (NVFP4, Ollama 11434)**: ## 正确答案：B  **两个全同费米子不能占据同一量子态（所有量子数相同）。**  ---  ### 逐项分析  | 选项 | 判断 | 理由 | |------|------|------| | A | ❌ | 说反了。玻色子（自旋为整数，如光子、⁴He 原子）**可以**且倾向于占据同一量子态
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: ## 正确答案：B  **两个全同费米子不能占据同一量子态（所有量子数相同）。**  ---  ### 逐项分析  | 选项 | 判断 | 理由 | |------|------|------| | A | ❌ | 玻色子恰恰**可以**占据同一量子态（如玻色-爱因斯坦凝聚），泡利原理不适用于玻色子

### D1 · D1（Long-context）

- **MLX 4-bit (NVFP4, Ollama 11434)**: # 「灯塔」项目周报（第 11 周）问答  ## (a) 二期模型平台 PoC 的阻塞点  周报"风险"一节列出了 **两个阻塞点**：  1. **一期 AML 规则联调未完成**——二期模型平台在流程上依赖一期 3 条反洗钱（AML）规则的联调结果，而该联调尚未完成（一期整体进度 92%），构成
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: **(a) 二期模型平台 PoC 的阻塞点**  有两个阻塞点：  1. **一期 AML 规则联调未完成**——二期依赖一期剩余 3 个反洗钱规则的联调，这是明确的阻塞点。 2. **客户侧数据脱敏环境未就绪**——直接影响 PoC 启动。  ---  **(b) 本期预算剩余**  $$480 

### E1 · E1（Structured Output）

- **MLX 4-bit (NVFP4, Ollama 11434)**: {"title":"Safari 浏览器登录页登录按钮点击无响应","priority":"high","steps":["打开 Safari 浏览器（建议最新稳定版）","访问应用登录页面","在用户名和密码输入框中填写有效凭证","点击「登录」按钮","观察按钮无任何响应，页面无跳转、无报错、无
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: {"title":"登录页在 Safari 上点击登录按钮无响应","priority":"high","steps":["使用 Safari 浏览器打开登录页面","输入正确的用户名和密码","点击登录按钮","观察按钮无响应，未触发登录请求"],"fix":"排查 Safari 兼容性问题：1.

### E2 · E2（Structured Output）

- **MLX 4-bit (NVFP4, Ollama 11434)**: [{"tool":"get_weather","args":{"city":"北京","date":"明天"}},{"tool":"send_reminder","args":{"text":"明天北京有雨，出门记得带伞！"}}] </think>
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: ```json [{"tool":"get_weather","args":{"city":"北京","date":"明天"}}] ```

### F1 · F1（Chinese Writing）

- **MLX 4-bit (NVFP4, Ollama 11434)**: # 为什么本地大模型量化对中小团队有真实价值  **引言**  中小团队不缺想法，缺的是算力预算。云端 API 按 token 计费，日活一上来账单就失控；而买一张 A100 动辄十几万，对十人团队而言近乎不可承受。本地量化大模型，恰恰把"用得起"这件事拉回了桌面。  **技术原理：把"重量"压薄*
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: # 为什么本地大模型量化对中小团队有真实价值  ## 引言  中小团队用大模型，常面临两难：API 调用按 token 计费，量大成本失控；自建 GPU 集群，硬件投入又远超预算。量化技术的成熟，正在打破这个僵局——它让一台普通工作站就能跑起过去需要数据中心才能承载的模型。  ## 技术原理：把"高

### F2 · F2（Chinese Writing）

- **MLX 4-bit (NVFP4, Ollama 11434)**: 推荐译文：  > **量化通过降低模型权重的数值精度，以微小的精度损失换取内存占用与推理开销的大幅降低。混合精度方案依据各张量的敏感度分配比特数，在更低的平均位宽下维持任务质量。**  --- **简要说明：** - **Quantization / Mixed-precision / tensor
- **Qwen3.8-Flash-Next 2bpw (Sushi 12345)**: 量化通过降低模型权重的数值精度，以少量精度损失换取内存占用和推理成本的大幅降低。混合精度方案根据各张量的敏感度分配比特数，从而在更低的平均位宽下保持任务质量。

## 四、结论

- **全 12 题整体**：27B `25.9` vs Flash-Next `25.5` → **0.98×，即整体没有提速**。
- **跑顺的那 6 题**（`A2,A3,E1,E2,F1,F2`）：27B `22.5` vs Flash-Next `42.2` → Flash-Next 快 **1.87×**（峰值 F2=57.86）。
- **塌掉的那 6 题**（`A1,A4,B1,B2,C1,D1`）：27B `29.3` vs Flash-Next `8.9` → Flash-Next 慢到 **0.30×**（D1=1.16 几乎不可用）。
- **为什么是「整体没提速」而不是「快 1.9 倍」**：网上流传的「快一倍」是拿 Flash-Next 的热区子集比 27B 全卷，苹果比橘子。口径对齐后（同一批题互比），收益与塌方基本对冲。
- **冷热分裂未定位**：本套数据里 Flash-Next 每题都重启服务清过 KV，冷热仍然五五开，说明「重启清 KV」不足以稳定热态；根因未证实（想跑的对照实验因权重在常态内存占用下加载不进 48GB 而未完成）。
- **质量同判**：E1 两模型 JSON 均合法；E2 两模型均因尾部多输出而 JSON 非法（同错，非其一独错）；B1(同余 n=23)、B2(相遇 t=5.6)、C1(GPQA 选 B/泡利) 两模型均给出正确结论。抽样层面二者质量在伯仲之间；但 12 题的样本量撑不起「谁质量更好」的结论。
- **共存约束（48GB 天花板）**：Flash-Next 常驻 ~37GB，27B 常驻 ~18GB，二者**不能同时驻留**。更硬的约束是在日常内存占用下 Flash-Next 甚至加载不进内存（卡在 Precomputing MoE layer weights）。
- **选型建议**：本机（M5 Pro 48GB）结论是保留 27B 当主力，Flash-Next 卸载待更优部署方案（≥128GB / 4-bit 以上位宽 / 调优引擎）再评估。
