"""
Chat com a ADA por VOZ: voce digita, ela responde FALANDO.

Três etapas:
  - PENSAR:   Qwen3.5-9B + LoRA (1_modelo/ada_v6_9b) -> responde em PORTUGUES, onde a ADA
              e ela mesma (sabe o nome, o tom, a favorita).
  - TRADUZIR: argostranslate PT->EN -> a fala sai sem sotaque (a voz e clonada em EN).
  - FALAR:    Qwen3-TTS 4bit -> clona a voz dela (4_voz/voz_ada.wav) e fala o ingles.

No terminal voce ve a resposta em PT (a ADA real); a voz toca em EN.

Rodar, da raiz do projeto:
    .venv/bin/python 4_voz/chat_voz.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io.wavfile import write as wav_write

from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.trainer.utils import apply_lora_layers
from mlx_audio.tts.utils import load_model
import mlx.core as mx
import argostranslate.translate

RAIZ = Path(__file__).resolve().parent.parent
VOZ_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "5_conhecimento"))
from conhecimento import carregar_conhecimento  # base de fatos confiáveis
sys.path.insert(0, str(RAIZ / "6_assistente"))
import cerebro_tools as ct  # runtime de tools (mesmo do chat de texto)

# --- cerebro (pensar) ---
CEREBRO = "mlx-community/Qwen3.5-9B-MLX-4bit"
# ADA_ADAPTER escolhe a versão (default v6_9b, o 9B treinado na nuvem); ADA_ADAPTER=ada_v5 volta pro antigo
ADAPTER = str(RAIZ / "1_modelo" / os.environ.get("ADA_ADAPTER", "ada_v6_9b"))
_BASE = "" if os.environ.get("ADA_BASE", "on") == "off" else "\n\n" + carregar_conhecimento()
SYSTEM = ("Usuário atual: Victor, seu criador. Você responde por voz, então vá direto ao "
          "ponto. Se o pedido pede uma ferramenta (hora, status, app, música...), use a "
          "ferramenta — você não tem relógio nem sensores próprios." + _BASE)
MAX_TOKENS = 4096          # solto: nunca corta; teto so de seguranca (anti-loop)
TEMPERATURE = 0.5
TOP_P = 0.8                # corta a cauda improvavel (evita alucinacao/frase quebrada) sem ficar decorado
REPETITION_PENALTY = 1.05

# --- voz (falar) ---
VOZ_MODELO = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit"  # 4bit: ~1.9x tempo real (bf16 dava 0.44x), mesma voz
VOZ_REF = str(VOZ_DIR / "voz_ada.wav")
VOZ_REF_TEXT = (VOZ_DIR / "voz_ada.txt").read_text().strip()
SAMPLE_RATE = 24000
VOZ_TEMP = 0.6  # ponto doce: voz viva (varia o tom) sem trocar de identidade
# Streaming por BLOCO: junta frases num bloco de áudio antes de tocar.
#   MAIOR  -> menos cortes, porém espera mais pra começar a falar
#   MENOR  -> começa a falar antes, porém com mais cortes
BLOCO_CHARS = 100


def carregar():
    _b = "OFF (teste puro)" if os.environ.get("ADA_BASE", "on") == "off" else "ON"
    print(f"[ADAPTER: {Path(ADAPTER).name} | base de conhecimento: {_b}]")
    model, processor = load(CEREBRO, processor_config={"trust_remote_code": True})
    config = model.config.__dict__
    model = apply_lora_layers(model, ADAPTER)
    voz_model = load_model(VOZ_MODELO)
    return model, processor, config, voz_model


def responder(model, processor, config, historico):
    resposta, passo = ct.responder(
        model, processor, config, historico,
        max_tokens=MAX_TOKENS, temperature=TEMPERATURE, top_p=TOP_P,
        repetition_penalty=REPETITION_PENALTY,
    )
    if passo:  # log das tools executadas (nome -> resultado)
        for t_nome, _, t_res in passo:
            print(f"  [tool: {t_nome} -> {t_res}]", flush=True)
    mx.clear_cache()  # libera buffers do 9B antes da voz
    return resposta


def traduzir(texto):
    """Traduz a resposta (PT -> EN) só pra voz falar sem sotaque. O cérebro pensa em PT,
    onde a ADA é ela mesma (sabe o nome, o tom); a tradução preserva o nome próprio."""
    return argostranslate.translate.translate(texto, "pt", "en")


def falar(voz_model, texto):
    """Gera frase a frase (qualidade, sem alucinar em texto longo), mas AGRUPA o áudio
    em blocos de >= BLOCO_CHARS e toca cada bloco inteiro de uma vez — fluido dentro do
    bloco, com corte só entre blocos (poucos). Enquanto um bloco toca, o próximo já vai
    sendo gerado, então a fala longa do bloco cobre a geração do seguinte."""
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]
    if not frases:
        return

    def tocar(pedacos, idx, anterior):
        arq = VOZ_DIR / f"_fala_{idx % 2}.wav"  # alterna 2 arquivos pra não pisar no que toca
        audio = np.clip(np.concatenate(pedacos), -1.0, 1.0)
        wav_write(str(arq), SAMPLE_RATE, (audio * 32767).astype(np.int16))
        if anterior is not None:
            anterior.wait()  # só solta o bloco novo quando o anterior terminar de tocar
        return subprocess.Popen(["afplay", str(arq)])

    proc, bloco, n_chars, idx = None, [], 0, 0
    for frase in frases:
        partes = list(voz_model.generate(
            text=frase, ref_audio=VOZ_REF, ref_text=VOZ_REF_TEXT, temperature=VOZ_TEMP,
        ))
        bloco += [np.asarray(p.audio, dtype=np.float32).reshape(-1) for p in partes]
        n_chars += len(frase)
        if n_chars >= BLOCO_CHARS:           # bloco cheio: toca e abre o próximo
            proc = tocar(bloco, idx, proc)
            idx += 1
            bloco, n_chars = [], 0
    if bloco:                                 # o resto vira o último bloco
        proc = tocar(bloco, idx, proc)
    if proc is not None:
        proc.wait()
    mx.clear_cache()


def main():
    print("Carregando a ADA (cerebro + voz)... (uns 30-60s)")
    model, processor, config, voz_model = carregar()

    print("\n" + "=" * 56)
    print("  ADA pronta. Fala com ela (digitando).  ('sair' encerra)")
    print("=" * 56 + "\n")

    historico = [{"role": "system", "content": SYSTEM}]

    while True:
        try:
            entrada = input("\033[1mvocê>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté, Victor.")
            break
        if entrada.lower() in ("sair", "exit", "quit"):
            print("Até, Victor.")
            break
        if not entrada:
            continue

        historico.append({"role": "user", "content": entrada})
        resposta = responder(model, processor, config, historico)
        print(f"\033[96mADA>\033[0m {resposta}\n")
        historico.append({"role": "assistant", "content": resposta})

        falar(voz_model, traduzir(resposta))  # pensa em PT, fala em EN


if __name__ == "__main__":
    main()
