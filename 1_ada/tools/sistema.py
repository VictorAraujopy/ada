import re
from datetime import datetime

from ._base import sh, osa

DIAS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def que_horas(**kw):
    a = datetime.now()
    return f"{a.strftime('%Y-%m-%d %H:%M')}, {DIAS[a.weekday()]}"


def status_mac(**kw):
    batt = sh(["pmset", "-g", "batt"])
    pct = re.search(r"(\d+)%", batt)
    bat = f"battery {pct.group(1)}%" if pct else "plugged in"
    df = sh(["df", "-h", "/"]).splitlines()
    disco = df[1].split()[3] if len(df) > 1 else "?"
    mfree = re.search(r"free percentage:\s*(\d+)%", sh(["memory_pressure"]))
    ram = f"{mfree.group(1)}% RAM free" if mfree else "RAM ?"
    return f"{bat} | {ram} | {disco} disk free"


def ajustar_volume(nivel=None, **kw):
    try:
        n = max(0, min(100, int(float(nivel))))
    except (TypeError, ValueError):
        return f"invalid level: {nivel!r}"
    osa(f"set volume output volume {n}")
    return f"volume at {n}%"


def ajustar_brilho(nivel=None, **kw):
    try:
        n = max(0, min(100, int(float(nivel))))
    except (TypeError, ValueError):
        return f"invalid level: {nivel!r}"
    r = sh(["brightness", str(round(n / 100, 2))])
    if "not found" in r.lower() or r.startswith("erro"):
        return "I need the 'brightness' utility (brew install brightness)"
    return f"brightness at {n}%"


def mudar_tema(modo=None, **kw):
    m = (modo or "").lower()
    alvo = ("true" if m in ("escuro", "dark", "noturno")
            else "false" if m in ("claro", "light") else "not dark mode")
    osa(f'tell application "System Events" to tell appearance preferences '
        f'to set dark mode to {alvo}')
    return f"theme: {modo or 'toggled'}"


def verificar_wifi(**kw):
    # a interface Wi-Fi varia por Mac (en0/en1...) -> descobre pelo hardware port
    m = re.search(r"Wi-Fi.*?Device:\s*(en\d+)", sh(["networksetup", "-listallhardwareports"]), re.DOTALL)
    iface = m.group(1) if m else "en0"
    return sh(["networksetup", "-getairportnetwork", iface]) or "Wi-Fi: unknown state"


def bloquear_tela(**kw):
    osa('tell application "System Events" to keystroke "q" using {control down, command down}')
    return "screen locked"


EXEC = {
    "que_horas": que_horas, "status_mac": status_mac, "ajustar_volume": ajustar_volume,
    "ajustar_brilho": ajustar_brilho, "mudar_tema": mudar_tema,
    "verificar_wifi": verificar_wifi, "bloquear_tela": bloquear_tela,
}
