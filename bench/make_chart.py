#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Flash-Next vs 27B 12 题 decode 速度对比图（公众号配图）。"""
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

ART = "/Users/xiaota/Documents/AI项目/本地部署Qwen3.8"
CSV = os.path.join(ART, "bench/ab_results/summary.csv")
OUT = os.path.join(ART, "配图-12题速度对比-FlashNext-vs-27B.png")

FN = "beamster/Qwen3.8-Flash-Next-Sushi-2bpw"
B27 = "qwen3.8:27b-mlx"

# ---- 中文字体 ----
cands = ["PingFang SC", "PingFang HK", "Heiti TC", "STHeiti", "Songti SC",
         "Hiragino Sans GB", "Arial Unicode MS"]
avail = {f.name for f in font_manager.fontManager.ttflist}
chosen = next((c for c in cands if c in avail), None)
if chosen:
    plt.rcParams["font.sans-serif"] = [chosen]
plt.rcParams["axes.unicode_minus"] = False
print("font:", chosen or "NONE(fallback)")

# ---- 读数据 ----
rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
order = ["A1", "A2", "A3", "A4", "B1", "B2", "C1", "D1", "E1", "E2", "F1", "F2"]
cat = {"A1": "代码生成", "A2": "代码生成", "A3": "代码生成", "A4": "代码生成",
       "B1": "数学推理", "B2": "数学推理", "C1": "知识问答", "D1": "长上下文",
       "E1": "结构化输出", "E2": "结构化输出", "F1": "中文写作", "F2": "中文写作"}
d = {}
for r in rows:
    d.setdefault(r["id"], {})[r["model"]] = float(r["decode_tps"])

b27 = [d[i][B27] for i in order]
fn = [d[i][FN] for i in order]
labels = [f"{i}\n{c}" for i, c in zip(order, [cat[i] for i in order])]

C27, CFN = "#1F8A5C", "#E07B2E"

fig, ax = plt.subplots(figsize=(13, 7.5), dpi=200)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

y = range(len(order))
h = 0.38
b1 = ax.barh([i + h / 2 for i in y], b27, height=h, color=C27, label="27B（Ollama）")
b2 = ax.barh([i - h / 2 for i in y], fn, height=h, color=CFN, label="Flash-Next（Sushi）")

# 数值标注
for bar in list(b1) + list(b2):
    w = bar.get_width()
    ax.text(w + 0.9, bar.get_y() + bar.get_height() / 2, f"{w:.1f}",
            va="center", ha="left", fontsize=9.5, color="#333333")

ax.set_yticks(list(y))
ax.set_yticklabels(labels, fontsize=10.5, color="#222222")
ax.invert_yaxis()
ax.set_xlabel("decode 速度（token/秒）", fontsize=11.5, color="#333333")
ax.set_xlim(0, 68)

# 均值参考线
import statistics as st
m27, mfn = st.mean(b27), st.mean(fn)
ax.axvline(m27, color=C27, ls="--", lw=1.4, alpha=0.85)
ax.axvline(mfn, color=CFN, ls="--", lw=1.6, alpha=0.9)
ax.text(m27 - 0.8, -0.75, f"27B 均值 {m27:.1f}", color=C27,
        fontsize=10.5, ha="right", va="center", fontweight="bold")
ax.text(mfn + 0.8, len(order) - 0.05, f"Flash-Next 均值 {mfn:.1f}（几乎与 27B 重合）",
        color=CFN, fontsize=10.5, ha="left", va="center", fontweight="bold")
ax.set_ylim(len(order) + 0.6, -1.25)

# 右左侧分别标「跑顺的一半 / 塌方的一半」
slow_idx = [i for i, v in enumerate(fn) if v < 20]
if slow_idx:
    ax.axhspan(min(slow_idx) - 0.55, max(slow_idx) + 0.55,
               color="#E07B2E", alpha=0.055, zorder=0)

for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#DDDDDD")
ax.tick_params(axis="x", colors="#555555")
ax.xaxis.grid(True, color="#EFEFEF", lw=1)
ax.set_axisbelow(True)

ax.set_title("12 题本机实测：整体均值打平，收益与塌方各占一半",
             fontsize=15, fontweight="bold", color="#111111", pad=16, loc="left")
ax.text(0, -0.9, "M5 Pro / 48GB / macOS · Flash-Next 2bpw(Sushi) vs 27B NVFP4(Ollama) · 2026-10-10 · 同 12 题 temperature=0",
        fontsize=9.5, color="#888888", transform=ax.transAxes, ha="left")

handles = [b1[0], b2[0]]
ax.legend(handles, ["27B（Ollama, NVFP4）", "Flash-Next（Sushi, 2bpw）"],
          loc="upper right", frameon=False, fontsize=11, ncol=1,
          bbox_to_anchor=(1.0, 1.02))

plt.tight_layout()
plt.savefig(OUT, dpi=200, facecolor="white", bbox_inches="tight")
print("saved:", OUT, os.path.getsize(OUT), "bytes")
