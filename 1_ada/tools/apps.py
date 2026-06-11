"""Tools de APPS: abrir, fechar e listar os aplicativos abertos."""
from ._base import sh, osa


def abrir_app(nome=None, **kw):
    if not nome:
        return "faltou o nome do app"
    return f"nao achei '{nome}'" if sh(["open", "-a", nome]) else f"abrindo {nome}"


def fechar_app(nome=None, **kw):
    if not nome:
        return "faltou o nome do app"
    osa(f'tell application "{nome}" to quit')
    return f"fechei {nome}"


def listar_apps_abertos(**kw):
    r = osa('tell application "System Events" to get name of '
            '(processes where background only is false)')
    apps = [a.strip() for a in r.split(",") if a.strip()]
    return "abertos: " + ", ".join(apps[:12])


EXEC = {"abrir_app": abrir_app, "fechar_app": fechar_app, "listar_apps_abertos": listar_apps_abertos}
