#!/usr/bin/env python3
"""Same-prompt throughput bench across Ollama and an OpenAI-compatible local server.

Usage:
  python3 local_llm_bench.py --kind ollama   --base http://127.0.0.1:11434 --model qwen3.8:27b-mlx
  python3 local_llm_bench.py --kind openai   --base http://127.0.0.1:PORT   --model mtplx-model --api-key k
"""
import argparse
import json
import statistics
import time
import urllib.error
import urllib.request

CODE_PROMPT = (
    "Read this Python snippet and list exactly 5 concrete issues, numbered 1 to 5, "
    "each in at most one sentence.\n\n"
    "import json\n\n"
    "def handle(u, payload):\n"
    "    data = json.loads(payload)\n"
    "    rows = []\n"
    "    for k in data:\n"
    "        r = db.query(u, k)\n"
    "        rows.append(r)\n"
    "    return rows\n"
)

LONG_PROMPT = (
    "请用中文写一段不少于 900 字的长文，主题是「在本地 Mac 上跑大模型时，团队最容易踩的五个坑」。"
    "要求：每个坑单起一段，给出现象、原因、可行的规避办法；不要空话，尽量给可操作的判断标准。"
)

PROMPT = CODE_PROMPT
PROMPT_NAME = "code"


def post_json(url, payload, timeout=1800):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def one_run(kind, base, model, max_tokens, api_key, reasoning):
    url = base.rstrip("/") + ("/api/chat" if kind == "ollama" else "/v1/chat/completions")
    msgs = [{"role": "user", "content": PROMPT}]
    if kind == "ollama":
        opts = {"num_ctx": 131072, "num_predict": max_tokens, "temperature": 0.7}
        if reasoning:
            opts["reasoning_effort"] = reasoning
        body = {"model": model, "messages": msgs, "stream": True,
                "options": opts, "think": False}
    else:
        body = {
            "model": model, "messages": msgs, "stream": True,
            "max_tokens": max_tokens, "temperature": 0.7,
            "stream_options": {"include_usage": True},
        }
        if reasoning:
            body["reasoning_effort"] = reasoning
        else:
            body["thinking"] = {"type": "disabled"}

    t0 = time.perf_counter()
    ttft = None
    out_tokens = 0
    text_len = 0
    saw_usage = False
    mtplx_last_progress = None
    with post_json(url, body) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            d = json.loads(line)
            if kind == "ollama":
                msg = d.get("message") or {}
                txt = msg.get("content") or msg.get("reasoning") or ""
                if ttft is None and txt:
                    ttft = time.perf_counter()
                text_len += len(txt)
                if d.get("done"):
                    out_tokens = d.get("eval_count") or 0
                    ev = (d.get("eval_duration") or 0) / 1e9
                    pe = (d.get("prompt_eval_duration") or 0) / 1e9
            else:
                delta = (d.get("choices") or [{}])[0].get("delta") or {}
                seg = delta.get("content") or delta.get("reasoning_content") or ""
                if ttft is None and seg:
                    ttft = time.perf_counter()
                text_len += len(seg)
                if d.get("mtplx_progress"):
                    mtplx_last_progress = d["mtplx_progress"]
                if d.get("usage"):
                    saw_usage = True
                    out_tokens = d.get("usage", {}).get("completion_tokens") or 0
    t_end = time.perf_counter()

    ttft = ttft or t_end
    total_s = t_end - t0
    decode_s = max(t_end - ttft, 1e-6)
    if not saw_usage:
        # 服务端没回 usage，用文本长度粗估（Qwen 中文约 1.5~1.7 字符/token）
        out_tokens = round(text_len / 1.6)
    return {
        "out_tokens": out_tokens,
        "text_chars": text_len,
        "mtplx_tok_s": (mtplx_last_progress or {}).get("decode_tok_s"),
        "mtplx_peak_gb": round(
            (mtplx_last_progress or {}).get("peak_memory_bytes", 0) / 1e9, 2),
        "mtplx_accept": (mtplx_last_progress or {}).get("accepted_by_depth"),
        "total_s": round(total_s, 3),
        "ttft_s": round(ttft - t0, 3),
        "e2e_tok_s": round(out_tokens / total_s, 2) if out_tokens else 0,
        "decode_tok_s": round(out_tokens / decode_s, 2) if out_tokens else 0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kind", choices=["ollama", "openai"], required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--reasoning", default="")
    p.add_argument("--api-key", default="")
    p.add_argument("--prompt", choices=["code", "long"], default="code")
    a = p.parse_args()

    global PROMPT, PROMPT_NAME
    PROMPT, PROMPT_NAME = (CODE_PROMPT, "code") if a.prompt == "code" else (LONG_PROMPT, "long")
    print(f"# prompt={PROMPT_NAME}")

    runs = []
    for i in range(a.rounds):
        try:
            r = one_run(a.kind, a.base, a.model, a.max_tokens, a.api_key, a.reasoning)
        except urllib.error.HTTPError as e:
            print("HTTP", e.code, e.read().decode()[:400])
            return
        runs.append(r)
        extra = ""
        if r.get("mtplx_tok_s"):
            extra = (f" MT=self {r['mtplx_tok_s']} tok/s peak={r.get('mtplx_peak_gb')}GB "
                     f"accept={r.get('mtplx_accept')}")
        print(f"run{i+1}: out={r['out_tokens']} tok, ttft={r['ttft_s']}s, "
              f"decode={r['decode_tok_s']} tok/s, e2e={r['e2e_tok_s']} tok/s "
              f"total={r['total_s']}s chars={r['text_chars']}{extra}")

    med = lambda k: round(statistics.median([r[k] for r in runs]), 2)
    print(f"MEDIAN out={med('out_tokens')} ttft={med('ttft_s')}s "
          f"decode={med('decode_tok_s')} tok/s e2e={med('e2e_tok_s')} tok/s")


if __name__ == "__main__":
    main()
