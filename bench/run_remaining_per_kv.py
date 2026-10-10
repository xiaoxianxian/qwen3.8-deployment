#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑 Flash-Next 剩余 7 题（B2 C1 D1 E1 E2 F1 F2），每题前重启寿司清 KV。
根因：48GB 上连发多道 1000+ token 生成 → KV 堆满 → 后续 prefill 报 400。
解法：每题跑前 pkill 寿司 + 重新拉起（start_new_session 脱离进程组，python 退出让寿司存活）+ 冒烟 + 再发。
macOS 无 setsid 二进制，改用 Popen(start_new_session=True)。"""
import json, os, time, subprocess, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ab_results")
MODEL = "beamster/Qwen3.8-Flash-Next-Sushi-2bpw"
SUSHI_BIN = "/opt/homebrew/bin/sushi"
# 模型权重路径用 $HOME 展开（读者本机路径不同，设 SUSHI_MODEL_PATH 环境变量可覆盖）
MODEL_PATH = os.environ.get(
    "SUSHI_MODEL_PATH",
    os.path.expanduser("~/.sushi/models/beamster/Qwen3.8-Flash-Next-Sushi-2bpw"))
PROMPTS = json.load(open(os.path.join(HERE, "ab_prompts.json"), encoding="utf-8"))
IDS = ["B2", "C1", "D1", "E1", "E2", "F1", "F2"]
PROMPT_MAP = {p["id"]: p for p in PROMPTS}


def restart_sushi(warm_wait=100):
    """pkill 旧寿司 → 等页回收 → Popen 拉起 → 冒烟。返回 bool。"""
    try:
        subprocess.run(["pkill", "-9", "-f", "/opt/homebrew/bin/sushi serve"],
                       capture_output=True, timeout=20)
    except Exception:
        pass
    time.sleep(12)  # 等 inactive 页回收 + 寿司释放
    logf = open("/tmp/sushi_remaining.log", "wb")
    p = subprocess.Popen(
        [SUSHI_BIN, "serve", "--model", MODEL_PATH,
         "--host", "127.0.0.1", "--port", "12345", "--skip-mem-preflight"],
        stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    # 等 warmup + 冒烟
    for i in range(24):  # 最多 24*8s=192s
        time.sleep(8)
        try:
            r = urllib.request.urlopen("http://127.0.0.1:12345/v1/models", timeout=8)
            if r.status == 200:
                print(f"    [kv-reset] 寿司活了（重启耗时 ~{(i+1)*8}s, pid={p.pid})", flush=True)
                return True
        except Exception:
            continue
    print(f"    [kv-reset-warn] 寿司 192s 未冒烟成功，继续尝试（可能慢）", flush=True)
    return False


def fire(vid):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT_MAP[vid]["prompt"]}],
        "max_tokens": 1024, "temperature": 0, "reasoning_effort": "low",
    }
    req = urllib.request.Request(
        "http://127.0.0.1:12345/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        out = json.loads(resp.read().decode())
    msg = out.get("choices", [{}])[0].get("message", {})
    t = out.get("timings", {})
    content = msg.get("content", "") or ""
    decode = round(t.get("predicted_n", 0) / (t.get("predicted_ms", 0) / 1000), 2) if t.get("predicted_ms") else 0
    return content, decode, t.get("predicted_n", 0)


def main():
    rows = []
    for i, vid in enumerate(IDS):
        print(f"\n[{i+1}/{len(IDS)}] {vid} ({PROMPT_MAP[vid]['category']})", flush=True)
        if i > 0:
            restart_sushi()  # 每题清 KV
        try:
            content, decode, gen = fire(vid)
        except urllib.error.HTTPError as e:
            print(f"  [ERR] HTTP {e.code}: {e.read().decode()[:160]}", flush=True)
            continue
        except Exception as e:
            print(f"  [ERR] {e}", flush=True)
            continue
        out_path = os.path.join(OUT, MODEL.replace("/", "_"), f"{vid}.txt")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        open(out_path, "w", encoding="utf-8").write(content)
        print(f"  decode={decode} t/s, gen={gen}tok", flush=True)
        rows.append(f"{MODEL},{vid},{PROMPT_MAP[vid]['category']},{decode},0,{gen},sushi")
        time.sleep(1)
    # 合并 summary.csv（容错：旧行格式不定，只追加新行）
    csv = os.path.join(OUT, "summary.csv")
    os.makedirs(OUT, exist_ok=True)
    with open(csv, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(r + "\n")
    print(f"\n[done] 追加 {len(rows)}/{len(IDS)} 题到 {csv}")
    # 最后清掉寿司，给 27B 腾内存
    subprocess.run(["pkill", "-9", "-f", "/opt/homebrew/bin/sushi serve"], capture_output=True)
    print("[done] 寿司已停，内存已释放给 27B")


if __name__ == "__main__":
    main()
