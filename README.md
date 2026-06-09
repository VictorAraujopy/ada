# ADA

> A personal AI that runs **entirely on a Mac** — no cloud, no API, nothing ever leaves the machine.

ADA's personality isn't a system prompt — it's **trained into the weights**. A LoRA adapter fine-tuned on top of **Qwen3.5-9B** gives her her own voice, opinions and taste, and she's wired to **act on macOS**. The goal: a real personal AI, not a generic assistant playing a role. *(The name comes from Ada Wong, of Resident Evil.)*

<!-- DEMO: drag your screen-recording (.mp4/.gif) into the GitHub README editor right here — it uploads and embeds automatically. This is the highest-impact spot on the page. -->

## What she does

- **Talks with a personality of her own** — dry, direct, with real opinions and taste, baked into the weights (not prompted)
- **Acts on the Mac** — opens/closes apps, reads system status (battery/RAM/disk/Wi-Fi), controls music, volume, brightness and theme, takes screenshots, finds files, sets reminders & alarms
- **Chains tools** — decides on her own when to use a tool, and can run several in a single turn
- **Voice + text** — listens (Whisper), thinks, and replies out loud (voice-cloned TTS), or chat through a streaming web UI
- **100% local & offline** — runs as a background daemon or in the terminal

## By the numbers

| | |
|---|---|
| Base model | Qwen3.5-9B |
| Personality adapter | **43M params — 0.48% of the model** |
| Training data | 4,545 hand-built examples |
| Runtime | Apple Silicon · MLX · 4-bit |
| Cloud / API at runtime | **none — fully offline** |

## How it works

- **Brain** — Qwen3.5-9B (base) + a LoRA adapter that carries the personality
- **Training** — LoRA / QLoRA (4-bit) on a cloud GPU, then converted to MLX to run locally
- **Inference** — MLX on Apple Silicon's unified memory; the 9B fits in 16 GB at 4-bit, fully offline
- **Tools** — the model reasons, picks a tool, runs it, then answers — no hardcoded intent matching

## Repo layout

| Path | What |
|---|---|
| `1_modelo/` | the LoRA adapter (MLX format) — the "brain" |
| `3_chat/` | terminal text chat |
| `4_voz/` | voice pipeline (Whisper → 9B → TTS) |
| `5_conhecimento/` | grounding facts (anti-hallucination) |
| `6_assistente/` | tool runtime + resident daemon |
| `7_interface/` | streaming web chat |

> The **personality dataset** and **training pipeline** are proprietary and **not** part of this repo — that's ADA's secret sauce.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python 3_chat/chat_ada.py     # text chat
python 4_voz/ada_voz.py       # voice: you talk, she talks back
```

The current adapter (`ada_v10_9b`) is included; the **Qwen3.5-9B** base downloads automatically on first run (~5 GB at 4-bit). Set `ADA_BASE=off` to test the raw LoRA without the grounding facts.

## Stack

`Qwen3.5-9B` · `MLX` · `LoRA / QLoRA` · `PEFT` · `Whisper` · `FastAPI` · Mac M4 (16 GB)

## License

**All rights reserved** — see [LICENSE](LICENSE). The code is public so you can see how it's built; the adapter weights, dataset and training pipeline may not be used, copied or redistributed without the author's written permission.

---

Built by **Victor Araújo**.
