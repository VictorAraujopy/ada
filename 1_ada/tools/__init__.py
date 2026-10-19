"""As tools da ADA por categoria e o EXECUTORES, que liga o nome de cada uma à função real."""
from . import sistema, apps, musica, arquivos, lembretes, web, calculo

EXECUTORES = {
    **sistema.EXEC,
    **apps.EXEC,
    **musica.EXEC,
    **arquivos.EXEC,
    **lembretes.EXEC,
    **web.EXEC,
    **calculo.EXEC,
}
