"""
Base de conhecimento da ADA (RAG).

Lê as fichas .md de 1_ada/conhecimento/base/ e monta o bloco de contexto que entra no
system prompt do chat. Assim a ADA responde fato com base na FICHA, não na memória
dos pesos (onde ela alucina).

Por enquanto é RAG SIMPLES: injeta a base INTEIRA no contexto (a base é pequena).
Quando crescer demais pra caber no contexto, é AQUI que entra a busca semântica
(embeddings) pra pescar só os trechos relevantes de cada pergunta.

Uso:
    from conhecimento import carregar_conhecimento
    bloco = carregar_conhecimento()   # texto pra concatenar no system prompt
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent / "base"


def carregar_conhecimento():
    """Lê todas as fichas da base e devolve um bloco pro system prompt (ou '' se vazia)."""
    fichas = sorted(BASE.glob("*.md"))
    if not fichas:
        return ""
    corpo = "\n\n---\n\n".join(f.read_text(encoding="utf-8").strip() for f in fichas)
    return (
        "## BASE DE CONHECIMENTO (fatos confiáveis)\n"
        "Use os fatos abaixo quando forem relevantes. NÃO invente fora disto: se algo "
        "não está aqui e você não tem certeza, diga que não sabe.\n\n"
        + corpo
    )


if __name__ == "__main__":
    print(carregar_conhecimento())
