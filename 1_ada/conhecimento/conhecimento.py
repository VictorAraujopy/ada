from pathlib import Path

BASE = Path(__file__).resolve().parent / "base"


def carregar_conhecimento():
    """Lê todas as fichas da base e devolve um bloco pro system prompt (ou '' se vazia)."""
    fichas = sorted(BASE.glob("*.md"))
    if not fichas:
        return ""
    corpo = "\n\n---\n\n".join(f.read_text(encoding="utf-8").strip() for f in fichas)
    return (
        "## KNOWLEDGE BASE (reliable facts)\n"
        "Use the facts below when they're relevant. Do NOT make things up beyond this: if something "
        "isn't here and you're not sure, say you don't know. The rule works both ways: what IS "
        "written here (or anywhere in this system) you KNOW for sure — using it isn't making "
        "things up, and denying you know it is wrong.\n\n"
        + corpo
    )


if __name__ == "__main__":
    print(carregar_conhecimento())
