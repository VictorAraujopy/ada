from ._base import sh, osa


def abrir_app(nome=None, **kw):
    if not nome:
        return "missing the app name"
    return f"couldn't find '{nome}'" if sh(["open", "-a", nome]) else f"{nome} opened"


def fechar_app(nome=None, **kw):
    if not nome:
        return "missing the app name"
    osa(f'tell application "{nome}" to quit')
    return f"{nome} closed"


def listar_apps_abertos(**kw):
    r = osa('tell application "System Events" to get name of '
            '(processes where background only is false)')
    apps = [a.strip() for a in r.split(",") if a.strip()]
    return "open apps: " + ", ".join(apps[:12])


EXEC = {"abrir_app": abrir_app, "fechar_app": fechar_app, "listar_apps_abertos": listar_apps_abertos}
