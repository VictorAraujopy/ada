from . import sistema, apps, musica, arquivos, lembretes, web

EXECUTORES = {
    **sistema.EXEC,
    **apps.EXEC,
    **musica.EXEC,
    **arquivos.EXEC,
    **lembretes.EXEC,
    **web.EXEC,
}
