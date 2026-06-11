# ADA

> A personal AI that runs **entirely on a Mac** — no cloud, no API, nothing ever leaves the machine.

ADA's personality isn't a system prompt — it's **trained into the weights**. A LoRA adapter fine-tuned on top of **Qwen3.5-9B** gives her her own voice, opinions and taste, and she's wired to **act on macOS**. The goal: a real personal AI, not a generic assistant playing a role. *(The name comes from Ada Wong, of Resident Evil.)*

https://github.com/user-attachments/assets/843289fe-79dc-42a0-ac63-a636efc6a6f9

## What she does

- **Talks with a personality of her own** — dry, direct, with real opinions and taste, baked into the weights (not prompted)
- **Acts on the Mac** — opens/closes apps, reads system status (battery/RAM/disk/Wi-Fi), controls music, volume, brightness and theme, takes screenshots, finds files, sets reminders & alarms
- **Chains tools** — decides on her own when to use a tool, and can run several in a single turn
- **Persistent web chat** — streaming UI with live reasoning, tool cards, conversation history (SQLite) and markdown export
- **100% local & offline** — chat in the browser or in the terminal

> The **voice pipeline** (Whisper → 9B → voice-cloned TTS) works and lives in `_arquivado/` — on hold until it fits comfortably next to the 9B on 16 GB.

## By the numbers

| | |
|---|---|
| Base model | Qwen3.5-9B |
| Personality adapter | **43M params — 0.48% of the model** |
| Training data | 4,537 curated examples |
| Runtime | Apple Silicon · MLX · 4-bit |
| Cloud / API at runtime | **none — fully offline** |

## How it works

- **Brain** — Qwen3.5-9B (base) + a LoRA adapter that carries the personality
- **Training** — LoRA / QLoRA (4-bit) on a cloud GPU, then converted to MLX to run locally
- **Inference** — MLX on Apple Silicon's unified memory; the 9B fits in 16 GB at 4-bit, fully offline
- **Tools** — the model reasons, picks a tool, runs it, then answers — no hardcoded intent matching
- **Evaluation** — versions are compared on a fixed 50-question benchmark: 5 objective categories scored by script against an answer key, plus blind-judged reasoning (see `6_benchmark/`)

## Repo layout

| Path | What |
|---|---|
| `1_ada/` | the core: brain runtime (`cerebro.py`), tool executors, grounding facts (RAG) |
| `2_interface/` | the main product — web chat (`back/` FastAPI + SSE, `front/` vanilla JS) |
| `3_chat/` | terminal chat, for debugging the brain raw |
| `6_benchmark/` | the evaluation harness — fixed questions, scoring, comparison chart |
| `_modelo/` | the LoRA adapter (MLX format) — the weights |
| `_arquivado/` | the voice pipeline + resident daemon, parked |

> The **personality dataset** and **training pipeline** are proprietary and **not** part of this repo — that's ADA's secret sauce.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python 2_interface/back/server.py   # web chat -> http://localhost:8000
python 3_chat/chat_ada.py           # terminal chat
```

The current adapter (`ada_v10_9b`) is included; the **Qwen3.5-9B** base downloads automatically on first run (~5 GB at 4-bit). Set `ADA_BASE=off` to test the raw LoRA without the grounding facts.

**Next up:** `v11b` — a reasoning upgrade (every training example rebuilt with a real chain of thought, plus new math / ambiguity / tool-boundary examples). Currently in blind-benchmark validation against v10.

## Stack

`Qwen3.5-9B` · `MLX` · `LoRA / QLoRA` · `PEFT` · `FastAPI` · `SQLite` · Mac M4 (16 GB)

## License

**All rights reserved** — see [LICENSE](LICENSE). The code is public so you can see how it's built; the adapter weights, dataset and training pipeline may not be used, copied or redistributed without the author's written permission.

---

Built by **Victor Araújo**.
