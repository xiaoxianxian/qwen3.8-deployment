#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ollama vs Shimmy 同 GGUF A/B 基准
两侧加载的是同一个 GGUF 文件，同 prompt、同 temperature=0、同输出上限，交错跑 3 轮。
Shimmy 的 /api/generate 不返回 eval_count，tok/s 用 Ollama 报告的 token 数做共同分母。
"""
import json, time, urllib.request, os

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
SHIMMY_URL = "http://127.0.0.1:11436/api/generate"
OLLAMA_MODEL = "qwen3-0.6b-q8:latest"
SHIMMY_MODEL = "Qwen3-0.6B-Q8_0"
PROMPT = ("Write a short paragraph about why local model inference matters for privacy. "
          "Keep it under 80 words.")
NUM_PREDICT = 96
ROUNDS = 3
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)
METRICS = ("eval_count", "eval_duration", "prompt_eval_count", "prompt_eval_duration")


def run(url, payload, is_shimmy):
    t0 = time.time()
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    text, ttft, meta, done_at = "", None, {}, None
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            for raw in r:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line == "[DONE]":
                    continue
                try:
                    d = json.loads(line[5:].strip()) if line.startswith("data:") and \
                        line[5:].strip().startswith("{") else (
                        json.loads(line) if line.startswith("{") else None)
                except Exception:
                    d = None
                if d is None:
                    piece = line[5:] if line.startswith("data:") else ""
                else:
                    piece = d.get("response") or ""
                    for k in METRICS:
                        if k in d:
                            meta[k] = d[k]
                    if d.get("done"):
                        done_at = time.time() - t0
                if piece:
                    if ttft is None:
                        ttft = time.time() - t0
                    text += piece
    except Exception as e:
        return {"error": str(e), "text": ""}
    wall = time.time() - t0
    ec, ed = meta.get("eval_count") or 0, meta.get("eval_duration") or 0
    return {"wall": round(wall, 2), "ttft": round(ttft or 0, 3), "text": text,
            "eval_count": ec, "tps": round(ec / (ed / 1e9), 2) if ec and ed else None}


rows = []
for i in range(ROUNDS):
    for engine, url, model in (("ollama", OLLAMA_URL, OLLAMA_MODEL),
                               ("shimmy", SHIMMY_URL, SHIMMY_MODEL)):
        payload = {"model": model, "prompt": PROMPT, "num_predict": NUM_PREDICT,
                   "stream": True, "think": False,
                   "options": {"temperature": 0, "num_predict": NUM_PREDICT}}
        res = run(url, payload, engine == "shimmy")
        rec = {"round": i + 1, "engine": engine, "wall_s": res["wall"],
               "ttft_s": res["ttft"], "chars": len(res["text"]),
               "eval_count": res["eval_count"], "server_tps": res["tps"],
               "error": res.get("error", "")}
        rows.append(rec)
        print(f"[{engine}] r{i+1}: wall={rec['wall_s']}s ttft={rec['ttft_s']}s "
              f"chars={rec['chars']} eval_count={rec['eval_count']} "
              f"server_tps={rec['server_tps']} {rec['error']}")
        with open(os.path.join(OUT, f"{engine}_r{i+1}.txt"), "w", encoding="utf-8") as f:
            f.write(res["text"][:400])
        time.sleep(1)

csv_path = os.path.join(OUT, "ab_summary.csv")
with open(csv_path, "w", encoding="utf-8", newline="") as f:
    f.write("round,engine,wall_s,ttft_s,chars,eval_count,server_tps,error\n")
    for r in rows:
        f.write(f"{r['round']},{r['engine']},{r['wall_s']},{r['ttft_s']},{r['chars']},"
                f"{r['eval_count']},{r['server_tps']},{r['error']}\n")
print(f"\n[done] {csv_path}")
