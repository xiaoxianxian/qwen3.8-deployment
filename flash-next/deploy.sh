#!/usr/bin/env bash
#
# deploy.sh — Qwen3.8-Flash-Next（Sushi 2bpw）一键本地部署
# 适用：macOS / Apple Silicon / ≥48GB 内存
# 做了什么：装引擎 → 拉权重（带自愈循环）→ 起服务 → 自检
# 不做：不改系统配置、不推送任何远端、不删除个人文件
#
set -euo pipefail

MODEL_REPO="beamster/Qwen3.8-Flash-Next-Sushi-2bpw"
MODEL_TAG="qwen3.8-flash-next:2bpw"
MODEL_DIR="$HOME/.sushi/models/$MODEL_REPO"
EXPECT_FILES=212
EXPECT_MB=64000
PORT=12345
LOG="/tmp/sushi-deploy.log"

echo "==> [1/4] 环境检查"
if [[ "$(uname)" != "Darwin" ]]; then
  echo "错误：仅支持 macOS（Apple Silicon）。" >&2; exit 1
fi
if ! uname -a | grep -qi "arm64"; then
  echo "错误：需要 Apple Silicon（M 系列芯片）。" >&2; exit 1
fi
mem_gb=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
if (( mem_gb < 48 )); then
  echo "警告：检测到 ${mem_gb}GB 内存，低于 2bpw 全驻留建议的 48GB。32GB 只能专家流式，不推荐继续。" >&2
fi

echo "==> [2/4] 安装 Sushi 引擎"
if command -v sushi >/dev/null 2>&1; then
  echo "    sushi 已在 PATH：${sushi:-$(command -v sushi)}"
else
  echo "    尝试 brew 安装……"
  if brew install beamivalice/tap/sushi 2>/dev/null; then
    echo "    brew 安装成功"
  else
    echo "    brew 安装失败（常见于沙箱拦截写 Homebrew 信任标记）。" >&2
    echo "    请手动从 https://github.com/beamivalice/sushi 的 Releases 下载" >&2
    echo "    sushi-bin-macos-arm64.tar.gz，解压后将内部 sushi 二进制软链到" >&2
    echo "    /opt/homebrew/bin/sushi，再重新运行本脚本。" >&2
    exit 1
  fi
fi
sushi --version

echo "==> [3/4] 下载权重（自愈循环：不足 212 文件 / 64GB 就续传）"
mkdir -p "$MODEL_DIR"
for i in $(seq 1 60); do
  n=$(find "$MODEL_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
  mb=$(du -sm "$MODEL_DIR" 2>/dev/null | cut -f1 || echo 0)
  if (( n >= EXPECT_FILES )) && (( ${mb:-0} >= EXPECT_MB )); then
    echo "    权重完整：${n} 文件 / ${mb}MB"
    break
  fi
  echo "    第 $i 次续传（当前 ${n} 文件 / ${mb}MB，目标 ≥${EXPECT_FILES} / ≥${EXPECT_MB}MB）"
  sushi pull "$MODEL_TAG" || true   # 网络抖动时退出码可能异常，循环兜底
  sleep 3
done

echo "==> [4/4] 启动服务（后台，--skip-mem-preflight）"
pkill -f "/opt/homebrew/bin/sushi serve" 2>/dev/null || true
sleep 2
nohup sushi serve \
  --model "$MODEL_DIR" \
  --host 127.0.0.1 --port "$PORT" \
  --skip-mem-preflight \
  > "$LOG" 2>&1 &
echo $! > /tmp/sushi.pid
echo "    服务 PID $(cat /tmp/sushi.pid)，日志 $LOG"

echo "==> 等待服务就绪……"
for i in $(seq 1 40); do
  if env -u http_proxy -u https_proxy curl -s "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
    echo "    服务已就绪：http://127.0.0.1:$PORT/v1"
    echo "==> 部署完成。运行 bash verify.sh 做健康检查，或把 Agent 工具的 Base URL 指向该地址。"
    exit 0
  fi
  sleep 3
done
echo "    服务未在 120 秒内就绪，请看 $LOG" >&2
exit 1
