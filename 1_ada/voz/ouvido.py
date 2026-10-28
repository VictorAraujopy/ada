"""O ouvido da ADA: o Whisper turbo na CPU transcreve um pedaço da fala (WAV 16 kHz mono) e separa o comando do fim."""
import io
import re
import wave

import numpy
from faster_whisper import WhisperModel

MODELO = "large-v3-turbo"
THREADS = 4
TAXA = 16_000
MAX_SEGUNDOS = 30
CONTEXTO = ("Hey Ada, open Spotify. enviar. apagar. Ada Wong, Leon, Claire Redfield, Resident Evil Requiem, "
            "Raccoon City. enviar.")
COMANDOS = ("enviar", "apagar")


class AudioInvalido(ValueError):
    """O áudio não é um WAV de 16 kHz, mono, 16 bits, com até MAX_SEGUNDOS."""


def carregar():
    """Abre o Whisper turbo em int8 na CPU; na primeira vez baixa do Hugging Face (~1,6 GB na memória)."""
    return WhisperModel(MODELO, device="cpu", compute_type="int8", cpu_threads=THREADS)


def _amostras_do_wav(wav_em_bytes):
    """Lê o WAV, confere formato e duração e devolve as amostras em float32 entre -1 e 1."""
    try:
        with wave.open(io.BytesIO(wav_em_bytes)) as arquivo:
            canais = arquivo.getnchannels()
            bytes_por_amostra = arquivo.getsampwidth()
            taxa = arquivo.getframerate()
            pcm = arquivo.readframes(arquivo.getnframes())
    except (wave.Error, EOFError):
        raise AudioInvalido("não é um WAV inteiro") from None
    if canais != 1 or bytes_por_amostra != 2 or taxa != TAXA:
        raise AudioInvalido(f"o WAV tem que ser mono, 16 bits, {TAXA} Hz (veio {canais} canais, "
                            f"{8 * bytes_por_amostra} bits, {taxa} Hz)")
    amostras = numpy.frombuffer(pcm, dtype=numpy.int16)
    if len(amostras) > MAX_SEGUNDOS * TAXA:
        raise AudioInvalido(f"áudio maior que {MAX_SEGUNDOS} s")
    return amostras.astype(numpy.float32) / 32768


def transcrever(whisper, wav_em_bytes):
    """Transcreve um pedaço da fala em inglês, com o CONTEXTO ensinando a grafia de "Ada", "enviar" e "apagar"."""
    amostras = _amostras_do_wav(wav_em_bytes)
    trechos, _ = whisper.transcribe(amostras, language="en", initial_prompt=CONTEXTO)
    return " ".join(trecho.text.strip() for trecho in trechos)


def _sem_pontuacao(palavra):
    """A palavra em minúsculas, sem ponto, vírgula nem outro sinal ("Enviar." vira "enviar")."""
    return re.sub(r"\W", "", palavra).lower()


def separar_comando(texto):
    """Se a última palavra é "enviar" ou "apagar", tira ela (e as repetições) do fim e devolve (texto, comando)."""
    palavras = texto.split()
    if not palavras or _sem_pontuacao(palavras[-1]) not in COMANDOS:
        return texto.strip(), None
    comando = _sem_pontuacao(palavras[-1])
    while palavras and _sem_pontuacao(palavras[-1]) == comando:
        palavras.pop()
    sem_o_comando = " ".join(palavras).rstrip(",;: ")
    return sem_o_comando, comando
