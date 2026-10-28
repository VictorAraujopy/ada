"""pesquisar_wiki: busca por palavra (FTS5) nas wikis de Resident Evil e The Walking Dead do enciclopedia.db local."""
import re
import sqlite3
from pathlib import Path

ENCICLOPEDIA = Path(__file__).resolve().parents[1] / "conhecimento" / "base" / "enciclopedia.db"
WIKIS = ("resident_evil", "walking_dead")
QUANTOS_TRECHOS = 5
MAX_TRECHO = 1000
BUSCA = ("SELECT pagina, secao, texto FROM trechos WHERE trechos MATCH ? AND wiki = ? "
         "ORDER BY bm25(trechos, 0, 10, 10, 1) LIMIT ?")


def _achar(conexao, palavras, ligacao, wiki):
    """Roda a BUSCA com cada palavra entre aspas, ligadas por `ligacao` (" " exige todas, " OR " aceita qualquer uma)."""
    consulta_fts = ligacao.join(f'"{palavra}"' for palavra in palavras)
    return conexao.execute(BUSCA, (consulta_fts, wiki, QUANTOS_TRECHOS)).fetchall()


def pesquisar_wiki(consulta=None, wiki=None, **kw):
    """Devolve os 5 trechos da wiki que mais batem com a consulta: primeiro os que têm todas as palavras, senão qualquer uma."""
    palavras = re.findall(r"\w+", consulta or "")
    if not palavras:
        return "missing the query"
    if wiki not in WIKIS:
        return f"unknown wiki {wiki!r}: use resident_evil or walking_dead"

    conexao = sqlite3.connect(f"file:{ENCICLOPEDIA}?mode=ro", uri=True)
    trechos = _achar(conexao, palavras, " ", wiki)
    if not trechos:
        trechos = _achar(conexao, palavras, " OR ", wiki)
    conexao.close()
    if not trechos:
        return f'nothing in the {wiki} wiki for "{consulta}"'

    linhas = []
    for pagina, secao, texto in trechos:
        titulo = f"{pagina} / {secao}" if secao else pagina
        linhas.append(f"{titulo}: {texto}"[:MAX_TRECHO])
    return f'wiki results for "{consulta}":\n\n' + "\n\n".join(linhas)


EXEC = {"pesquisar_wiki": pesquisar_wiki}
