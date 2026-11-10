"""O ouvido da ADA: o Silero recorta a fala do WAV no Mac, o OpenRouter transcreve (endpoint e modelos no .env) e o comando do fim é separado."""
import base64
import io
import os
import re
import wave
from dataclasses import dataclass

import numpy
import requests
from faster_whisper.vad import VadOptions, collect_chunks, get_speech_timestamps, get_vad_model

TAXA = 16_000
MAX_SEGUNDOS = 30
PROMPT_INICIAL_DO_WHISPER = ("Hey Ada, open Spotify. enviar. apagar. Ada Wong, Leon, Claire Redfield, "
                             "Resident Evil Requiem, Raccoon City. enviar.")
PALAVRAS_CHAVE_DO_DEEPGRAM = ["Ada", "Ada Wong", "Leon", "Claire Redfield", "Resident Evil Requiem", "Raccoon City",
                              "enviar", "apagar"]
COMANDOS = ("enviar", "apagar")
FOLGA_EM_VOLTA_DA_FALA_MS = 800


class AudioInvalido(ValueError):
    """O áudio não é um WAV inteiro de 16 kHz, mono, 16 bits, com até MAX_SEGUNDOS."""


class OuvidoForaDoAr(RuntimeError):
    """Nenhum dos modelos do Config respondeu pro pedaço (rede, provedor fora do ar, crédito acabou)."""


@dataclass(frozen=True)
class Config:
    """O endpoint de transcrição, os modelos em ordem (o primeiro que responder vale) e quanto esperar cada um."""

    url: str
    modelos_em_ordem: list[str]
    tempo_maximo_por_modelo_s: float


def _lista_do_env(nome):
    """A variável do .env separada nas vírgulas, sem espaço em volta de cada item."""
    return [item.strip() for item in os.environ[nome].split(",")]


def configurar():
    """Monta o Config a partir do OUVIDO_URL, do OUVIDO_MODELOS e do OUVIDO_TEMPO_MAXIMO_S do .env."""
    return Config(
        url=os.environ["OUVIDO_URL"],
        modelos_em_ordem=_lista_do_env("OUVIDO_MODELOS"),
        tempo_maximo_por_modelo_s=float(os.environ["OUVIDO_TEMPO_MAXIMO_S"]),
    )


def carregar(config=None):
    """Abre o Silero (fica guardado dentro do faster-whisper) e a sessão HTTP com o OpenRouter e devolve (sessão, config)."""
    config = config or configurar()
    get_vad_model()
    openrouter = requests.Session()
    openrouter.headers["Authorization"] = f"Bearer {os.environ['OPENROUTER_API_KEY']}"
    return openrouter, config


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


def _so_a_fala(amostras):
    """O Silero acha os trechos com fala (com FOLGA_EM_VOLTA_DA_FALA_MS em volta) e junta só eles; None se não há fala."""
    trechos_com_fala = get_speech_timestamps(amostras, VadOptions(speech_pad_ms=FOLGA_EM_VOLTA_DA_FALA_MS))
    if not trechos_com_fala:
        return None
    pedacos_com_fala, _ = collect_chunks(amostras, trechos_com_fala)
    return numpy.concatenate(pedacos_com_fala)


def _wav_em_bytes(amostras):
    """As amostras em float32 de volta num WAV de TAXA Hz, mono, 16 bits."""
    pcm = (numpy.clip(amostras, -1, 1) * 32767).astype(numpy.int16).tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(TAXA)
        arquivo.writeframes(pcm)
    return buffer.getvalue()


def _pedido_pro_openrouter(modelo, wav_so_da_fala):
    """O corpo do POST: o áudio em base64, em inglês, só em provedor zdr e com a dica de vocabulário de cada provedor."""
    return {
        "model": modelo,
        "input_audio": {"data": base64.b64encode(wav_so_da_fala).decode(), "format": "wav"},
        "language": "en",
        "temperature": 0,
        "provider": {
            "zdr": True,
            "options": {
                "deepinfra/us": {"prompt": PROMPT_INICIAL_DO_WHISPER},
                "together": {"prompt": PROMPT_INICIAL_DO_WHISPER},
                "groq": {"prompt": PROMPT_INICIAL_DO_WHISPER},
                "deepgram": {"keyterm": PALAVRAS_CHAVE_DO_DEEPGRAM},
            },
        },
    }


def transcrever(openrouter, config, wav_em_bytes):
    """Recorta a fala com o Silero e transcreve no primeiro modelo que responder; só barulho volta "" sem sair do Mac."""
    amostras = _amostras_do_wav(wav_em_bytes)
    so_a_fala = _so_a_fala(amostras)
    if so_a_fala is None:
        return ""
    wav_so_da_fala = _wav_em_bytes(so_a_fala)
    for modelo in config.modelos_em_ordem:
        try:
            resposta = openrouter.post(config.url, json=_pedido_pro_openrouter(modelo, wav_so_da_fala),
                                       timeout=config.tempo_maximo_por_modelo_s)
        except requests.RequestException as erro:
            print(f"[ouvido] {modelo} não respondeu: {type(erro).__name__}")
            continue
        if resposta.status_code != 200:
            print(f"[ouvido] {modelo} devolveu HTTP {resposta.status_code}: {resposta.text[:200]}")
            continue
        texto_do_openrouter = resposta.json()["text"]
        return texto_do_openrouter.strip()
    raise OuvidoForaDoAr(f"nenhum dos {len(config.modelos_em_ordem)} modelos respondeu")


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
