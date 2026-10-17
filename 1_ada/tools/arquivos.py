"""Tools de arquivos: screenshot e busca pelo Spotlight."""
from datetime import datetime
from pathlib import Path

from ._base import sh


def tirar_screenshot(**kw):
    """Salva um screenshot da tela na Mesa."""
    arq = f"{Path.home()}/Desktop/screenshot_{datetime.now():%H%M%S}.png"
    sh(["screencapture", arq])
    return f"screenshot at {arq}"


def buscar_arquivo(nome=None, **kw):
    """Acha até 5 arquivos pelo nome com o Spotlight (mdfind)."""
    if not nome:
        return "missing the name"
    achados = [l for l in sh(["mdfind", "-name", nome]).splitlines() if l][:5]
    return "found:\n" + "\n".join(achados) if achados else f"no file found with '{nome}'"


EXEC = {"tirar_screenshot": tirar_screenshot, "buscar_arquivo": buscar_arquivo}
