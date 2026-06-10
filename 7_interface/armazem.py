"""
Armazenamento das conversas da interface — SQLite local (7_interface/conversas.db).

Duas tabelas:
  conversas — id, título (1ª mensagem encurtada), criada/atualizada
  mensagens — role + content (o que vai pro modelo) e um meta JSON só do
              assistant (tools usadas, tempos, raciocínio) pra UI restaurar
              a tela fielmente depois de um F5 ou reinício.

Uma conexão única + lock: os endpoints rodam em threads do pool do Starlette,
e o SQLite não gosta de conexão compartilhada sem proteção.
"""
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
    _con.execute("""CREATE TABLE IF NOT EXISTS mensagens (
        n INTEGER PRIMARY KEY AUTOINCREMENT, conversa TEXT NOT NULL,
        role TEXT NOT NULL, content TEXT NOT NULL, meta TEXT, criada REAL)""")


def _sql(query, args=()):
    with _trava, _con:
        return _con.execute(query, args).fetchall()


def criar(primeira_msg):
    """Cria a conversa; o título é a primeira mensagem, encurtada."""
    titulo = " ".join((primeira_msg or "conversa").split())
    if len(titulo) > 46:
        titulo = titulo[:46].rstrip() + "…"
    cid = uuid.uuid4().hex[:12]
    agora = time.time()
    _sql("INSERT INTO conversas VALUES (?,?,?,?)", (cid, titulo, agora, agora))
    return {"id": cid, "titulo": titulo}


def listar():
    rs = _sql("""SELECT c.id, c.titulo, c.atualizada,
                 (SELECT COUNT(*) FROM mensagens m WHERE m.conversa = c.id) AS n
                 FROM conversas c ORDER BY c.atualizada DESC""")
    return [dict(r) for r in rs]


def existe(cid):
    return bool(_sql("SELECT 1 FROM conversas WHERE id=?", (cid,)))


def titulo(cid):
    r = _sql("SELECT titulo FROM conversas WHERE id=?", (cid,))
    return r[0]["titulo"] if r else None


def mensagens(cid):
    rs = _sql("SELECT role, content, meta FROM mensagens WHERE conversa=? ORDER BY n", (cid,))
    return [{"role": r["role"], "content": r["content"],
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
