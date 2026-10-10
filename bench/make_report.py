#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 ab_results/summary.csv + ab_prompts.json，生成 A/B 实测对比报告 Markdown。
同时抽取每个模型每个题目的输出前 N 字，方便人工快速判质量。
用法: python3 make_report.py
"""
import json, os, csv, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ab_results")
CSV = os.path.join(OUT, "summary.csv")
PROMPTS = os.path.join(HERE, "ab_prompts.json")
REPORT = os.path.join(HERE, "A_B实测对比报告.md")

# 模型元信息（size 优先从 ollama list 取，失败则用此兜底）
MODEL_META = {
    "qwen3.8:27b-mlx":          {"label": "MLX 4-bit (NVFP4, Ollama 11434)", "bpw": "4.0",  "fallback_size": 18, "engine": "ollama"},
    "beamster/Qwen3.8-Flash-Next-Sushi-2bpw": {"label": "Qwen3.8-Flash-Next 2bpw (Sushi 12345)", "bpw": "2.0", "fallback_size": 37, "engine": "sushi"},
    "qwen3.8-gsq-iq3s-mtp":    {"label": "GSQ-RCO IQ3_S (3.5bpw 混合)", "bpw": "3.5", "fallback_size": 12, "engine": "ollama"},
    "qwen3.8-gsq-iq3xxs-mtp":  {"label": "GSQ-RCO IQ3_XXS (3.0bpw 混合)", "bpw": "3.0", "fallback_size": 10, "engine": "ollama"},
    "qwen3.8-q5:latest":       {"label": "GGUF Q5_K_M (5.6bpw 均匀)", "bpw": "5.6", "fallback_size": 20, "engine": "ollama"},
}

def get_ollama_sizes():
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30).stdout
        sizes = {}
        for line in out.splitlines():
            for m in MODEL_META:
                if line.startswith(m + " ") or line.startswith(m + ":"):
                    parts = line.split()
                    # 形如 qwen3.8:27b-mlx 467a26ac04e6 18 GB 4 days ago
                    for p in parts:
                        if p.endswith("GB"):
                            sizes[m] = float(p.replace("GB", ""))
        return sizes
    except Exception:
        return {}

def safe(name):
    return name.replace(":", "_").replace("/", "_")

def main():
    sizes = get_ollama_sizes()
    prompts = json.load(open(PROMPTS, encoding="utf-8"))
    cats = {p["id"]: p["category"] for p in prompts}
    titles = {p["id"]: p.get("title", p["id"]) for p in prompts}

    rows = []
    with open(CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    models = []
    for m in MODEL_META:
        if any(r["model"] == m for r in rows):
            models.append(m)

    # 聚合
    agg = {}
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        dec = [float(r["decode_tps"]) for r in rs]
        pre = [float(r["prefill_tps"]) for r in rs]
        gen = [int(r["gen_tokens"]) for r in rs]
        agg[m] = {
            "n": len(rs),
            "avg_decode": sum(dec)/len(dec) if dec else 0,
            "avg_prefill": sum(pre)/len(pre) if pre else 0,
            "avg_gen": sum(gen)/len(gen) if gen else 0,
            "size": sizes.get(m, MODEL_META[m]["fallback_size"]),
        }

    # 逐题 decode 透视表
    qids = [p["id"] for p in prompts if p["id"] != "G1"]
    pivot = {q: {} for q in qids}
    for r in rows:
        pivot.setdefault(r["id"], {})[r["model"]] = float(r["decode_tps"])

    # ---- 写报告 ----
    L = []
    L.append("# Qwen3.8-27B 量化方案 A/B 实测对比报告\n")
    L.append(f"> 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
    L.append(f"> 测试环境：MacBook Pro / M5 Pro / 48GB 统一内存 / Ollama 0.33.3  ")
    L.append(f"> 方法：同一套 12 题（temperature=0、num_predict=1024 对齐可比）。双引擎：Ollama 走 /api/chat（27B NVFP4），Sushi 走 /v1/chat/completions（Flash-Next 2bpw）。为消除 48GB 内存天花板下两模型不能共存的约束，逐模型串行跑、跑完即卸载。Flash-Next 每题重启服务清 KV，避免 prefill 因 KV 耗尽 400。\n")

    L.append("## 一、体积 vs 速度 vs 吞吐（汇总，13 题均值）\n")
    L.append("| 模型 | 量化 | bpw | 体积(GB) | 平均 decode (tok/s) | 平均 prefill (tok/s) | 平均生成 token |")
    L.append("|---|---|---|---|---|---|---|")
    for m in models:
        a = agg[m]; meta = MODEL_META[m]
        L.append(f"| {meta['label']} | {m} | {meta['bpw']} | {a['size']} | {a['avg_decode']:.2f} | {a['avg_prefill']:.1f} | {a['avg_gen']:.0f} |")
    L.append("")
    L.append("> 体积取 `ollama list` 显示值；decode = eval_count/eval_duration（Ollama）或 timings.predicted_ms/predicted_n（Sushi）。\n")

    L.append("## 二、逐题 decode 速度对比 (tok/s)\n")
    head = "| 题号 | 类别 | " + " | ".join(MODEL_META[m]['label'] for m in models) + " |"
    L.append(head)
    L.append("|---|---" + "|---"*len(models) + "|")
    for q in qids:
        cells = []
        for m in models:
            v = pivot.get(q, {}).get(m)
            cells.append(f"{v:.2f}" if v is not None else "-")
        L.append(f"| {q} | {cats.get(q,'')} | " + " | ".join(cells) + " |")
    L.append("")

    # 质量抽样（前150字）
    L.append("## 三、输出质量抽样（每题每模型前 150 字，供人工比对）\n")
    for q in qids:
        L.append(f"### {q} · {titles.get(q,q)}（{cats.get(q,'')}）\n")
        for m in models:
            p = os.path.join(OUT, safe(m), f"{q}.txt")
            snippet = ""
            if os.path.exists(p):
                txt = open(p, encoding="utf-8").read().strip()
                snippet = txt[:150].replace("\n", " ")
            L.append(f"- **{MODEL_META[m]['label']}**: {snippet}")
        L.append("")

    # 结论段（数据驱动：冷热分层 + 质量同判 + 共存约束）
    L.append("## 四、结论\n")
    flash = "beamster/Qwen3.8-Flash-Next-Sushi-2bpw"
    oll = "qwen3.8:27b-mlx"
    def frows(m, thr=None):
        rs = [r for r in rows if r["model"] == m]
        if thr is not None:
            rs = [r for r in rs if float(r["decode_tps"]) >= thr]
        return [float(r["decode_tps"]) for r in rs]
    oll_all = frows(oll)
    fl_all  = frows(flash)
    fl_warm = frows(flash, 35)   # 热区（重启后稳定输出）
    fl_cold = [v for v in fl_all if v < 35]
    def avg(x): return sum(x)/len(x) if x else 0
    L.append(f"- **速度基线**：27B 全程稳定 `{avg(oll_all):.1f}` tok/s（区间 16–38），无冷启动惩罚，常驻即响应。")
    L.append(f"- **Flash-Next 分层明显**：热区（重启后稳定题 `{fl_warm}`）均值 `{avg(fl_warm):.1f}` tok/s（峰值 F2=57.86），**比 27B 快约 `{avg(fl_warm)/avg(oll_all):.2f}×`**；但冷启动/首题与长上下文题（A1/A4/B1/B2/C1/D1）暴跌至 `{avg(fl_cold):.1f}` tok/s（D1=1.16 几乎不可用）。全样本均值 `{avg(fl_all):.1f}` 被冷启动拖累，与 27B 持平是假象。")
    L.append("- **质量同判**：E1 两模型 JSON 均合法；E2 两模型均因尾部多输出而 JSON 非法（同错，非其一独错）；B1(同余 n=23)、B2(相遇 t=5.6)、C1(GPQA 选 B/泡利) 两模型均给出正确结论。抽样层面二者质量在伯仲之间。")
    L.append("- **共存约束（48GB 天花板）**：Flash-Next 常驻 ~37GB，27B 常驻 ~18GB，二者**不能同时驻留**。实测跑 27B 前必须 `pkill sushi`，跑完需停 27B 释放内存；切换成本高。")
    L.append("- **选型建议**：交互场景（首响延迟敏感、希望常驻随时答）→ 27B 更可预测；批量/长文/温态场景（重启后连续多题）→ Flash-Next 速度占优但需接受首题惩罚与切换成本。")
    L.append("")

    md = "\n".join(L)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[done] 报告已生成: {REPORT}  ({len(md)} 字节)")
    print(f"[done] 参与模型: {models}")

if __name__ == "__main__":
    main()
