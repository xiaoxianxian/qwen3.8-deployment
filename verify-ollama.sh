#!/bin/bash
# Qwen3.8-27B 本地部署验证脚本
# 使用方法：bash verify-ollama.sh

set -e

echo "========================================"
echo "  Qwen3.8-27B 本地部署验证"
echo "========================================"
echo ""

# 检查 Ollama 是否安装
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama 未安装，请先执行：brew install ollama"
    exit 1
fi
echo "✅ Ollama 已安装: $(ollama --version)"
echo ""

# 检查 Ollama 服务是否运行
if ! curl -s http://localhost:11434/api/version &> /dev/null; then
    echo "❌ Ollama 服务未运行，请执行：ollama serve"
    exit 1
fi
echo "✅ Ollama 服务运行中"
echo ""

# 列出已安装的模型
echo "📋 已安装的模型："
ollama list
echo ""

# 检查目标模型是否存在
MODEL_NAME="qwen3.8:27b-mlx"
if ! ollama list | grep -q "$MODEL_NAME"; then
    echo "⚠️  模型 $MODEL_NAME 未找到"
    echo ""
    echo "🔧 请手动创建模型："
    echo "   1. 下载模型文件到 ~/models/"
    echo "   2. 编辑 ~/models/Modelfile，修改路径"
    echo "   3. 执行：ollama create qwen3.8:27b-mlx -f ~/models/Modelfile"
    exit 1
fi
echo "✅ 模型 $MODEL_NAME 已安装"
echo ""

# 测试简单对话
echo "🧪 测试模型响应（3秒超时）..."
RESPONSE=$(timeout 30 ollama run "$MODEL_NAME" "你好，请回复'部署成功'" 2>&1)
if echo "$RESPONSE" | grep -q "部署成功\|成功\|hello\|Hello"; then
    echo "✅ 模型响应正常"
else
    echo "⚠️  模型响应异常: $RESPONSE"
fi
echo ""

# 检查模型信息
echo "📊 模型详细信息："
curl -s http://localhost:11434/api/show -d "{\"name\":\"$MODEL_NAME\"}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    details = data.get('details', {})
    print(f\"  量化: {details.get('quantization_level', 'N/A')}\")
    print(f\"  上下文: {details.get('context_length', 'N/A')} tokens\")
    caps = data.get('capabilities', [])
    print(f\"  能力: {', '.join(caps) if caps else 'N/A'}\")
except:
    print('  (无法解析模型详情)')
" 2>/dev/null || echo "  (无法获取模型详情)"
echo ""

echo "========================================"
echo "  ✅ 验证完成！"
echo "========================================"
echo ""
echo "下一步：在 Hermes Agent 中使用"
echo "  1. 编辑 ~/.hermes/config.yaml"
echo "  2. 在 providers 下添加："
echo "     ollama:"
echo "       name: Ollama (Local)"
echo "       base_url: http://localhost:11434/v1"
echo "       model: qwen3.8:27b-mlx"
echo "       discover_models: true"
echo "  3. 在 Hermes 中输入：/model ollama/qwen3.8:27b-mlx"
echo ""
