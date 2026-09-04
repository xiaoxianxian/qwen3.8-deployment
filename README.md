# 本地 Qwen3.8 部署指南

基于 M5 Pro / 48GB 实测的本地 LLM 部署完整指南。

## 快速开始

### 1. 环境检查

```bash
# 查看内存
sysctl hw.memsize | awk '{printf "内存: %.0f GB\n", $2/1024/1024/1024}'

# 检测代理
for port in 7890 7897 1087 1080; do
  curl -s -x http://127.0.0.1:$port -o /dev/null -w "%{http_code}" https://huggingface.co | grep -q 200 && echo "代理端口: $port" && break
done
```

### 2. 选择量化版本

| 内存 | 推荐版本 | 文件大小 |
|------|---------|---------|
| 16GB | Q3_K_XL / Q4_K_M | 12-16 GB |
| 24GB+ | **Q5_K_M** ⭐ | 18.41 GB |
| 36GB+ | Q6_K_XL | 23.56 GB |
| 48GB+ | Q8_K_XL | 29.30 GB |

### 3. 验证状态

```bash
./scripts/verify-ollama.sh
```

## 文档结构

```
├── README.md                    # 本文件（项目说明）
├── setup-guide.md               # 完整部署指南（从零开始看这个）
├── 调优与避坑指南.md            # ⭐ 装好之后的调优与踩坑（强烈推荐）
├── CURRENT_CONFIG.md            # 本机配置快照
├── Modelfile                    # 模型配置模板
├── docs/
│   ├── LOCAL_MODEL_SETUP_GUIDE.md  # 主文档（完整版）
│   ├── SKILL.md                 # Skill入口（简洁版）
│   └── references/
│       ├── guide.md             # 详细流程
│       └── api_reference.md     # API格式参考
└── scripts/
    ├── verify-ollama.sh         # 一键验证脚本
    └── ollama_strip_proxy.py   # 上下文截断代理
```

## 实测性能（M5 Pro / 48GB / Q5_K_M）

- 生成速度：~9.6 tokens/s
- 首次加载：~6s（开启 keep_alive 后驻留期间降至 ~0）
- 上下文：**262144 tokens**（原生上限，已拉满）
- 图片理解（1024px 单图）：~15–23 秒

> ⚠️ 262144 需配合 `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0`，见调优指南。

## 分享给别人

- **从零部署**：发 `setup-guide.md`
- **已经装好、想调优**：发 `调优与避坑指南.md`（这次踩的坑都在里面）
- 两者都是独立完整的，不需要附带其他文件

### 分享前请替换

文档里的 `<你的用户名>` 是路径占位符，对方需替换为自己的实际路径。

## 资源

- 模型仓库：https://huggingface.co/unsloth/Qwen3.8-27B-GGUF
- Ollama 文档：https://ollama.com/docs
