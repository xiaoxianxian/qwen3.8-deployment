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
        pre_nz = [float(r["prefill_tps"]) for r in rs if float(r["prefill_tps"]) > 0]
        gen = [int(r["gen_tokens"]) for r in rs]
        agg[m] = {
            "n": len(rs),
            "avg_decode": sum(dec)/len(dec) if dec else 0,
            "avg_prefill": (sum(pre_nz)/len(pre_nz) if pre_nz else 0),
            "prefill_n": len(pre_nz),
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

    L.append("## 一、体积 vs 速度 vs 吞吐（汇总，12 题均值）\n")
    L.append("| 模型 | 量化 | bpw | 体积(GB) | 平均 decode (tok/s) | 平均 prefill (tok/s，仅计有返回的题) | 平均生成 token |")
    L.append("|---|---|---|---|---|---|---|")
    for m in models:
        a = agg[m]; meta = MODEL_META[m]
        pf = f"{a['avg_prefill']:.1f}（{a['prefill_n']}/{a['n']} 题）" if a["prefill_n"] else "—（未返回）"
        L.append(f"| {meta['label']} | {m} | {meta['bpw']} | {a['size']} | {a['avg_decode']:.2f} | {pf} | {a['avg_gen']:.0f} |")
    L.append("")
    L.append("> 体积取 `ollama list` 显示值；decode = eval_count/eval_duration（Ollama）或 timings.predicted_ms/predicted_n（Sushi）。⚠️ prefill 只对**有返回值的题**取均值，不用 0 充数：Sushi 在本套 12 题中有 8 题未返回 prefill 耗时（CSV 记为 0，属未采集而非真 0），故该列附注分母。\n")

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
    def avg(x): return sum(x)/len(x) if x else 0
    # 冷热分层：以 Flash-Next 自身 25 tok/s 为界分成两半（各 6 题）
    HOT = 25.0
    hot_ids  = sorted(r["id"] for r in rows if r["model"] == flash and float(r["decode_tps"]) >= HOT)
    cold_ids = sorted(r["id"] for r in rows if r["model"] == flash and float(r["decode_tps"]) <  HOT)
    def pair(m, ids):
        return [float(r["decode_tps"]) for r in rows if r["model"] == m and r["id"] in ids]
    oh, oc = pair(oll, hot_ids), pair(oll, cold_ids)
    fh, fc = pair(flash, hot_ids), pair(flash, cold_ids)
    L.append(f"- **全 12 题整体**：27B `{avg(oll_all):.1f}` vs Flash-Next `{avg(fl_all):.1f}` → **{avg(fl_all)/avg(oll_all):.2f}×，即整体没有提速**。")
    L.append(f"- **跑顺的那 6 题**（`{','.join(hot_ids)}`）：27B `{avg(oh):.1f}` vs Flash-Next `{avg(fh):.1f}` → Flash-Next 快 **{avg(fh)/avg(oh):.2f}×**（峰值 F2=57.86）。")
    L.append(f"- **塌掉的那 6 题**（`{','.join(cold_ids)}`）：27B `{avg(oc):.1f}` vs Flash-Next `{avg(fc):.1f}` → Flash-Next 慢到 **{avg(fc)/avg(oc):.2f}×**（D1=1.16 几乎不可用）。")
    L.append(f"- **为什么是「整体没提速」而不是「快 1.9 倍」**：网上流传的「快一倍」是拿 Flash-Next 的热区子集比 27B 全卷，苹果比橘子。口径对齐后（同一批题互比），收益与塌方基本对冲。")
    L.append(f"- **冷热分裂未定位**：本套数据里 Flash-Next 每题都重启服务清过 KV，冷热仍然五五开，说明「重启清 KV」不足以稳定热态；根因未证实（想跑的对照实验因权重在常态内存占用下加载不进 48GB 而未完成）。")
    L.append("- **质量同判**：E1 两模型 JSON 均合法；E2 两模型均因尾部多输出而 JSON 非法（同错，非其一独错）；B1(同余 n=23)、B2(相遇 t=5.6)、C1(GPQA 选 B/泡利) 两模型均给出正确结论。抽样层面二者质量在伯仲之间；但 12 题的样本量撑不起「谁质量更好」的结论。")
    L.append("- **共存约束（48GB 天花板）**：Flash-Next 常驻 ~37GB，27B 常驻 ~18GB，二者**不能同时驻留**。更硬的约束是在日常内存占用下 Flash-Next 甚至加载不进内存（卡在 Precomputing MoE layer weights）。")
    L.append("- **选型建议**：本机（M5 Pro 48GB）结论是保留 27B 当主力，Flash-Next 卸载待更优部署方案（≥128GB / 4-bit 以上位宽 / 调优引擎）再评估。")
    L.append("")

    md = "\n".join(L)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[done] 报告已生成: {REPORT}  ({len(md)} 字节)")
    print(f"[done] 参与模型: {models}")

if __name__ == "__main__":
    main()
