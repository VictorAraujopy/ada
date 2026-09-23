
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


def existe(cid):
    return bool(_sql("SELECT 1 FROM conversas WHERE id=?", (cid,)))


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


def avaliar(cid, voto, n=None):
    """Grava o feedback (voto: 'up' | 'down' | None limpa) numa fala da ADA.
    Sem n, vale a última fala assistant da conversa (o caso do chat ao vivo)."""
    if n is None:
        r = _sql("SELECT n FROM mensagens WHERE conversa=? AND role='assistant' "
                 "ORDER BY n DESC LIMIT 1", (cid,))
        if not r:
            return False
        n = r[0]["n"]
    r = _sql("SELECT meta FROM mensagens WHERE n=? AND conversa=?", (n, cid))
    if not r:
        return False
    meta = json.loads(r[0]["meta"]) if r[0]["meta"] else {}
    if voto:
        meta["voto"] = voto
    else:
        meta.pop("voto", None)
    _sql("UPDATE mensagens SET meta=? WHERE n=?",
         (json.dumps(meta, ensure_ascii=False), n))
    return True


def apagar(cid):
    _sql("DELETE FROM mensagens WHERE conversa=?", (cid,))
    _sql("DELETE FROM conversas WHERE id=?", (cid,))
