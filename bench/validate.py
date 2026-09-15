#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""严格质量校验：JSON 可解析性 + 数学题最终答案 + 知识题选项。"""
import os, json, re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ab_results")
MODELS = {
    "qwen3.8:27b-mlx": "MLX 4-bit",
    "qwen3.8-gsq-iq3s-mtp": "IQ3_S",
    "qwen3.8-gsq-iq3xxs-mtp": "IQ3_XXS",
    "qwen3.8-q5:latest": "Q5",
}
def safe(n): return n.replace(":", "_").replace("/", "_")

def read(q, m):
    p = os.path.join(OUT, safe(m), f"{q}.txt")
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""

print("=== E1 / E2 JSON 严格解析 ===")
for q in ("E1", "E2"):
    print(f"-- {q} --")
    for m, lab in MODELS.items():
        t = read(q, m)
        ok = False; err = ""
        try:
            json.loads(t); ok = True
        except Exception as e:
            # 尝试抽取首个 { 或 [ 之后的内容
            s = t.find("{") if "{" in t else t.find("[")
            if s >= 0:
                try: json.loads(t[s:]); ok = True; err="(已截断前缀)"
                except Exception as e2: err = str(e2)[:40]
        print(f"  {lab:10s}: {'VALID' if ok else 'INVALID'} {err}")

print("\n=== B1 同余方程（标准答案 n=23）===")
for m, lab in MODELS.items():
    t = read("B1", m)
    nums = re.findall(r"n\s*[=＝]\s*(\d+)", t)
    # 找最后一个 =数字 或 明确结论
    conclusion = ""
    for kw in ["最小正整数", "因此", "所以", "答案", "解得", "最终", "综上"]:
        i = t.find(kw)
        if i >= 0:
            conclusion = t[i:i+120].replace("\n"," ")
    print(f"  {lab:10s}: 提及n= {nums[-3:] if nums else '无'} | 结论片段: {conclusion[:90]}")

print("\n=== B2 相遇问题（标准答案：乙出发后 t=5.6 小时相遇）===")
for m, lab in MODELS.items():
    t = read("B2", m)
    # 找 t = 数字 或 相遇时间结论
    ts = re.findall(r"t\s*[=＝]\s*([\d.]+)", t)
    frac = re.findall(r"(\d+/\d+)\s*h", t)
    conclusion = ""
    for kw in ["相遇", "答案", "因此", "所以", "解得"]:
        i = t.find(kw)
        if i >= 0:
            conclusion = t[max(0,i-10):i+110].replace("\n"," "); break
    print(f"  {lab:10s}: t={ts[-3:] if ts else '无'} frac={frac[:2]} | {conclusion[:90]}")

print("\n=== C1 知识题选项（标准答案 B：泡利不相容/费米子）===")
for m, lab in MODELS.items():
    t = read("C1", m)
    # 找 正确答案：X
    m1 = re.search(r"正确答案[：:]\s*\(?([A-D])\)?", t)
    letter = m1.group(1) if m1 else "?"
    has_pauli = "泡利" in t or "Pauli" in t
    print(f"  {lab:10s}: 选项={letter} 含泡利阐述={'Y' if has_pauli else 'N'}")
