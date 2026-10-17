"""Tools de música: tocar, pausar e pular no player que estiver aberto."""
from ._base import osa, player


def tocar_musica(busca=None, **kw):
    """Dá play no player aberto."""
    app = player()
    osa(f'tell application "{app}" to play')
    return f"playing on {app}" + (f" (search: {busca})" if busca else "")


def pausar_musica(**kw):
    """Pausa o player aberto."""
    osa(f'tell application "{player()}" to pause')
    return "playback paused"


def proxima_musica(**kw):
    """Pula pra próxima faixa."""
    osa(f'tell application "{player()}" to next track')
    return "next track"


EXEC = {"tocar_musica": tocar_musica, "pausar_musica": pausar_musica, "proxima_musica": proxima_musica}
