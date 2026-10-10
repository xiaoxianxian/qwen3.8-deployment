#!/usr/bin/env bash
#
# verify.sh — Qwen3.8-Flash-Next（Sushi）健康检查
# 检查：服务在听 /v1/models、能正常出 token、工具调用透传
# 出任何问题都只打印诊断，不改动系统。
#
set -uo pipefail

PORT="${1:-12345}"
BASE="http://127.0.0.1:$PORT"
PASS=0; FAIL=0

check() { if [[ $1 -eq 0 ]]; then echo "  [OK]   $2"; PASS=$((PASS+1)); else echo "  [FAIL] $2"; FAIL=$((FAIL+1)); fi; }

echo "==> 健康检查：Sushi @ $BASE"

echo "-- 1. 模型列表"
if env -u http_proxy -u https_proxy curl -s --max-time 10 "$BASE/v1/models" \
   | grep -q "Qwen3.8-Flash-Next"; then
  check 0 "服务可达且暴露 Flash-Next 模型"
else
  check 1 "服务不可达或未暴露模型（确认 sushi serve 在跑、端口正确）"
fi

echo "-- 2. 基础对话（2+3）"
REPLY=$(env -u http_proxy -u https_proxy curl -s --max-time 30 "$BASE/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"beamster/Qwen3.8-Flash-Next-Sushi-2bpw","messages":[{"role":"user","content":"只回答数字：2+3=?"}],"max_tokens":32}' \
  || true)
if echo "$REPLY" | grep -q "5"; then
  check 0 "生成正常，返回含 5"
else
  check 1 "生成异常或超时（回复：${REPLY:0:120}）"
fi

echo "-- 3. 工具调用透传"
TOOL=$(env -u http_proxy -u https_proxy curl -s --max-time 30 "$BASE/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"beamster/Qwen3.8-Flash-Next-Sushi-2bpw","messages":[{"role":"user","content":"调用 get_weather 查北京天气"}],"tools":[{"type":"function","function":{"name":"get_weather","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],"max_tokens":64}' \
  || true)
if echo "$TOOL" | grep -qi "tool_calls\|get_weather"; then
  check 0 "工具调用透传正常"
else
  check 1 "工具调用未触发（回复：${TOOL:0:120}）"
fi

echo ""
echo "==> 结果：通过 $PASS，失败 $FAIL"
[[ $FAIL -eq 0 ]]
