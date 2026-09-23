from datetime import datetime
from pathlib import Path

from ._base import sh


def tirar_screenshot(**kw):
    arq = f"{Path.home()}/Desktop/screenshot_{datetime.now():%H%M%S}.png"
    sh(["screencapture", arq])
    return f"screenshot at {arq}"


def buscar_arquivo(nome=None, **kw):
    if not nome:
        return "missing the name"
    achados = [l for l in sh(["mdfind", "-name", nome]).splitlines() if l][:5]
    return "found:\n" + "\n".join(achados) if achados else f"no file found with '{nome}'"


EXEC = {"tirar_screenshot": tirar_screenshot, "buscar_arquivo": buscar_arquivo}
