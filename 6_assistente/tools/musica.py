"""Tools de MUSICA: tocar, pausar e pular faixa (Spotify ou Music)."""
from ._base import osa, player


def tocar_musica(busca=None, **kw):
    app = player()
    osa(f'tell application "{app}" to play')
    return f"tocando no {app}" + (f" (busca: {busca})" if busca else "")


def pausar_musica(**kw):
    osa(f'tell application "{player()}" to pause')
    return "pausado"


def proxima_musica(**kw):
    osa(f'tell application "{player()}" to next track')
    return "proxima faixa"


EXEC = {"tocar_musica": tocar_musica, "pausar_musica": pausar_musica, "proxima_musica": proxima_musica}
