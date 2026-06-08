"""
Diz se a permissão de Acessibilidade está ATIVA pra este processo — é o que o
pynput precisa pra capturar o botão do mouse e o Ctrl+L globalmente. Sem ela,
nada do gatilho funciona (foi o 'not trusted' que apareceu no teste do mouse).

    .venv/bin/python 6_assistente/checa_permissao.py

Mostra SIM/NÃO e QUAL app você precisa liberar (sobe a árvore até achar o .app).
"""
import ctypes
import os
import subprocess
import sys
from ctypes import util

fw = ctypes.cdll.LoadLibrary(util.find_library("ApplicationServices"))
fw.AXIsProcessTrusted.restype = ctypes.c_bool
trusted = bool(fw.AXIsProcessTrusted())

print(f"\n  Acessibilidade ativa pra este processo?   {'SIM ✓' if trusted else 'NÃO ✗'}\n")


def comm(pid):
    return subprocess.run(["ps", "-o", "comm=", "-p", str(pid)],
                          capture_output=True, text=True).stdout.strip()


def ppid(pid):
    try:
        return int(subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                                  capture_output=True, text=True).stdout.strip())
    except Exception:
        return 0


pid, cadeia, app = os.getpid(), [], None
for _ in range(15):
    c = comm(pid)
    cadeia.append(c)
    if ".app/" in c and app is None:
        app = c.split(".app/")[0].split("/")[-1] + ".app"
    pid = ppid(pid)
    if pid <= 1:
        break

print("  cadeia de processos (de baixo pra cima):")
for c in cadeia:
    print(f"    {c}")

if not trusted:
    print(f"\n  >> O app a liberar é: {app or 'o teu app de terminal'}")
    print("     1. System Settings > Privacy & Security > Accessibility")
    print(f"     2. Ligue '{app or 'o terminal'}' (se não estiver na lista, '+' e adicione).")
    print("     3. FECHE e REABRA esse app — só vale depois de reiniciar.")
    print("     4. Rode este teste de novo: tem que dizer SIM.")
else:
    print("\n  >> Perfeito. O gatilho do mouse e o Ctrl+L vão funcionar daqui.")
