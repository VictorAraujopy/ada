"""
Daemon da ADA — residente, controlado pelo Hammerspoon.
  Ctrl+Alt+E liga · Ctrl+Alt+T desliga · segurar o botão de cima = falar.

Fluxo ao usar o botão:
  /start -> começa a gravar o microfone
  /stop  -> para, transcreve (PT), pensa (9B em PT), traduz e FALA (EN)
  /clear -> limpa o contexto da conversa

O cérebro e a voz vêm de 4_voz/chat_voz.py. O MLX EXIGE a thread principal, então:
  - o servidor HTTP roda numa thread só pra receber o sinal e ENFILEIRAR;
  - a thread principal (loop) tira da fila e processa (Whisper -> 9B -> voz).

    .venv/bin/python 6_assistente/ada.py
"""
import queue
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np
import sounddevice as sd
import mlx_whisper
import mlx.core as mx

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "4_voz"))
import chat_voz as cv  # carregar / responder / traduzir / falar / SYSTEM

PORTA = 8765
FS = 16000
OUVIDO = "mlx-community/whisper-medium-mlx"  # medium: mais preciso que small, formato .npz (o que o mlx_whisper le)
# contexto pro Whisper -> ele "espera" essas palavras e erra menos em nomes/comandos
DICA_VOZ = ("Conversa em português entre o Victor e a ADA, a assistente dele. Ele pode "
            "pedir as horas, o status do Mac, abrir ou fechar apps, controlar a música.")
LOG = Path(__file__).resolve().parent / "ada_daemon.log"
HS = "/opt/homebrew/bin/hs"  # CLI do Hammerspoon, pra atualizar o feedback na tela


def feedback(lua):
    """Atualiza o aviso na tela via Hammerspoon (silencioso se falhar)."""
    try:
        subprocess.run([HS, "-c", lua], timeout=2, capture_output=True)
    except Exception:
        pass

_frames = []
_stream = None
_fila = queue.Queue()


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def eh_ruido(texto):
    """Pega alucinacao do Whisper em silencio/ruido (ex: 'Ek Ek Ek...' repetido):
    se uma palavra so domina a transcricao, e ruido -> ignora."""
    from collections import Counter
    palavras = texto.split()
    if len(palavras) < 4:
        return False
    return Counter(palavras).most_common(1)[0][1] / len(palavras) > 0.5


def gravar_inicio():
    global _frames, _stream
    _frames = []
    _stream = sd.InputStream(samplerate=FS, channels=1, dtype="float32",
                             callback=lambda indata, n, t, s: _frames.append(indata.copy()))
    _stream.start()


def gravar_fim():
    global _stream
    if _stream is not None:
        _stream.stop(); _stream.close(); _stream = None
    if not _frames:
        return None
    audio = np.concatenate(_frames, axis=0).flatten()
    return audio if len(audio) >= FS * 0.3 else None  # ignora toque rápido (< 0.3s)


class Gatilho(BaseHTTPRequestHandler):
    def do_GET(self):
        rota = self.path.strip("/")
        if rota == "start":
            gravar_inicio()
        elif rota == "stop":
            audio = gravar_fim()
            if audio is not None:
                _fila.put(("fala", audio))
        elif rota == "clear":
            _fila.put(("clear", None))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass  # silencia o log padrão do http.server


def main():
    log("Carregando a ADA (cérebro + voz)... (~15s)")
    model, processor, config, voz_model = cv.carregar()
    # aquece o Whisper agora (senão a 1a fala trava carregando ele)
    mlx_whisper.transcribe(np.zeros(FS // 2, dtype=np.float32),
                           path_or_hf_repo=OUVIDO, language="pt", task="transcribe")
    mx.clear_cache()

    historico = [{"role": "system", "content": cv.SYSTEM}]
    srv = HTTPServer(("127.0.0.1", PORTA), Gatilho)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    log(f"=== ADA PRONTA — segure o botão de cima pra falar (porta {PORTA}) ===")
    cv.falar(voz_model, "Ready.")  # avisa, falando, que carregou

    while True:
        cmd, dado = _fila.get()
        if cmd == "clear":
            historico = [{"role": "system", "content": cv.SYSTEM}]
            log("(contexto limpo)")
        elif cmd == "fala":
            r = mlx_whisper.transcribe(dado, path_or_hf_repo=OUVIDO, language="pt",
                                       task="transcribe", condition_on_previous_text=False,
                                       initial_prompt=DICA_VOZ)
            mx.clear_cache()
            texto = r["text"].strip()
            if not texto or eh_ruido(texto):
                log(f"(ignorado, sem fala clara: {texto[:40]!r})")
                continue
            log(f"você: {texto}")
            historico.append({"role": "user", "content": texto})
            resposta = cv.responder(model, processor, config, historico)
            log(f"ADA: {resposta}")
            historico.append({"role": "assistant", "content": resposta})
            feedback("adaFalando()")
            cv.falar(voz_model, cv.traduzir(resposta))
            feedback("adaParado()")


if __name__ == "__main__":
    main()
