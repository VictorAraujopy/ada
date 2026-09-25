"""pesquisar_web: busca no DuckDuckGo e devolve no formato que a ADA viu no treino."""
import re
from urllib.parse import urlparse

from ddgs import DDGS
from ddgs.exceptions import DDGSException

NOMES_PRIVADOS = []
try:
    from personas_local import NOMES_PRIVADOS  # nomes reais ficam no arquivo gitignorado
except ImportError:
    pass

MAX_TRECHO = 160
DADO_PESSOAL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|~/|/Users/")


def _dominio(url):
    return urlparse(url).netloc.removeprefix("www.")


def _limpar(texto):
    texto = " ".join(re.sub(r"<[^>]*>", "", texto).split())
    if len(texto) <= MAX_TRECHO:
        return texto
    return texto[:MAX_TRECHO].rsplit(" ", 1)[0] + "…"


def _vaza_dado_pessoal(consulta):
    palavras = set(re.findall(r"\w+", consulta.lower()))
    return bool(DADO_PESSOAL.search(consulta)) or any(n.lower() in palavras for n in NOMES_PRIVADOS)


def pesquisar_web(consulta=None, **kw):
    consulta = (consulta or "").strip()
    if not consulta:
        return "missing the query"
    if _vaza_dado_pessoal(consulta):
        return "search blocked: the query had personal data"
    try:
        achados = DDGS(timeout=8).text(consulta, region="us-en", max_results=5, backend="duckduckgo")
    except DDGSException as e:
        if "No results found" in str(e):
            return f'no results for "{consulta}"'
        return "error: no connection"

    linhas, vistos = [], set()
    for r in achados:
        dominio, trecho = _dominio(r.get("href", "")), _limpar(r.get("body", ""))
        if dominio and trecho and dominio not in vistos:
            vistos.add(dominio)
            linhas.append(f"• [{dominio}] {trecho}")
        if len(linhas) == 2:
            break
    if not linhas:
        return f'no results for "{consulta}"'
    return f'search results for "{consulta}":\n' + "\n".join(linhas)


EXEC = {"pesquisar_web": pesquisar_web}
