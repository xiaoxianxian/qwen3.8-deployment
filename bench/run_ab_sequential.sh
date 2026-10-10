#!/bin/bash
# 12 题 A/B 串行执行：Flash-Next(sushi 12345) → 27B(ollama 11434)
# 前置：本脚本假定你已跑完（或正在跑）Flash-Next 那一段，这里负责切换 + 跑 27B。
# 用法：
#   1) 确认 sushi 的 12 题已跑完（ab_results/beamster_Qwen3.8-Flash-Next-Sushi-2bpw/ 有 12 个 txt）
#   2) bash run_ab_sequential.sh
# 内存原则：Flash-Next(~37G) 与 27B(~18G) 不能同驻，先 kill sushi 再加载 27B。

set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
NOX="env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY"

echo "===== 1. kill sushi serve（释放 ~37G，给 27B 腾内存）====="
pkill -f "sushi serve" 2>/dev/null || echo "(无 sushi 进程)"
sleep 8
# 等 inactive 页回收
sleep 10
$NOX lsof -nP -iTCP:12345 -sTCP:LISTEN 2>/dev/null | head -1 || echo "✅ 12345 已释放"

echo
echo "===== 2. 确认 Ollama 存活（daemon 在才需 27B 加载）====="
$NOX curl -s http://127.0.0.1:11434/api/ps 2>/dev/null >/dev/null && echo "✅ Ollama 在 11434" || echo "❌ Ollama 没起，先 launchctl bootstrap com.ollama.serve"

echo
echo "===== 3. 跑 27B 12 题（首次加载 ~23s 冷启动）====="
cd "$HERE"
$NOX python3 ab_run_unified.py --ollama "qwen3.8:27b-mlx" 2>&1

echo
echo "===== 4. 跑完 27B 后立刻卸载（防残留占内存）====="
$NOX curl -s -X POST http://127.0.0.1:11434/api -H 'Content-Type: application/json' \
  -d '{"action":"stop","model":"qwen3.8:27b-mlx","keep_alive":0}' 2>/dev/null || \
  $NOX curl -s -X POST http://127.0.0.1:11434/api/unload \
  -d '{"keep_alive":0}' 2>/dev/null || echo "(stop 端点未确认，手动 ollama stop qwen3.8:27b-mlx)"

echo
echo "===== 5. 生成对照报告 ====="
cd "$HERE"
python3 make_report.py 2>&1 | tail -20
echo
echo "===== 质量判分（JSON/数学/知识）====="
python3 validate.py 2>&1 | head -40
echo
echo "✅ 完成。结果目录: $HERE/ab_results/  报告: $HERE/A_B实测对比报告.md"
