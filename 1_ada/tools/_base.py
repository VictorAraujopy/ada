"""O que as tools usam pra falar com o Mac: shell e AppleScript."""
import subprocess


def sh(cmd, timeout=10):
    """Roda um comando do sistema e devolve a saida (stdout, ou stderr se vazio)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr).strip()
    except Exception as e:
        return f"error: {e}"


def osa(script):
    """Atalho pra rodar um AppleScript (osascript)."""
    return sh(["osascript", "-e", script])
