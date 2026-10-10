#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冷启动缓解实测：单实例 sushi，按顺序发请求，测 D1/A1 在「冷首题」vs「热机后重发」的 decode 是否回升。
基线（A_B实测对比报告.md）：D1=1.16 t/s，A1=11.81 t/s，F1=41.99 t/s。
若 D1_after_warmup / A1_after_warmup 回到 ~40 → 首题冷可绕过 → 全押路线可行。
若仍 ~1-12 → 结构性（长上下文/KV），需引擎修复。
"""
import json, time, urllib.request, os

SUSHI = "http://127.0.0.1:12345"
HERE = os.path.dirname(os.path.abspath(__file__))
prompts = json.load(open(os.path.join(HERE, "ab_prompts.json"), encoding="utf-8"))
by_id = {p["id"]: p["prompt"] for p in prompts}
WARMUP = "Reply with the single word: OK."


def ask(prompt, max_tokens=256, tag=""):
    body = {
        "model": "beamster/Qwen3.8-Flash-Next-Sushi-2bpw",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "reasoning_effort": "low",
    }
    req = urllib.request.Request(
        SUSHI + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as resp:
        out = json.loads(resp.read().decode())
    wall = time.time() - t0
    t = out.get("timings", {})
    pn, pms = t.get("predicted_n", 0), t.get("predicted_ms", 0)
    dec = round(pn / (pms / 1000), 2) if pms else 0
    pfn, pfms = t.get("prompt_n", 0), t.get("prompt_ms", 0)
    pref = round(pfn / (pfms / 1000), 2) if pfms else 0
    return {"tag": tag, "decode": dec, "prefill": pref, "gen": pn, "wall": round(wall, 1)}


seq = [
    ("D1_first",         by_id["D1"], 256),
    ("warmup1",         WARMUP,        16),
    ("D1_after_warmup",  by_id["D1"], 256),
    ("A1_first",         by_id["A1"], 256),
    ("warmup2",         WARMUP,        16),
    ("A1_after_warmup",  by_id["A1"], 256),
    ("F1_sanity",        by_id["F1"], 256),
]

rows = []
for tag, p, mt in seq:
    r = ask(p, mt, tag)
    rows.append(r)
    print(f"{tag:20s} decode={r['decode']:8.2f} t/s  prefill={r['prefill']:8.2f}  gen={r['gen']}  wall={r['wall']}s", flush=True)
    time.sleep(1)

with open(os.path.join(HERE, "cold_start_test.csv"), "w", encoding="utf-8") as f:
    f.write("tag,decode_tps,prefill_tps,gen_tokens,wall_s\n")
    for r in rows:
        f.write(f"{r['tag']},{r['decode']},{r['prefill']},{r['gen']},{r['wall']}\n")
print("saved cold_start_test.csv")
