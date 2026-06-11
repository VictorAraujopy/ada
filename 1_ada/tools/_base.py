"""
Helpers compartilhados por todas as tools: rodar comandos do macOS sem nunca explodir.
Erro vira texto (que a ADA le e reporta), em vez de derrubar o programa.
"""
import subprocess


def sh(cmd, timeout=10):
    """Roda um comando do sistema e devolve a saida (stdout, ou stderr se vazio)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr).strip()
    except Exception as e:
        return f"erro: {e}"


def osa(script):
    """Atalho pra rodar um AppleScript (osascript)."""
    return sh(["osascript", "-e", script])


def player():
    """Diz qual app de musica usar: Spotify se estiver aberto, senao Music."""
    aberto = osa('tell application "System Events" to (name of processes) contains "Spotify"')
    return "Spotify" if aberto == "true" else "Music"
