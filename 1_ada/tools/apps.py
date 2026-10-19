"""Tools de apps do Mac: abrir, fechar e listar os abertos."""
import re

from ._base import sh, osa


def abrir_app(nome=None, **kw):
    """Abre o app pelo nome."""
    if not nome:
        return "missing the app name"
    return f"couldn't find '{nome}'" if sh(["open", "-a", nome]) else f"{nome} opened"


def fechar_app(nome=None, **kw):
    """Fecha o app pelo nome."""
    if not nome:
        return "missing the app name"
    osa(f'tell application "{nome}" to quit')
    return f"{nome} closed"


def listar_apps_abertos(**kw):
    """Lista os apps com ícone no Dock lendo o lsappinfo, que não pede permissão de Automação."""
    saida_do_lsappinfo = sh(["lsappinfo", "list"])
    apps = []
    nome_do_app = None
    for linha in saida_do_lsappinfo.splitlines():
        cabecalho_do_app = re.match(r'\s*\d+\) "(.+?)"', linha)
        if cabecalho_do_app:
            nome_do_app = cabecalho_do_app.group(1)
        elif 'type="Foreground"' in linha:
            apps.append(nome_do_app)
    if not apps:
        return "couldn't list the open apps"
    return "open apps: " + ", ".join(apps)


EXEC = {"abrir_app": abrir_app, "fechar_app": fechar_app, "listar_apps_abertos": listar_apps_abertos}
