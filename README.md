# ADA

> A personal AI whose brain runs **entirely on a Mac** — no cloud model, no AI API. The only thing that goes online is a web search, when she decides she needs one.

ADA's personality isn't a system prompt — it's **trained into the weights**. A LoRA fine-tuned on **Qwen3.8-27B** and merged into the model gives her her own voice, opinions and taste, and she's wired to **act on macOS**. The goal: a real personal AI, not a generic assistant playing a role. *(The name comes from Ada Wong, of Resident Evil.)*

https://github.com/user-attachments/assets/843289fe-79dc-42a0-ac63-a636efc6a6f9

> This demo was recorded on one of ADA's **early versions** (still on the 9B). She's come a long way since, and there's a lot more I'll be showing soon.

## What she does

- **Talks with a personality of her own** — dry, direct, with real opinions and taste, baked into the weights (not prompted)
- **Acts on the Mac** — opens and closes apps, and lists the ones that are open
- **Does the math exactly** — arithmetic goes through a calculator tool instead of being done in her head
- **Searches the web** — when the subject is current or she isn't sure of a fact (DuckDuckGo, no API key); a query with personal data is blocked before it leaves the Mac
- **Knows Resident Evil and The Walking Dead, and remembers past chats** — before answering, she searches a local encyclopedia (the two Fandom wikis, ~221k passages) and her own past conversations, and the closest passages go into the message (RAG)
- **Chains tools** — decides on her own when to use a tool, and can run several in a single turn
- **Sees images** — send her a photo and she reads it: receipts, screenshots, signs, what's in the picture. The vision runs on the Mac too
- **Talks by voice** — hold the phone's side button (she's the Android assistant) and talk: the Mac transcribes each phrase, and she answers out loud in an on-device voice. Saying *enviar* sends the message, *apagar* clears it, and any chat can turn into a voice conversation
- **Phone app** — an Android app that talks to the Mac over a private network: streaming replies with the live reasoning and the tools she used, photos from the camera or the gallery, voice, conversation history (SQLite) kept on the Mac
- **The model runs 100% locally** — chat in the phone app or in the terminal

## By the numbers

| | |
|---|---|
| Model | Qwen3.8-27B with the personality merged in — one 3-bit GGUF, ~10 GB |
| Personality | LoRA, rank 16, on every linear layer, merged into the weights |
| Training data | 1,612 curated examples (+71 for validation) |
| Vision | Qwen3.8's own vision encoder (461M, F16) on the CPU · a photo of up to 1024 px is up to 1,024 tokens |
| Voice | Whisper large-v3-turbo (int8) on the Mac's CPU · ~4.3 s per phrase · 4.9% word error rate on 14 real phone recordings (the phone's built-in offline recognizer: 38%) · replies spoken by an on-device Android voice |
| Knowledge (RAG) | Qwen3-Embedding-4B (2560-dim) for the wikis, Qwen3-Embedding-0.6B (1024-dim) for past conversations and as the fallback · ~221k wiki passages (~22M tokens) · up to 5 wiki passages + 2 conversation passages per message, each with similarity ≥ 0.60 |
| Runtime | Apple Silicon · llama.cpp on Metal · 16k context |
| Cloud model / AI API | **none** — the only online call is the web search tool (DuckDuckGo) |

## How it works

- **Brain** — Qwen3.8-27B with the personality LoRA merged into the weights: one model file, no adapter at runtime
- **Training** — LoRA+ in bf16 on a cloud GPU; then the LoRA is merged into the bf16 weights (in f32) and the model is re-quantized to 3-bit GGUF with the base quant's per-tensor bit allocation
- **Inference** — llama.cpp with every layer on the GPU. 3-bit is the largest that fits in 16 GB without dumbing the model down, and only 16 of the 64 layers keep a KV cache (the rest are linear attention), so 16k tokens of context cost ~1 GB
- **Prompt cache on disk** — the llama.cpp state is saved at three points of the prompt (system + tools, the conversation up to the new message, and the new message itself), and each reply resumes from the longest start already read instead of re-reading it all. The RAG passages change with every message, so they ride inside the new message: each reply re-reads only the last exchange and the new message
- **Vision** — Qwen3.8 is natively multimodal, but the GGUF ships the vision encoder as a separate file (the mmproj). It runs on the CPU, since the 27B already fills the GPU, and in F16: same output as the original BF16 weights, ~15x faster on the CPU. A photo takes its place in the prompt cache under a hash of the image, so a follow-up question about the same photo doesn't read it again
- **RAG** — the Resident Evil and The Walking Dead wikis live in a local SQLite database, split at sentence boundaries into passages of up to 900 characters, the size that goes into the prompt. Each passage has a Qwen3-Embedding-4B vector (stored in float16), embedded once on a cloud GPU; at runtime the question is embedded by the same model on a second machine on the private network (a PC, on its CPU) and compared against all of them on the Mac. If that machine is off, the search falls back to Qwen3-Embedding-0.6B vectors, with the question embedded on the Mac's CPU. Up to 5 of the closest passages and up to 2 exchanges from past conversations (never the current one) go into the last user message, never into the system prompt; each needs a similarity of at least 0.60, so most app commands and small talk get none
- **Voice** — the phone cuts the speech at pauses and sends each chunk (16 kHz WAV) to the Mac, where Whisper large-v3-turbo transcribes it on the CPU (the GPU is already full with the 27B). A short context prompt teaches it the spelling of "Ada", the Resident Evil names and the two command words, which are Portuguese on purpose (*enviar* = send, *apagar* = clear): no English synonym slips into a sentence by accident. The reply is spoken sentence by sentence as it streams, by the phone's own offline voice; the audio is never stored
- **Tools** — the model reasons, picks a tool, runs it, then answers — no hardcoded intent matching
- **Evaluation** — each version is compared on an internal benchmark (kept out of the repo): answer keys scored by script, code run against hidden tests, conversations scored by two judges. Latest result below

## Repo layout

| Path | What |
|---|---|
| `1_ada/` | the core: brain runtime (`cerebro.py`), tool executors, RAG (`conhecimento/`: search over the local encyclopedia and past conversations), the ear (`voz/`: Whisper transcription for the phone's voice) |
| `3_chat/` | terminal chat, for debugging the brain raw |
| [`ada-api`](https://github.com/VictorAraujopy/ada-api) | the API the phone talks to (FastAPI + SSE, its own repo) |
| [`ada-app`](https://github.com/VictorAraujopy/ada-app) | the Android app (Expo / React Native, its own repo) |

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

`Qwen3.8-27B` · `llama.cpp (GGUF)` · `Qwen3-Embedding-4B / 0.6B` · `sentence-transformers` · `faster-whisper (Whisper large-v3-turbo)` · `LoRA / LoRA+` · `PEFT` · `FastAPI` · `SQLite` · `Expo / React Native` · Mac M4 (16 GB)

## License

**All rights reserved** — see [LICENSE](LICENSE). The code is public so you can see how it's built; the model weights, dataset and training pipeline may not be used, copied or redistributed without the author's written permission.

---

Built by **Victor Araújo**.
