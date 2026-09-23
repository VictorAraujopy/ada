from . import sistema, apps, musica, arquivos, lembretes

EXECUTORES = {
    **sistema.EXEC,
    **apps.EXEC,
    **musica.EXEC,
    **arquivos.EXEC,
    **lembretes.EXEC,
}
