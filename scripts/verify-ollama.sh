#!/bin/bash
echo "=== Ollama 状态检查 ==="
echo ""

# 检查 Ollama 服务
if ! curl -s http://localhost:11434/api/version > /dev/null 2>&1; then
  echo "❌ Ollama 未运行，请先启动 Ollama.app"
  exit 1
fi
echo "✅ Ollama 服务正常"

# 列出模型
echo ""
echo "=== 已安装模型 ==="
ollama list

# 检查 API 连通性
echo ""
echo "=== API 连通性测试 ==="
response=$(curl -s -w "\n%{http_code}" http://localhost:11434/v1/models)
http_code=$(echo "$response" | tail -1)
if [ "$http_code" = "200" ]; then
  echo "✅ API 端点正常: http://localhost:11434/v1"
else
  echo "❌ API 端点异常 (HTTP $http_code)"
fi

# 测试简单推理
echo ""
echo "=== 推理测试 ==="
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-local","messages":[{"role":"user","content":"用一句话介绍自己"}],"stream":false}' \
  | python3 -c "import sys,json; print('✅ 推理正常:', json.load(sys.stdin)['choices'][0]['message']['content'][:50])" 2>/dev/null || echo "⚠️ 推理测试失败，请检查模型名"

echo ""
echo "=== 完成 ==="
