
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

DB = Path(__file__).resolve().parent / "conversas.db"

_con = sqlite3.connect(DB, check_same_thread=False)
_con.row_factory = sqlite3.Row
_trava = threading.Lock()

with _trava, _con:
    _con.execute("""CREATE TABLE IF NOT EXISTS conversas (
        id TEXT PRIMARY KEY, titulo TEXT, criada REAL, atualizada REAL)""")
    # migração: coluna dono (conversas antigas viram do victor)
    if "dono" not in [c[1] for c in _con.execute("PRAGMA table_info(conversas)")]:
        _con.execute("ALTER TABLE conversas ADD COLUMN dono TEXT DEFAULT 'victor'")
    _con.execute("""CREATE TABLE IF NOT EXISTS mensagens (
        n INTEGER PRIMARY KEY AUTOINCREMENT, conversa TEXT NOT NULL,
        role TEXT NOT NULL, content TEXT NOT NULL, meta TEXT, criada REAL)""")


def _sql(query, args=()):
    with _trava, _con:
        return _con.execute(query, args).fetchall()


def criar(primeira_msg, dono="victor"):
    """Cria a conversa (título = primeira mensagem encurtada) já com dono."""
    titulo = " ".join((primeira_msg or "conversa").split())
    if len(titulo) > 46:
        titulo = titulo[:46].rstrip() + "…"
    cid = uuid.uuid4().hex[:12]
    agora = time.time()
    _sql("INSERT INTO conversas VALUES (?,?,?,?,?)", (cid, titulo, agora, agora, dono))
    return {"id": cid, "titulo": titulo}


def listar(dono="victor"):
    """Só as conversas do dono — cada pessoa vê a própria sidebar."""
    rs = _sql("""SELECT c.id, c.titulo, c.atualizada,
                 (SELECT COUNT(*) FROM mensagens m WHERE m.conversa = c.id) AS n
                 FROM conversas c WHERE c.dono = ? ORDER BY c.atualizada DESC""", (dono,))
    return [dict(r) for r in rs]


def listar_todas():
    """Todas as conversas, com dono — pro log no terminal."""
    rs = _sql("""SELECT c.id, c.dono, c.titulo, c.atualizada,
                 (SELECT COUNT(*) FROM mensagens m WHERE m.conversa = c.id) AS n
                 FROM conversas c ORDER BY c.atualizada DESC""")
    return [dict(r) for r in rs]


def existe(cid, dono):
    """A conversa existe e é desse dono."""
    return bool(_sql("SELECT 1 FROM conversas WHERE id=? AND dono=?", (cid, dono)))


def titulo(cid):
    r = _sql("SELECT titulo FROM conversas WHERE id=?", (cid,))
    return r[0]["titulo"] if r else None


def mensagens(cid):
    rs = _sql("SELECT n, role, content, meta FROM mensagens WHERE conversa=? ORDER BY n", (cid,))
    return [{"n": r["n"], "role": r["role"], "content": r["content"],
             "meta": json.loads(r["meta"]) if r["meta"] else None} for r in rs]


def gravar(cid, role, content, meta=None):
    _sql("INSERT INTO mensagens (conversa, role, content, meta, criada) VALUES (?,?,?,?,?)",
         (cid, role, content,
          json.dumps(meta, ensure_ascii=False) if meta else None, time.time()))
    _sql("UPDATE conversas SET atualizada=? WHERE id=?", (time.time(), cid))


def renomear(cid, novo):
    novo = " ".join((novo or "").split())[:60]
    if novo:
        _sql("UPDATE conversas SET titulo=? WHERE id=?", (novo, cid))
    return novo


def apagar(cid):
    _sql("DELETE FROM mensagens WHERE conversa=?", (cid,))
    _sql("DELETE FROM conversas WHERE id=?", (cid,))


if __name__ == "__main__":
    # log no terminal: sem argumento lista todas; com o id, mostra a conversa inteira
    import sys

    if len(sys.argv) < 2:
        for c in listar_todas():
            quando = time.strftime("%d/%m %H:%M", time.localtime(c["atualizada"]))
            print(f"{c['dono']:<10} {c['id']}  {quando}  {c['n']:>3} msgs  {c['titulo']}")
    elif not titulo(sys.argv[1]):
        sys.exit("conversa não existe")
    else:
        print(f"# {titulo(sys.argv[1])}\n")
        for m in mensagens(sys.argv[1]):
            for t in (m["meta"] or {}).get("tools", []):
                print(f"  🔧 {t['nome']} → {t['res']}")
            print(f"{'ADA' if m['role'] == 'assistant' else 'user'}: {m['content']}\n")
