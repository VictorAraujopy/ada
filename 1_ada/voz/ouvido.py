"""O ouvido da ADA: o Whisper turbo na CPU transcreve um pedaço da fala (WAV 16 kHz mono) e separa o comando do fim."""
import io
import re
import wave

import numpy
from faster_whisper import WhisperModel

MODELO = "large-v3-turbo"
VERSAO_DO_MODELO = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
THREADS = 4
TAXA = 16_000
MAX_SEGUNDOS = 30
PROMPT_INICIAL_DO_WHISPER = ("Hey Ada, open Spotify. enviar. apagar. Ada Wong, Leon, Claire Redfield, "
                             "Resident Evil Requiem, Raccoon City. enviar.")
COMANDOS = ("enviar", "apagar")
FOLGA_EM_VOLTA_DA_FALA_MS = 800


class AudioInvalido(ValueError):
    """O áudio não é um WAV inteiro de 16 kHz, mono, 16 bits, com até MAX_SEGUNDOS."""


def carregar():
    """Abre o Whisper turbo em int8 na CPU, na VERSAO_DO_MODELO, do cache local; o Hugging Face só se não estiver lá."""
    try:
        return WhisperModel(MODELO, device="cpu", compute_type="int8", cpu_threads=THREADS,
                            revision=VERSAO_DO_MODELO, local_files_only=True)
    except FileNotFoundError:
        return WhisperModel(MODELO, device="cpu", compute_type="int8", cpu_threads=THREADS,
                            revision=VERSAO_DO_MODELO)


def _amostras_do_wav(wav_em_bytes):
    """Lê o WAV, confere formato, tamanho e duração e devolve as amostras em float32 entre -1 e 1."""
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
    if len(pcm) % 2 != 0:
        raise AudioInvalido("o WAV acaba no meio de uma amostra")
    amostras = numpy.frombuffer(pcm, dtype=numpy.int16)
    if len(amostras) > MAX_SEGUNDOS * TAXA:
        raise AudioInvalido(f"áudio maior que {MAX_SEGUNDOS} s")
    return amostras.astype(numpy.float32) / 32768


def transcrever(whisper, wav_em_bytes):
    """Transcreve um pedaço em inglês com o PROMPT_INICIAL_DO_WHISPER e o detector de fala (Silero) do Whisper."""
    amostras = _amostras_do_wav(wav_em_bytes)
    trechos, _ = whisper.transcribe(amostras, language="en", initial_prompt=PROMPT_INICIAL_DO_WHISPER,
                                    vad_filter=True, vad_parameters={"speech_pad_ms": FOLGA_EM_VOLTA_DA_FALA_MS})
    return " ".join(trecho.text.strip() for trecho in trechos)


def _sem_pontuacao(palavra):
    """A palavra em minúsculas, sem ponto, vírgula nem outro sinal ("Enviar." vira "enviar")."""
    return re.sub(r"\W", "", palavra).lower()


def separar_comando(texto):
    """Se a última palavra é "enviar" ou "apagar", tira ela (e as repetições) do fim e devolve (texto, comando)."""
    palavras = texto.split()
    ultima_palavra = _sem_pontuacao(palavras[-1]) if palavras else ""
    if ultima_palavra not in COMANDOS:
        return texto.strip(), None
    while palavras and _sem_pontuacao(palavras[-1]) == ultima_palavra:
        palavras.pop()
    sem_o_comando = " ".join(palavras).rstrip(",;: ")
    return sem_o_comando, ultima_palavra
