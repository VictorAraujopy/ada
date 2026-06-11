"""Tools de TELA e ARQUIVOS: tirar screenshot, buscar arquivo por nome."""
from datetime import datetime
from pathlib import Path

from ._base import sh


def tirar_screenshot(**kw):
    arq = f"{Path.home()}/Desktop/screenshot_{datetime.now():%H%M%S}.png"
    sh(["screencapture", arq])
    return f"screenshot em {arq}"


def buscar_arquivo(nome=None, **kw):
    if not nome:
        return "faltou o nome"
    achados = [l for l in sh(["mdfind", "-name", nome]).splitlines() if l][:5]
    return "achei:\n" + "\n".join(achados) if achados else f"nada com '{nome}'"


EXEC = {"tirar_screenshot": tirar_screenshot, "buscar_arquivo": buscar_arquivo}
