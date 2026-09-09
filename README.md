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

## 实测性能（M5 Pro / 48GB）

### MLX 原生版（qwen3.8:27b-mlx，当前推荐）
- 生成速度：**~40 tok/s**（代码生成 40.8 / 开放式写作 29.0 / 列表结构化 34.2）
- 首 token 延迟：**3-4 秒**
- 内存占用：~18GB（nvfp4 量化）
- 自动开启 MTP 投机解码，接受率约 0.90

### GGUF 备选方案（Q5_K_M + draft_num_predict=3）
- 生成速度：~22 tok/s（代码类）
- 首次加载：~5s（常驻期间 ~0）
- 内存占用：~28GB（num_ctx=131072 时）
- 图片理解（1024px 单图 + 思考）：~17s

> MLX 原生版比 GGUF 方案快约 2 倍，且首 token 延迟更低。
> 见 `CURRENT_CONFIG.md` 和 `调优与避坑指南.md` 的详细说明。

## 分享给别人

- **从零部署**：发 `setup-guide.md`
- **已经装好、想调优**：发 `调优与避坑指南.md`（这次踩的坑都在里面）
- 两者都是独立完整的，不需要附带其他文件

### 分享前请替换

文档里的 `<你的用户名>` 是路径占位符，对方需替换为自己的实际路径。

## 资源

- 模型仓库：https://huggingface.co/unsloth/Qwen3.8-27B-GGUF
- Ollama 文档：https://ollama.com/docs
