# ADA

> A personal AI whose brain runs **entirely on a Mac** — no cloud model, no AI API. The only thing that goes online is a web search, when she decides she needs one.

ADA's personality isn't a system prompt — it's **trained into the weights**. A LoRA fine-tuned on **Qwen3.8-27B** and merged into the model gives her her own voice, opinions and taste, and she's wired to **act on macOS**. The goal: a real personal AI, not a generic assistant playing a role. *(The name comes from Ada Wong, of Resident Evil.)*

https://github.com/user-attachments/assets/843289fe-79dc-42a0-ac63-a636efc6a6f9

> This demo was recorded on one of ADA's **early versions** (still on the 9B). She's come a long way since, and there's a lot more I'll be showing soon.

## What she does

- **Talks with a personality of her own** — dry, direct, with real opinions and taste, baked into the weights (not prompted)
- **Acts on the Mac** — opens/closes apps, reads system status (battery/RAM/disk/Wi-Fi), controls music, volume, brightness and theme, takes screenshots, finds files, sets reminders & alarms
- **Searches the web** — when the subject is current or she isn't sure of a fact (DuckDuckGo, no API key); a query with personal data is blocked before it leaves the Mac
- **Chains tools** — decides on her own when to use a tool, and can run several in a single turn
- **Phone app** — an Android app that talks to the Mac over a private network: streaming replies with the live reasoning and the tools she used, conversation history (SQLite) kept on the Mac
- **The model runs 100% locally** — chat in the phone app or in the terminal

## By the numbers

| | |
|---|---|
| Model | Qwen3.8-27B with the personality merged in — one 3-bit GGUF, ~10 GB |
| Personality | LoRA, rank 16, on every linear layer, merged into the weights |
| Training data | 1,250 curated examples (+71 for validation) |
| Runtime | Apple Silicon · llama.cpp on Metal · 16k context |
| Cloud model / AI API | **none** — the only online call is the web search tool (DuckDuckGo) |

## How it works

- **Brain** — Qwen3.8-27B with the personality LoRA merged into the weights: one model file, no adapter at runtime
- **Training** — LoRA+ in bf16 on a cloud GPU; then the LoRA is merged into the bf16 weights (in f32) and the model is re-quantized to 3-bit GGUF with the base quant's per-tensor bit allocation
- **Inference** — llama.cpp with every layer on the GPU. 3-bit is the largest that fits in 16 GB without dumbing the model down, and only 16 of the 64 layers keep a KV cache (the rest are linear attention), so 16k tokens of context cost ~1 GB
- **Prompt cache on disk** — the llama.cpp state is saved at two points of the prompt (system + tools, and the conversation up to the new message), and each reply resumes from the longest start already read instead of re-reading it all: ~24 s to the first token on the very first message, then under 1 s for a new conversation and ~2-3 s per later turn
- **Tools** — the model reasons, picks a tool, runs it, then answers — no hardcoded intent matching
- **Evaluation** — each version is compared on an internal benchmark (kept out of the repo): answer keys scored by script, code run against hidden tests, conversations scored by two judges. Latest result below

## Repo layout

| Path | What |
|---|---|
| `1_ada/` | the core: brain runtime (`cerebro.py`), tool executors, grounding facts (out of the prompt for now, coming back as RAG) |
| `3_chat/` | terminal chat, for debugging the brain raw |

> The **personality dataset**, the **training pipeline** and the **model weights** are proprietary and **not** part of this repo — that's ADA's secret sauce.

## Benchmark

**Latest benchmark** (23 Sep 2026) — ADA `v12_1_en` (Qwen3.8-27B, 3-bit, English) vs ADA `v12` (Qwen3.5-9B, 4-bit, Portuguese):

| Topic | How it's scored | v12 · 9B | v12_1_en · 27B |
|---|---|---|---|
| Objective questions | script vs answer key, 108 questions — saturated | 98% | 99% |
| Open reasoning | judged, 22 duels | 25% | 75% |
| Hard questions | script + code against hidden tests, 10 questions | 60% | 80% |
| Logic & code | code quality + 5 coding tasks + a large project with a debug session | 28% | 78% |
| Conversation: close person | two judges, 6 duels | 38% | 63% |
| Conversation: visitor | two judges, 5 duels | 30% | 70% |

Model and language changed together, so the gains measure both.

## Stack

`Qwen3.8-27B` · `llama.cpp (GGUF)` · `LoRA / LoRA+` · `PEFT` · `FastAPI` · `SQLite` · Mac M4 (16 GB)

## License

**All rights reserved** — see [LICENSE](LICENSE). The code is public so you can see how it's built; the model weights, dataset and training pipeline may not be used, copied or redistributed without the author's written permission.

---

Built by **Victor Araújo**.
