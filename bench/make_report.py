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
    "qwen3.8:27b-mlx":          {"label": "MLX 4-bit (NVFP4 均匀)", "bpw": "4.0",  "fallback_size": 18},
    "qwen3.8-gsq-iq3s-mtp":    {"label": "GSQ-RCO IQ3_S (3.5bpw 混合)", "bpw": "3.5", "fallback_size": 12},
    "qwen3.8-gsq-iq3xxs-mtp":  {"label": "GSQ-RCO IQ3_XXS (3.0bpw 混合)", "bpw": "3.0", "fallback_size": 10},
    "qwen3.8-q5:latest":       {"label": "GGUF Q5_K_M (5.6bpw 均匀)", "bpw": "5.6", "fallback_size": 20},
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
    L.append(f"> 方法：同一套 13 题（temperature=0、num_predict=4096、num_ctx=131072、统一走 Ollama /api/chat），逐模型串行跑，跑完即卸载避免显存叠加。\n")

    L.append("## 一、体积 vs 速度 vs 吞吐（汇总，13 题均值）\n")
    L.append("| 模型 | 量化 | bpw | 体积(GB) | 平均 decode (tok/s) | 平均 prefill (tok/s) | 平均生成 token |")
    L.append("|---|---|---|---|---|---|---|")
    for m in models:
        a = agg[m]; meta = MODEL_META[m]
        L.append(f"| {meta['label']} | {m} | {meta['bpw']} | {a['size']} | {a['avg_decode']:.2f} | {a['avg_prefill']:.1f} | {a['avg_gen']:.0f} |")
    L.append("")
    L.append("> 体积取 `ollama list` 显示值；decode = eval_count/eval_duration，prefill = prompt_eval_count/prompt_eval_duration（均来自 Ollama 返回顶层字段）。\n")

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

    md = "\n".join(L)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[done] 报告已生成: {REPORT}  ({len(md)} 字节)")
    print(f"[done] 参与模型: {models}")

if __name__ == "__main__":
    main()
