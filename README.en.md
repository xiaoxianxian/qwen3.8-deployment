---
permalink: /en/
title: English Guide
---

# Run Qwen3.8-27B Locally on Mac (Apple Silicon / Ollama)

A practical local-LLM deployment guide for macOS Apple Silicon users, based on real-world testing on an M5 Pro / 48GB. Covers the Ollama + MLX vs GGUF quantization comparison, MTP speculative-decoding acceleration, China-region mirror downloads, and a full troubleshooting playbook.

> **Last verified: 2026-09-15** · Ollama 0.33.3 · macOS 26 (M5 Pro / 48GB)
> Supported: **Ollama ≥ 0.30**. Earlier versions have an MLX large-context timeout bug (see [Issue 2](./TROUBLESHOOTING.md#2-mlx-超时-500-context-canceled)); check your version before starting.

## Who this is for

- macOS with Apple Silicon (M1/M2/M3/M4/M5)
- RAM ≥ 16GB (24GB runs; 32GB+ is smooth; 48GB is the fully-tested environment in this guide)
- Already have a Python environment

## Who this is NOT for

- **Non-Apple Silicon** (Intel Mac / Windows / Linux): the MLX path and all benchmark numbers here don't apply. Use the model API or cloud GPU instead.
- **RAM < 16GB**: a 27B model won't fit. Use a smaller model or the API.
- **Production multi-user concurrency**: Ollama is single-machine / personal-use. For high concurrency use vLLM or similar (not covered here).

## Choosing a quantization

### Quick decision table

| Your RAM | Recommended | File size | Speed* | Quality |
|----------|-------------|-----------|--------|---------|
| 16GB | GGUF Q3_K_XL (emergency) | ~12 GB | slower | medium |
| 16–24GB | GSQ-RCO IQ3_S (VRAM-saving balance) | ~12 GB | ~12.6 tok/s | near-lossless |
| 24GB | GGUF Q4_K_M / Q5_K_M | 15–18 GB | ~22–30 tok/s | med-high |
| **32GB+** | **MLX native** (recommended) | ~18 GB | **~40 tok/s** | high |
| 48GB+ | Q8_K_XL (max quality) or MLX | ~29 GB | ~25 tok/s | very high |

> \* All speeds are **measured on M5 Pro / 48GB**. Memory bandwidth differs across chip generations — don't extrapolate directly. On 24GB, running MLX leaves almost no headroom for weights + KV cache; you must lower `num_ctx` or it will swap — **32GB is the floor for the experience above; 48GB is the fully-tested environment**.

### Four-model performance summary (M5 Pro 48GB, num_ctx=131072)

| Model | Quant | Size | Short benchmark · codegen¹ | Strict 12-q · avg decode² | 12-q quality | RAM |
|-------|-------|------|----------------------------|---------------------------|--------------|-----|
| **MLX 4-bit** | NVFP4 | 18 GB | 40.8 tok/s | **29.9 tok/s** | 12/12 | ~21 GB |
| **Q5_K_M** | GGUF 5.6bpw | 20 GB | 22.4 tok/s | 14.9 tok/s | 12/12 | ~20 GB |
| **GSQ IQ3_S** | 3.5bpw mixed | 12 GB | 16.2 tok/s | 12.6 tok/s | 12/12 | ~12 GB |
| **GSQ IQ3_XXS** | 3.0bpw mixed | 10 GB | — | 12.5 tok/s | 12/12 | ~10 GB |

¹ Early short benchmark: short context, non-uniform temperature, no MTP stacking, single-task peak (MLX early split: writing 29.0 / structured 34.2 tok/s).
² Strict 12-question A/B: temperature=0, 12 unified questions, MTP on for all four, serial run-then-unload. The two methods differ in methodology, so ratios aren't directly divisible — use as order-of-magnitude only.

> **MLX native (`qwen3.8:27b-mlx`)** is the best choice: ~2× faster, sub-second first token. MTP speculative decoding must be enabled manually (`draft_num_predict 3`); it's shared by both GGUF and MLX, not MLX-exclusive.
> For maximum quality with enough RAM, choose **Q8_K_XL** (8-bit, near-lossless).

Full comparison: [性能对比与量化指南.md (Quantization Guide, Chinese)](./性能对比与量化指南.md)

## Quick start

### Step 1: Check your environment

```bash
# Check RAM
sysctl hw.memsize | awk '{printf "RAM: %.0f GB\n", $2/1024/1024/1024}'

# Detect proxy
for port in 7890 7897 1087 1080; do
  curl -s -x http://127.0.0.1:$port -o /dev/null -w "%{http_code}" https://huggingface.co | grep -q 200 && echo "Proxy port: $port" && break
done
```

### Step 2: Pick a quantization

| RAM | Recommended | Size | Gen speed (M5 Pro measured) |
|-----|-------------|------|------------------------------|
| 16GB | Q3_K_XL / Q4_K_M | 12–16 GB | not measured (below Q5) |
| **24GB+** | **MLX nvfp4 (MLX native)** (recommended) | 18 GB | ~29.9 tok/s (12-q A/B) / ~40 tok/s (short) |
| 24GB+ | **Q5_K_M** | 18–20 GB | ~14.9 tok/s (12-q A/B) |
| 24GB+ | GSQ IQ3_S | 12 GB | ~12.6 tok/s |
| 24GB+ | GSQ IQ3_XXS | 10 GB | ~12.5 tok/s |
| 36GB+ | Q6_K_XL | 23.56 GB | not measured |
| 48GB+ | Q8_K_XL | 29.30 GB | not measured |

> Speed figures use the 2026-09-15 same-condition A/B (`temperature=0`, 12 questions). MLX nvfp4 peaks ~40 tok/s on short context. IQ series are ISTA-DASLab **GSQ-RCO** mixed-precision quants — VRAM-saving, near-lossless quality (IQ3_XXS has a ~1-point marginal drop on large knowledge benchmarks). Both MLX nvfp4 and GGUF Q5_K_M need `draft_num_predict 3` in the Modelfile to reach the speeds above.

### Step 3: Install Ollama

```bash
# Option A: Homebrew (recommended)
brew install ollama

# Option B: direct download
# https://ollama.com/download
```

### Step 4: Pull the model

```bash
# Option 1 (recommended): MLX native — fast, vision built-in
export HF_ENDPOINT=https://hf-mirror.com   # China mirror, optional
ollama pull qwen3.8:27b-mlx

# Option 2 (concurrency / long-agent fallback): GGUF Q5_K_M, more stable under llama.cpp concurrency
# ollama pull unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q5_K_M
```

**nvfp4**: a 4-bit floating-point quantization format that compresses 27B weights from 50+ GB down to ~18 GB with restrained precision loss — the basis for the MLX build being small and fast.

**If the network is slow or HuggingFace is unreachable, use a China mirror:**

```bash
# Mirror A: hf-mirror.com
export HF_ENDPOINT=https://hf-mirror.com
ollama pull qwen3.8:27b-mlx

# Mirror B: ModelScope
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3.8-27B', cache_dir='./models')"
# then create a local model with the in-repo Modelfile (see Step 5)
```

**Lower VRAM (≥16GB): GSQ-RCO IQ3_S / IQ3_XXS**

```bash
pip install -U "huggingface_hub[cli]"
hf download ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF \
  Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf mmproj-Qwen3.8-27B-BF16.gguf --local-dir .
# create with the Step 5 Modelfile (replace FROM with the local .gguf path)
```

GSQ-RCO is ISTA-DASLab's learned mixed-precision quantization: IQ3_S compresses 27B to ~12GB with near-lossless quality (GPQA only 0.5pt off), smaller and more stable than Q4_K_M; IQ3_XXS (~10GB) saves more but carries a ~1pt marginal risk on knowledge questions. MLX native is ~2.4× the speed of GSQ mixed precision; when you also run video models like MiniMax H3 on the same machine and VRAM is tight, GSQ IQ3_S is the VRAM-saving default.

### Step 5: Create the local model

The MLX native build is usable right after `ollama pull`. The GGUF (Q5 / GSQ IQ3) path needs an explicit Modelfile that attaches the **multimodal template** and **MTP speculative decoding** — otherwise image input errors out and you waste the model's built-in acceleration.

**MLX native (FROM official tag):**

```dockerfile
FROM qwen3.8:27b-mlx
PARAMETER num_ctx 131072
PARAMETER draft_num_predict 3     # MTP speculative decoding (Qwen3.8 built-in acceleration)
PARAMETER temperature 0.7
PARAMETER top_p 0.95
PARAMETER top_k 20
```

**GGUF Q5_K_M (FROM Ollama tag; needs multimodal template + MTP + vision projector):**

```dockerfile
FROM unsloth/Qwen3.8-27B-GGUF:Qwen3.8-27B-UD-Q5_K_M
FROM ./mmproj-F16.gguf            # vision projector (required for multimodal; download separately)
TEMPLATE """{{- if .System }}<|system|>
{{ .System }}
<|end|>
{{ end }}
{{- range .Messages }}
{{- if eq .Role "user" }}<|user|>
{{ .Content }}
<|end|>
{{ else if eq .Role "assistant" }}<|assistant|>
{{ if .Content }}{{ .Content }}{{ end }}{{ if .ReasoningContent }}<|reserved_special_token_145|>{{ .ReasoningContent }}<|end|>
{{ end }}
<|end|>
{{ end }}
{{- end }}
<|assistant|>
{{ if .ReasoningContent }}<|reserved_special_token_145|>{{ .ReasoningContent }}<|end|>
{{ end }}{{ .Response }}"""
PARAMETER num_ctx 131072
PARAMETER draft_num_predict 3
```

**GSQ-RCO IQ3_S / IQ3_XXS (FROM local GGUF; same structure, just swap FROM and mmproj):**

```dockerfile
FROM ./Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf   # for IQ3_XXS use the -IQ3_XXS- file
FROM ./mmproj-Qwen3.8-27B-BF16.gguf
TEMPLATE """(identical multimodal template as GGUF Q5 above)"""
PARAMETER num_ctx 131072
PARAMETER draft_num_predict 3
```

```bash
# GGUF / GSQ path: create the model
ollama create qwen3.8-q5 -f Modelfile.q5
ollama create qwen3.8-gsq-iq3s -f Modelfile.gsq
```

### Step 6: Configure global environment variables

```bash
# macOS user-level global config (Ollama runs as a user LaunchAgent, no sudo needed)
launchctl setenv OLLAMA_CONTEXT_LENGTH 131072
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_KEEP_ALIVE 30m

# Apply: restart Ollama so env vars take effect
pkill -f "ollama serve" && sleep 2 && open -a Ollama
```

**What each variable does:**

| Variable | Effect | If unset |
|----------|--------|----------|
| `OLLAMA_CONTEXT_LENGTH=131072` | global default 128K context | model falls back to 4096; long docs silently truncated |
| `OLLAMA_FLASH_ATTENTION=1` | +30–50% long-context speed | slower |
| `OLLAMA_KV_CACHE_TYPE=q8_0` | quantize KV cache, halve RAM | high RAM, may swap |
| `OLLAMA_KEEP_ALIVE=30m` | keep model in RAM 30 min | ~6s cold start per call |

> `launchctl setenv` is lost after a Mac reboot — re-run it. For a permanent fix, write the vars into Ollama's LaunchAgent plist.

### Step 7: Verify the install

```bash
# Show model info
ollama show qwen3.8:27b-mlx

# Confirm context length took effect (should print 131072, not 4096)
ollama show qwen3.8:27b-mlx | grep num_ctx

# Test a chat
ollama run qwen3.8:27b-mlx "Hi, introduce yourself in one sentence"
```

You can also run the in-repo verification script to do all the above at once:

```bash
./verify-ollama.sh
```

**Test image understanding (MLX has vision built-in; GGUF / GSQ need mmproj attached in the Modelfile):**

```bash
ollama run qwen3.8:27b-mlx "Describe this image" --images image.jpg
```

### Step 8: Use the model

```bash
# Chat
ollama run qwen3.8:27b-mlx "Hi, introduce yourself in one sentence"

# Code generation
ollama run qwen3.8:27b-mlx "Write a Python quicksort"

# Image understanding (MLX has vision built-in; GGUF/GSQ need mmproj attached)
ollama run qwen3.8:27b-mlx "Describe this image" --images image.jpg
```

## API usage

Ollama exposes an OpenAI-compatible API:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

response = client.chat.completions.create(
    model="qwen3.8:27b-mlx",  # swap for qwen3.8-q5 / qwen3.8-gsq-iq3s etc.
    messages=[{"role": "user", "content": "Hi"}],
    temperature=0.7,
    max_tokens=2000
)

print(response.choices[0].message.content)
```

## Benchmark notes

Full speed / size / quality comparison is in the "Four-model performance summary" above. Raw data, per-question validation, and hardware comparison for the strict 12-question A/B are in [A_B实测对比报告.md (A/B Report, Chinese)](./A_B实测对比报告.md).

- MTP acceptance rate: ~0.6–0.85 (measured from runner logs)
- Memory bandwidth varies widely across Apple chips; all numbers above are M5 Pro measurements — don't extrapolate; benchmark your own hardware.

## GSQ-RCO extreme quantization A/B (2026-09-15)

ISTA-DASLab's **GSQ-RCO** compresses Qwen3.8-27B to IQ3_S (~12 GB) / IQ3_XXS (~10 GB) with near-lossless quality. We ran a **4-model strict comparison** on this machine (M5 Pro / 48GB / Ollama 0.33.3): `temperature=0`, unified 12 questions (agentic coding / math / knowledge GPQA / long context / strict JSON / Chinese writing), each model run serially and unloaded after to avoid VRAM stacking.

| Model | Quant | Size | Avg decode | Quality (12-q strict) |
|-------|-------|------|------------|------------------------|
| **MLX 4-bit** (current) | NVFP4 uniform 4.0bpw | 18 GB | **29.9 tok/s** | 12/12 |
| Q5_K_M | GGUF 5.6bpw uniform | 20 GB | 14.9 tok/s | 12/12 |
| GSQ IQ3_S | 3.5bpw mixed | 12 GB | 12.6 tok/s | 12/12 |
| GSQ IQ3_XXS | 3.0bpw mixed | 10 GB | 12.5 tok/s | 12/12 |

**Three takeaways:**
- **Less RAM**: IQ3_S saves 6 GB vs MLX 4-bit, IQ3_XXS saves 8 GB — freeing room for 131K context or a co-resident H3 video model.
- **Faster**: your MLX 4-bit is ~**2.4×** GSQ mixed precision. Why: NVFP4 is GPU-friendly uniform 4-bit; IQ/GSQ mixed precision has per-weight dequant overhead that's slower on Apple Silicon's Metal backend (memory-bound decode).
- **Lossless quality (vs your MLX)**: 12-question small-sample all four tiers pass (JSON strictly parseable, math final answers match, knowledge options match). DASLab measured IQ3_XXS ~1pt off BF16 on 198-question GPQA — needs a large set to reproduce.

**Recommendation (48GB Mac, mainly agentic coding + long reasoning):**
- Speed first → keep **MLX 4-bit** (current)
- Balanced (recommended switch) → **GSQ IQ3_S**: 6 GB saved, no quality drop
- Extreme VRAM saving → **GSQ IQ3_XXS** (accept ~1pt marginal knowledge risk)
- Concurrency safety net → keep **Q5**

Full data: [A_B实测对比报告.md (A/B Report, Chinese)](./A_B实测对比报告.md) and [性能对比与量化指南.md (Quantization Guide, Chinese)](./性能对比与量化指南.md).

## FAQ

> Full troubleshooting playbook (9 issues + root cause + fix commands): **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)**. High-frequency answers below.

### Q1: Out of memory?
Keep `num_ctx 131072` (stable for single runs); if RAM is tight, lower to 65536, then downsize quantization (Q4_K_M) if still insufficient.

### Q2: Generation is slow?
Check for Swap — make sure the model is fully loaded into RAM.

### Q3: Image understanding errors out?
The MLX native `qwen3.8:27b-mlx` has a built-in vision projector — just send an image, no extra model needed. The GGUF / GSQ path (Q5, GSQ IQ3, etc.) is also GGUF format and needs the Qwen multimodal template written into the Modelfile plus mmproj attached (see pitfall 3).

### Q4: Need internet?
No. The local model runs fully offline.

### Q5: Will MLX blow up VRAM at 128K context?
Single runs won't. In the 2026-09-10 A/B, MLX at 131072 context + MTP passed 10/10 on a 5-dimension question over 2 rounds with **zero OOM**; the GSQ / GGUF path (Q5, IQ3, etc.) is the same llama.cpp engine and is equally stable at 131K single-run. The occasional "intermittent VRAM overflow" was caused by **multiple sessions/processes calling the same MLX model at once**, stacking KV-cache VRAM — not the 128K context being too large.

- Daily single run / short-mid interaction: use `qwen3.8:27b-mlx` (MLX, full 131k + MTP) — fastest and most stable.
- Long agent with concurrent sessions: switch to `qwen3.8-q5` (GGUF + llama.cpp, more stable concurrency); GSQ IQ3 shares the llama.cpp path with Q5 — same concurrency behavior, smaller but slower.
- Don't let Hermes and WorkBuddy hit MLX concurrently; stagger them.

## References

- Ollama docs: https://ollama.com/docs
- Qwen3.8 model card: https://huggingface.co/Qwen/Qwen3.8-27B
- unsloth GGUF quant: https://huggingface.co/unsloth/Qwen3.8-27B-GGUF

## Acknowledgements

Thanks to the Qwen team for open-sourcing a high-quality model; to unsloth for optimized GGUF quants; and especially to ISTA-DASLab's **GSQ-RCO** learned mixed-precision quantization, which keeps a 27B model near-lossless at ~12GB VRAM and is the basis of the "VRAM-saving balance" approach here.

## Companion article

Full war-story and decision rationale (with root-cause retrospectives of three detours), provided in two formats in-repo:
- HTML: [本地部署 Qwen3.8 全记录：从翻车到跑通](./公众号文章-本地部署Qwen3.8.html)
- Markdown: [本地部署 Qwen3.8 全记录：从翻车到跑通](./公众号文章-本地部署Qwen3.8.md)

> Issues / PRs welcome — help us add benchmark data for other hardware (M1–M4, different RAM tiers) and grow the hardware comparison table.

---

## Contact

- WeChat public account: **Jason 的落地思考**
- Juejin: [Jason的落地思考](https://juejin.cn/user/1574156379368311)

---

*This English README is a translation of the primary Chinese guide. For the authoritative, fully-detailed version, see [README.md (中文)](./README.md).*
