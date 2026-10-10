#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一 A/B 跑测：同一份 ab_prompts.json，对 Ollama(11434 /api/chat) 与 sushi(12345 /v1)
两类端点各模型串行跑 12 题，速度从各自响应里取（Ollama eval_count/duration；
sushi 从 response.timings 的 predicted/prompt 毫秒数算）。

用法:
  # 先跑 Flash-Next(sushi)：此时 27B 必须已 stop
  python3 ab_run_unified.py --sushi beamster/Qwen3.8-Flash-Next-Sushi-2bpw
  # 再跑 27B(ollama)：sushi 已 kill
  python3 ab_run_unified.py --ollama qwen3.8:27b-mlx

说明:
  - 结果写 ab_results/<safe_model>/<id>.txt + ab_results/summary.csv（按 model,id 去重合并）
  - sushi 走 OpenAI /v1/chat/completions，speed 来自 response.timings.predicted_ms/predicted_n
  - Ollama 走 /api/chat，speed 来自 eval_count/eval_duration（同 ab_run.py 口径）
  - 两模型不能同时驻留 48G，调用方负责串行（先 kill 一个再起另一个）
"""
import json, sys, os, time, argparse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "ab_prompts.json")
OUT = os.path.join(HERE, "ab_results")
OLLAMA_BASE = "http://127.0.0.1:11434"
SUSHI_BASE = "http://127.0.0.1:12345"
NO_PROXY = ("no_proxy", "NO_PROXY")  # 仅记录，实际清代理靠 shell env


def load_prompts(vision=False):
    prompts = json.load(open(PROMPTS, encoding="utf-8"))
    if not vision:
        prompts = [p for p in prompts if p["id"] != "G1"]
    return prompts


def safe(name):
    return name.replace(":", "_").replace("/", "_")


# ---------- Ollama /api/chat ----------
def run_ollama(model, prompts, num_predict=4096, timeout=900):
    base = OLLAMA_BASE
    rows = []
    print(f"\n===== OLLAMA: {model} =====", flush=True)
    for p in prompts:
        out_path = os.path.join(OUT, safe(model), f"{p['id']}.txt")
        if os.path.exists(out_path):
            print(f"  [skip] {p['id']} (exists)", flush=True)
            continue
        print(f"  [run ] {p['id']} ({p['category']}) ...", flush=True)
        body = {
            "model": model,
            "messages": [{"role": "user", "content": p["prompt"]}],
            "stream": False,
            "options": {"temperature": 0, "num_predict": num_predict, "num_ctx": 131072},
        }
        req = urllib.request.Request(
            base + "/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.loads(resp.read().decode())
            content = out.get("message", {}).get("content", "")
            ec, ed = out.get("eval_count", 0), out.get("eval_duration", 0)
            pc, pd_ = out.get("prompt_eval_count", 0), out.get("prompt_eval_duration", 0)
            decode = round(ec / (ed / 1e9), 2) if ed else 0
            prefill = round(pc / (pd_ / 1e9), 2) if pd_ else 0
        except urllib.error.HTTPError as e:
            print(f"  [ERR ] {p['id']}: HTTP {e.code} {e.read().decode()[:200]}", flush=True)
            continue
        except Exception as e:
            print(f"  [ERR ] {p['id']}: {e}", flush=True)
            continue
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        open(out_path, "w", encoding="utf-8").write(content)
        print(f"         decode={decode} t/s, gen={ec}tok", flush=True)
        rows.append({"model": model, "id": p["id"], "category": p["category"],
                    "decode_tps": decode, "prefill_tps": prefill,
                    "gen_tokens": ec, "engine": "ollama"})
        time.sleep(0.5)
    return rows


# ---------- sushi /v1/chat/completions ----------
def _sushi_restart(model, wait=95):
    """清 KV：pkill 旧服务 → 等页回收 → 后台重启 → 等 warmup → 冒烟。返回 True/False。
    用 run_in_background 风格不可行（脚本是同步 python），这里用 nohup + setsid 持久化。"""
    import os, subprocess, time, urllib.request
    # macOS/Linux 通用：pkill 精确匹配二进制全路径，避免误杀自己命令行里含 "sushi serve" 的包装进程
    try:
        subprocess.run(["pkill", "-f", "/opt/homebrew/bin/sushi serve"], capture_output=True, timeout=15)
    except Exception:
        pass
    time.sleep(10)  # 等 inactive 页回收
    # 模型权重路径用 $HOME 展开（读者本机路径不同，设 SUSHI_MODEL_PATH 环境变量可覆盖）
    model_path = os.environ.get(
        "SUSHI_MODEL_PATH",
        os.path.expanduser("~/.sushi/models/beamster/Qwen3.8-Flash-Next-Sushi-2bpw"))
    logf = open("/tmp/sushi_bench.log", "wb")
    # start_new_session=True 让 sushi 脱离当前进程组（等价 setsid，但不依赖 setsid 二进制）
    subprocess.Popen(
        ["/opt/homebrew/bin/sushi", "serve",
         "--model", model_path, "--host", "127.0.0.1", "--port", "12345",
         "--skip-mem-preflight"],
        stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    print(f"    [kv-reset] 重启中，等 {wait}s warmup ...", flush=True)
    time.sleep(wait)
    # 冒烟测试
    try:
        req = urllib.request.Request(SUSHI_BASE + "/v1/models")
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception:
        return False


def run_sushi(model, prompts, max_tokens=4096, timeout=900, reset_kv=False):
    base = SUSHI_BASE
    rows = []
    print(f"\n===== SUSHI: {model} =====", flush=True)
    for i, p in enumerate(prompts):
        out_path = os.path.join(OUT, safe(model), f"{p['id']}.txt")
        if os.path.exists(out_path):
            print(f"  [skip] {p['id']} (exists)", flush=True)
            continue
        if reset_kv and i > 0:
            ok = _sushi_restart(model)
            if not ok:
                print(f"  [kv-reset-warn] 重启后冒烟失败，继续尝试（可能冷启动慢）", flush=True)
        print(f"  [run ] {p['id']} ({p['category']}) ...", flush=True)
        body = {
            "model": model,
            "messages": [{"role": "user", "content": p["prompt"]}],
            "max_tokens": max_tokens,
            "temperature": 0,
            "reasoning_effort": "low",
        }
        req = urllib.request.Request(
            base + "/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.loads(resp.read().decode())
            msg = out.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "") or ""
            t = out.get("timings", {})
            pred_n = t.get("predicted_n", 0)
            pred_ms = t.get("predicted_ms", 0)
            prompt_n = t.get("prompt_n", 0)
            prompt_ms = t.get("prompt_ms", 0)
            decode = round(pred_n / (pred_ms / 1000), 2) if pred_ms else 0
            prefill = round(prompt_n / (prompt_ms / 1000), 2) if prompt_ms else 0
        except urllib.error.HTTPError as e:
            print(f"  [ERR ] {p['id']}: HTTP {e.code} {e.read().decode()[:300]}", flush=True)
            continue
        except Exception as e:
            print(f"  [ERR ] {p['id']}: {e}", flush=True)
            continue
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        open(out_path, "w", encoding="utf-8").write(content)
        print(f"         decode={decode} t/s, gen={pred_n}tok", flush=True)
        rows.append({"model": model, "id": p["id"], "category": p["category"],
                    "decode_tps": decode, "prefill_tps": prefill,
                    "gen_tokens": pred_n, "engine": "sushi"})
        time.sleep(0.5)
    return rows


def merge_csv(rows):
    csv_path = os.path.join(OUT, "summary.csv")
    header = "model,id,category,decode_tps,prefill_tps,gen_tokens,engine\n"
    merged, seen = [], set()
    if os.path.exists(csv_path):
        for l in open(csv_path, encoding="utf-8").read().splitlines()[1:]:
            if not l.strip():
                continue
            parts = l.split(",")
            if len(parts) >= 2:
                seen.add((parts[0], parts[1]))
            merged.append(l)
    # 老格式没有 engine 列的旧行补一列（容错：行可能只有 6~7 列，统一补到 7 列）
    norm = []
    for l in merged:
        parts = l.split(",")
        if len(parts) < 7:
            # 不足 7 列的老行：model,id,cat,dec,pref,gen（6列）→ 补 engine
            parts = parts + [""] * (7 - len(parts))
        if len(parts) == 7 and parts[6].strip() == "":
            parts[6] = "ollama"
        norm.append(",".join(parts[:7]))
    merged = norm
    for r in rows:
        key = (r["model"], r["id"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(f"{r['model']},{r['id']},{r['category']},{r['decode_tps']},{r['prefill_tps']},{r['gen_tokens']},{r['engine']}")
    os.makedirs(OUT, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(header)
        for l in merged:
            f.write(l + "\n")
    print(f"\n[done] summary: {csv_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", nargs="*", default=[])
    ap.add_argument("--sushi", nargs="*", default=[])
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--vision", action="store_true")
    ap.add_argument("--num-predict", type=int, default=4096)
    ap.add_argument("--reset-kv", action="store_true",
                    help="sushi 每题前重启清 KV（防长生成堆满显存导致后续题 400）")
    args = ap.parse_args()

    prompts = load_prompts(vision=args.vision)
    if args.only:
        prompts = [p for p in prompts if p["id"] in args.only]
    os.makedirs(OUT, exist_ok=True)

    all_rows = []
    for m in args.ollama:
        all_rows += run_ollama(m, prompts, num_predict=args.num_predict)
    for m in args.sushi:
        all_rows += run_sushi(m, prompts, max_tokens=args.num_predict, reset_kv=args.reset_kv)
    merge_csv(all_rows)
    print(f"[done] 本次新增 {len(all_rows)} 条记录")


if __name__ == "__main__":
    main()
