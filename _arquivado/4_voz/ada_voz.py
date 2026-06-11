"""
ADA por voz COMPLETO: voce FALA (em PT), ela ENTENDE, PENSA e RESPONDE FALANDO.

Pipeline:
  voce fala PT
    -> Whisper transcreve o PT
    -> 9B + LoRA responde em PORTUGUES (onde a ADA e ela mesma)
    -> argostranslate traduz PT->EN
    -> voz da ADA fala o ingles (sem sotaque)

Reaproveita carregar()/responder()/traduzir()/falar() do chat_voz.py.

Rodar, da raiz do projeto:
    .venv/bin/python 4_voz/ada_voz.py

(Na 1a vez baixa o Whisper; o macOS pede permissao de microfone — permitir.)
"""
import numpy as np
import sounddevice as sd
import mlx_whisper
import mlx.core as mx

import chat_voz as cv  # cerebro + voz (carregar/responder/falar/SYSTEM)

# Whisper medium: transcreve o PT (task=transcribe). A traducao pra fala vem depois,
# no chat_voz, sobre a RESPOSTA — assim o cerebro pensa todo em portugues.
OUVIDO = "mlx-community/whisper-medium-mlx"  # unificado com o daemon (6_assistente/ada.py)
FS = 16000  # 16 kHz


def ouvir():
    """Grava do microfone e devolve o que voce disse, transcrito em portugues."""
    print("\n\033[1m🎤 fala (PT)\033[0m — aperte ENTER quando terminar.", flush=True)
    frames = []

    def cb(indata, n, t, status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=FS, channels=1, dtype="float32", callback=cb):
        input()
    if not frames:
        return ""
    audio = np.concatenate(frames, axis=0).flatten()
    if len(audio) < FS * 0.3:
        return ""
    r = mlx_whisper.transcribe(
        audio, path_or_hf_repo=OUVIDO, language="pt", task="transcribe",
    )
    mx.clear_cache()  # libera buffers do Whisper antes de pensar/falar
    return r["text"].strip()


def main():
    print("Carregando a ADA completa (ouvido + cérebro + voz)...")
    model, processor, config, voz_model = cv.carregar()

    print("\n" + "=" * 56)
    print("  ADA pronta. FALA com ela.  (Ctrl+C encerra)")
    print("=" * 56)

    historico = [{"role": "system", "content": cv.SYSTEM}]

    while True:
        try:
            falado = ouvir()
        except (EOFError, KeyboardInterrupt):
            print("\nAté, Victor.")
            break
        if not falado:
            print(">> não ouvi nada.")
            continue

        print(f"\033[90m(entendi: {falado})\033[0m", flush=True)
        historico.append({"role": "user", "content": falado})
        resposta = cv.responder(model, processor, config, historico)
        print(f"\033[96mADA>\033[0m {resposta}\n", flush=True)
        historico.append({"role": "assistant", "content": resposta})

        cv.falar(voz_model, cv.traduzir(resposta))  # pensa em PT, fala em EN


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAté, Victor.")
