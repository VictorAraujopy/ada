"""
Tools de SISTEMA: hora, status do Mac, volume, brilho, tema, Wi-Fi, bloquear a tela.
Cada funcao recebe os argumentos por nome (**kwargs) e devolve um texto curto.
"""
import re
from datetime import datetime

from ._base import sh, osa

DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def que_horas(**kw):
    a = datetime.now()
    return f"{DIAS[a.weekday()]}, {a.strftime('%d/%m/%Y, %H:%M')}"


def status_mac(**kw):
    batt = sh(["pmset", "-g", "batt"])
    pct = re.search(r"(\d+)%", batt)
    bat = f"bateria {pct.group(1)}%" if pct else "na tomada"
    df = sh(["df", "-h", "/"]).splitlines()
    disco = df[1].split()[3] if len(df) > 1 else "?"
    mfree = re.search(r"free percentage:\s*(\d+)%", sh(["memory_pressure"]))
    ram = f"{mfree.group(1)}% RAM livre" if mfree else "RAM ?"
    return f"{bat} | {ram} | disco livre {disco}"


def ajustar_volume(nivel=None, **kw):
    try:
        n = max(0, min(100, int(float(nivel))))
    except (TypeError, ValueError):
        return f"nivel invalido: {nivel!r}"
    osa(f"set volume output volume {n}")
    return f"volume em {n}%"


def ajustar_brilho(nivel=None, **kw):
    try:
        n = max(0, min(100, int(float(nivel))))
    except (TypeError, ValueError):
        return f"nivel invalido: {nivel!r}"
    r = sh(["brightness", str(round(n / 100, 2))])
    if "not found" in r.lower() or r.startswith("erro"):
        return "preciso do utilitario 'brightness' (brew install brightness)"
    return f"brilho em {n}%"


def mudar_tema(modo=None, **kw):
    m = (modo or "").lower()
    alvo = ("true" if m in ("escuro", "dark", "noturno")
            else "false" if m in ("claro", "light") else "not dark mode")
    osa(f'tell application "System Events" to tell appearance preferences '
        f'to set dark mode to {alvo}')
    return f"tema: {modo or 'alternado'}"


def verificar_wifi(**kw):
    # a interface Wi-Fi varia por Mac (en0/en1...) -> descobre pelo hardware port
    m = re.search(r"Wi-Fi.*?Device:\s*(en\d+)", sh(["networksetup", "-listallhardwareports"]), re.DOTALL)
    iface = m.group(1) if m else "en0"
    return sh(["networksetup", "-getairportnetwork", iface]) or "Wi-Fi: estado desconhecido"


def bloquear_tela(**kw):
    osa('tell application "System Events" to keystroke "q" using {control down, command down}')
    return "tela bloqueada"


EXEC = {
    "que_horas": que_horas, "status_mac": status_mac, "ajustar_volume": ajustar_volume,
    "ajustar_brilho": ajustar_brilho, "mudar_tema": mudar_tema,
    "verificar_wifi": verificar_wifi, "bloquear_tela": bloquear_tela,
}
