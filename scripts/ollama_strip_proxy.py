#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama 智能代理（多模态 + 上下文截断）
-----------------------------------------
在 Ollama(默认 11434) 前做透明转发，解决两类本地模型调用问题：

  1) 上下文截断（防 WorkBuddy 长历史超时 / 400 context 超限）
     WorkBuddy 会把整段长对话历史发给本地 27B 模型，累计几万 token 在 Metal
     上预填充极慢，客户端易超时，或触发 "exceeds the available context"。
     本代理按 token 估算，超 --max-prompt-tokens 时只保留 system + 最近若干轮。

  2) 图片处理
     Qwen3.8-27B 已挂载 mmproj，原生支持看图，默认【放行图片】。
     可用 --strip-images 切回"剥图"模式（极端兜底，模型将看不到图）。

用法：
    python3 ollama_smart_proxy.py [--port 11435] [--upstream http://127.0.0.1:11434]
                                  [--max-prompt-tokens 24000] [--strip-images]
"""
import sys
import json
import argparse
import urllib.request
import urllib.error
import http.server
import socketserver

UPSTREAM = "http://127.0.0.1:11434"
PORT = 11435
MAX_PROMPT_TOKENS = 24000
STRIP_IMAGES = False


def _is_cjk(ch):
    o = ord(ch)
    return (0x2E80 <= o <= 0x9FFF) or (0xF900 <= o <= 0xFAFF) or (0xFF00 <= o <= 0xFFEF)


def estimate_tokens(messages):
    """CJK 感知的 token 估算：中文约 1.2 token/字，西文约 1 token/4 字符，
    每张图额外计约 800 视觉 token。无需加载 tokenizer，足够用于截断决策。"""
    cjk = 0
    other = 0
    images = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if isinstance(c, str):
            for ch in c:
                if _is_cjk(ch):
                    cjk += 1
                else:
                    other += 1
        elif isinstance(c, list):
            for part in c:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    for ch in part.get("text", ""):
                        if _is_cjk(ch):
                            cjk += 1
                        else:
                            other += 1
                elif part.get("type") in ("image_url", "image"):
                    images += 1
    return int(cjk * 1.2 + other / 4.0 + images * 800)


def strip_images(data):
    """从 chat 请求体剥离图片，仅保留文本。"""
    changed = False
    if isinstance(data, dict) and "images" in data:
        del data["images"]
        changed = True
    msgs = data.get("messages") if isinstance(data, dict) else None
    if isinstance(msgs, list):
        for m in msgs:
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            if isinstance(c, list):
                m["content"] = "\n".join(
                    p.get("text", "")
                    for p in c
                    if isinstance(p, dict) and p.get("type") == "text"
                )
                changed = True
    return data, changed


def truncate_messages(messages, max_tokens):
    """保留 system 消息 + 最近的若干条，使估算 token 不超过 max_tokens。"""
    system = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"]
    rest = [m for m in messages if not (isinstance(m, dict) and m.get("role") == "system")]
    kept = list(rest)
    while estimate_tokens(system + kept) > max_tokens and len(kept) > 1:
        kept.pop(0)
    out = system + kept
    # 避免首条非 system 是 assistant 导致模板异常
    if out and out[0].get("role") == "assistant":
        out = out[1:]
    return out


def transform_chat(body_bytes):
    """对 chat 请求体做图片处理 + 上下文截断，返回 (新body, 是否改动)。"""
    try:
        data = json.loads(body_bytes)
    except Exception:
        return body_bytes, False
    if not isinstance(data, dict):
        return body_bytes, False
    changed = False
    msgs = data.get("messages")
    if isinstance(msgs, list):
        before = estimate_tokens(msgs)
        if STRIP_IMAGES:
            data, sc = strip_images(data)
            changed = changed or sc
            if sc:
                msgs = data.get("messages")
        new_msgs = truncate_messages(msgs, MAX_PROMPT_TOKENS)
        after = estimate_tokens(new_msgs)
        if new_msgs != msgs:
            data["messages"] = new_msgs
            changed = True
            sys.stderr.write(
                "TRUNCATE: msgs %d->%d, est_tokens %d->%d (cap=%d)\n"
                % (len(msgs), len(new_msgs), before, after, MAX_PROMPT_TOKENS)
            )
            sys.stderr.flush()
    if changed:
        return json.dumps(data, ensure_ascii=False).encode("utf-8"), True
    return body_bytes, False


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ollama-smart-proxy/2.0"

    def log_message(self, fmt, *args):
        try:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))
        except Exception:
            pass

    def _forward(self, method):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""

        is_chat = self.path.endswith("/chat/completions") or self.path.endswith("/api/chat")
        if is_chat and method == "POST":
            body, _ = transform_chat(body)

        url = UPSTREAM + self.path
        req = urllib.request.Request(url, data=body if body else None, method=method)
        for k, v in self.headers.items():
            kl = k.lower()
            if kl in ("host", "content-length", "connection", "transfer-encoding"):
                continue
            req.add_header(k, v)
        req.add_header("Connection", "close")

        try:
            resp = urllib.request.urlopen(req, timeout=600)
            status = resp.getcode()
            self.send_response(status)
            for k, v in resp.getheaders():
                kl = k.lower()
                if kl in ("transfer-encoding", "content-length", "connection"):
                    continue
                self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            total = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
            self.wfile.flush()
        except urllib.error.HTTPError as e:
            payload = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:  # noqa
            import traceback as _tb
            sys.stderr.write("PROXY ERROR: %s\n%s\n" % (e, _tb.format_exc()))
            sys.stderr.flush()
            msg = json.dumps({"error": f"proxy error: {e}"}).encode("utf-8")
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Connection", "close")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            except Exception:
                pass

    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")


def main():
    global PORT, UPSTREAM, MAX_PROMPT_TOKENS, STRIP_IMAGES
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--upstream", default=UPSTREAM)
    p.add_argument("--max-prompt-tokens", type=int, default=MAX_PROMPT_TOKENS)
    p.add_argument("--strip-images", action="store_true")
    a = p.parse_args()
    PORT, UPSTREAM, MAX_PROMPT_TOKENS, STRIP_IMAGES = (
        a.port, a.upstream, a.max_prompt_tokens, a.strip_images,
    )

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(
            "ollama-smart-proxy on 127.0.0.1:%d -> %s (max_tokens=%d, strip_images=%s)"
            % (PORT, UPSTREAM, MAX_PROMPT_TOKENS, STRIP_IMAGES),
            flush=True,
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
