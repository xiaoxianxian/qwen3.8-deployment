#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen3.8 A/B 跑测脚本：对比 qwen3.8:27b-mlx (4-bit NVFP4) 与 GSQ-RCO IQ3_S-mtp (3.5bpw)
用法:
  python3 ab_run.py                 # 跑全部（默认两个模型）
  python3 ab_run.py --models m1 m2 # 指定模型
  python3 ab_run.py --only A1 B1   # 只跑指定题
  python3 ab_run.py --vision       # 包含 G1 视觉题
  python3 ab_run.py --base http://localhost:11434
输出: ab_results/<model>/<id>.txt + ab_results/summary.csv
Ollama 通过 /api/chat 返回 eval_count / eval_duration，直接算出解码速度，无需外部计时。
"""
import json, sys, os, time, argparse, subprocess, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "ab_prompts.json")
OUT = os.path.join(HERE, "ab_results")
DEFAULT_MODELS = ["qwen3.8:27b-mlx", "qwen3.8-gsq-iq3s-mtp", "qwen3.8-gsq-iq3xxs-mtp", "qwen3.8-q5:latest"]

def load_prompts():
    with open(PROMPTS, "r", encoding="utf-8") as f:
        return json.load(f)

def chat(base, model, prompt, num_ctx=131072, num_predict=4096, timeout=600):
    url = base.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    wall = time.time() - t0
    msg = out.get("message", {})
    content = msg.get("content", "")
    # Ollama /api/chat (stream:false) 把 metrics 放在顶层，没有 metrics 子对象
    eval_count = out.get("eval_count", 0)
    eval_dur = out.get("eval_duration", 0)  # ns
    pe_count = out.get("prompt_eval_count", 0)
    pe_dur = out.get("prompt_eval_duration", 0)
    decode_tps = (eval_count / (eval_dur / 1e9)) if eval_dur else 0
    prefill_tps = (pe_count / (pe_dur / 1e9)) if pe_dur else 0
    return {
        "content": content,
        "eval_count": eval_count,
        "decode_tps": round(decode_tps, 2),
        "prompt_eval_count": pe_count,
        "prefill_tps": round(prefill_tps, 2),
        "wall_s": round(wall, 2),
    }

def safe(name):
    return name.replace(":", "_").replace("/", "_")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--only", nargs="+", default=None)
    ap.add_argument("--base", default="http://localhost:11434")
    ap.add_argument("--vision", action="store_true", help="包含 G1 视觉题")
    ap.add_argument("--num-predict", type=int, default=4096)
    args = ap.parse_args()

    prompts = load_prompts()
    if not args.vision:
        prompts = [p for p in prompts if p["id"] != "G1"]
    if args.only:
        prompts = [p for p in prompts if p["id"] in args.only]

    os.makedirs(OUT, exist_ok=True)
    summary_rows = []

    for model in args.models:
        mdir = os.path.join(OUT, safe(model))
        os.makedirs(mdir, exist_ok=True)
        print(f"\n===== MODEL: {model} =====")
        for p in prompts:
            out_path = os.path.join(mdir, f"{p['id']}.txt")
            if os.path.exists(out_path):
                print(f"  [skip] {p['id']} (exists)")
                continue
            print(f"  [run ] {p['id']} ({p['category']}) ...", flush=True)
            try:
                r = chat(args.base, model, p["prompt"], num_predict=args.num_predict)
            except urllib.error.HTTPError as e:
                print(f"  [ERR ] {p['id']}: HTTP {e.code} {e.read().decode()[:200]}", flush=True)
                continue
            except Exception as e:
                print(f"  [ERR ] {p['id']}: {e}", flush=True)
                continue
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(r["content"])
            print(f"         decode={r['decode_tps']} t/s, gen={r['eval_count']}tok, wall={r['wall_s']}s", flush=True)
            summary_rows.append({
                "model": model, "id": p["id"], "category": p["category"],
                "decode_tps": r["decode_tps"], "prefill_tps": r["prefill_tps"],
                "gen_tokens": r["eval_count"], "wall_s": r["wall_s"],
            })
            time.sleep(0.5)

        # 该模型全部题跑完，立即卸载，避免三模型显存叠加 OOM
        try:
            subprocess.run(["ollama", "stop", model], capture_output=True, timeout=30)
            print(f"  [stop] 已卸载 {model}")
        except Exception as e:
            print(f"  [stop-warn] {model}: {e}")

    # 写 summary.csv（合并已有行，避免分模型多次运行时覆盖）
    csv_path = os.path.join(OUT, "summary.csv")
    seen = set()
    merged = []
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        for l in lines[1:]:  # skip header
            parts = l.split(",")
            if len(parts) >= 2:
                seen.add((parts[0], parts[1]))
                merged.append(l)
    for r in summary_rows:
        key = (r["model"], r["id"])
        if key in seen:
            continue
        merged.append(f"{r['model']},{r['id']},{r['category']},{r['decode_tps']},{r['prefill_tps']},{r['gen_tokens']},{r['wall_s']}")
        seen.add(key)
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("model,id,category,decode_tps,prefill_tps,gen_tokens,wall_s\n")
        for l in merged:
            f.write(l + "\n")
    print(f"\n[done] 结果目录: {OUT}\n[done] 汇总: {csv_path}")

if __name__ == "__main__":
    main()
