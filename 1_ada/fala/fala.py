"""A fala da ADA: uma frase da resposta vira mp3 no OpenRouter, na primeira das vozes do .env que responder."""
import os
from dataclasses import dataclass

import requests


class FalaForaDoAr(RuntimeError):
    """Nenhuma das vozes do Config devolveu o áudio da frase (rede, provedor fora do ar, crédito acabou)."""


@dataclass(frozen=True)
class Voz:
    """Um modelo de voz do OpenRouter, o nome da voz nele e quanto esperar pelo mp3."""

    modelo: str
    nome: str
    tempo_maximo_s: float


@dataclass(frozen=True)
class Config:
    """O endpoint de voz e as vozes em ordem (a primeira que responder vale)."""

    url: str
    vozes_em_ordem: list[Voz]


def _lista_do_env(nome):
    """A variável do .env separada nas vírgulas, sem espaço em volta de cada item."""
    return [item.strip() for item in os.environ[nome].split(",")]


def configurar():
    """Monta o Config a partir do FALA_URL e das listas FALA_MODELOS, FALA_VOZES e FALA_TEMPOS_MAXIMOS_S do .env."""
    modelos = _lista_do_env("FALA_MODELOS")
    nomes_das_vozes = _lista_do_env("FALA_VOZES")
    tempos_maximos_s = [float(tempo) for tempo in _lista_do_env("FALA_TEMPOS_MAXIMOS_S")]
    if not len(modelos) == len(nomes_das_vozes) == len(tempos_maximos_s):
        raise ValueError("FALA_MODELOS, FALA_VOZES e FALA_TEMPOS_MAXIMOS_S precisam ter o mesmo número de itens")
    vozes_em_ordem = [Voz(modelo, nome, tempo_maximo_s)
                      for modelo, nome, tempo_maximo_s in zip(modelos, nomes_das_vozes, tempos_maximos_s)]
    return Config(url=os.environ["FALA_URL"], vozes_em_ordem=vozes_em_ordem)


def carregar(config=None):
    """Abre a sessão HTTP com o OpenRouter, com a chave do .env, e devolve (sessão, config)."""
    config = config or configurar()
    openrouter = requests.Session()
    openrouter.headers["Authorization"] = f"Bearer {os.environ['OPENROUTER_API_KEY']}"
    return openrouter, config


def _pedido_pro_openrouter(voz, frase):
    """O corpo do POST: a frase, o modelo e a voz, mp3 de volta e só provedor que não guarda o texto (zdr)."""
    return {"model": voz.modelo, "input": frase, "voice": voz.nome, "response_format": "mp3", "provider": {"zdr": True}}


def falar(openrouter, config, frase):
    """Devolve o mp3 da frase na primeira voz que responder; se nenhuma responder, levanta FalaForaDoAr."""
    for voz in config.vozes_em_ordem:
        try:
            resposta = openrouter.post(config.url, json=_pedido_pro_openrouter(voz, frase), timeout=voz.tempo_maximo_s)
        except requests.RequestException as erro:
            print(f"[fala] {voz.modelo} não respondeu: {type(erro).__name__}")
            continue
        if resposta.status_code != 200:
            print(f"[fala] {voz.modelo} devolveu HTTP {resposta.status_code}: {resposta.text[:200]}")
            continue
        mp3_do_openrouter = resposta.content
        return mp3_do_openrouter
    raise FalaForaDoAr(f"nenhuma das {len(config.vozes_em_ordem)} vozes respondeu")
