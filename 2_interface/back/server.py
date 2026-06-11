"""
Interface web da ADA — backend.

Arquitetura: o MLX precisa de UMA thread dona do modelo, então um worker único
consome uma fila de jobs. Cada POST /chat vira um job com a SUA fila de saída —
o endpoint streama os eventos dela via SSE, e conversas não se misturam.

As conversas vivem no SQLite (armazem.py): sobrevivem a F5 e a reinício do
servidor. O histórico que vai pro modelo é remontado do banco a cada turno.

O cérebro é caixa-preta aqui: tudo passa por cerebro.responder_eventos().

Rodar:
    .venv/bin/python 2_interface/back/server.py        # abre http://localhost:8000
Trocar de versão:   ADA_ADAPTER=ada_v9_9b .venv/bin/python 2_interface/back/server.py
Testar a interface SEM carregar o 9B (eventos de mentira, resposta na hora):
    ADA_FAKE=1 .venv/bin/python 2_interface/back/server.py
"""
import json
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import armazem

RAIZ = Path(__file__).resolve().parent.parent.parent
AQUI = Path(__file__).resolve().parent
FRONT = AQUI.parent / "front"
sys.path.insert(0, str(RAIZ / "1_ada"))

FAKE = os.environ.get("ADA_FAKE") == "1"

# Config, system prompt e params de geração vivem TODOS no núcleo (1_ada/cerebro.py).
# Aqui o backend só importa e repassa. No modo FAKE o núcleo nem é carregado (sem MLX), então
# o SYSTEM fica vazio (os eventos de mentira ignoram); o worker o preenche ao carregar de verdade.
ADAPTER = str(RAIZ / "_modelo" / os.environ.get("ADA_ADAPTER", "ada_v11_a16_9b"))  # só pro /info
SYSTEM = ""  # preenchido pelo worker com cerebro.SYSTEM quando o modelo carrega


@dataclass
class Job:
    historico: list                                          # snapshot da conversa
    saida: queue.Queue = field(default_factory=queue.Queue)  # eventos só deste job


jobs = queue.Queue()
pronta = threading.Event()


def _eventos_fake(historico):
    """Eventos de mentira (think -> tool -> resp) pra testar a UI sem o 9B."""
    msg = historico[-1]["content"]
    pensamento = (f'O Victor mandou "{msg}". Modo fake ligado, então eu não penso de '
                  f'verdade — só finjo bem. Vou fingir uma tool também. ')
    for palavra in pensamento.split(" "):
        time.sleep(0.03)
        yield {"t": "think", "d": palavra + " "}
    yield {"t": "tool", "nome": "que_horas", "args": {}, "res": "segunda, 09/06/2026, 16:20"}
    resposta = ("Interface de ponta a ponta, com **negrito**, `código` e\n"
                "- até lista\n- funcionando.\n\nQuando for pra valer, tira o ADA_FAKE=1. ")
    for palavra in resposta.split(" "):
        time.sleep(0.04)
        yield {"t": "resp", "d": palavra + " "}
    yield {"t": "fim"}


def worker():
    """Thread única dona do modelo: carrega uma vez e processa um job por vez."""
    global SYSTEM
    if FAKE:
        gerar = _eventos_fake
        print("[interface] MODO FAKE — sem modelo, eventos de mentira")
    else:
        import cerebro  # núcleo da ADA (só carrega o MLX fora do modo FAKE)

        SYSTEM = cerebro.SYSTEM
        print(f"[interface] carregando a ADA ({Path(cerebro.ADAPTER).name})... (uns 30-60s)")
        model, processor, config = cerebro.carregar()

        def gerar(historico):
            return cerebro.responder_eventos(model, processor, config, historico, **cerebro.GEN)

    pronta.set()
    print("[interface] PRONTA  ->  http://localhost:8000")

    while True:
        job = jobs.get()
        try:
            for ev in gerar(job.historico):
                job.saida.put(ev)
        except Exception as e:
            job.saida.put({"t": "erro", "d": f"{type(e).__name__}: {e}"})
        finally:
            job.saida.put(None)   # sinal de fim pro endpoint, aconteça o que acontecer


app = FastAPI()
app.mount("/static", StaticFiles(directory=FRONT), name="static")
threading.Thread(target=worker, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(FRONT / "index.html")


@app.get("/info")
def info():
    """A UI consulta isto pra saber se já pode liberar o input."""
    return {"pronta": pronta.is_set(), "adapter": Path(ADAPTER).name,
            "fake": FAKE, "fila": jobs.qsize()}


@app.get("/conversas")
def conversas():
    return armazem.listar()


@app.post("/conversas")
async def criar_conversa(req: Request):
    corpo = await req.json()
    return armazem.criar(corpo.get("titulo", ""))


@app.get("/conversas/{cid}")
def abrir_conversa(cid: str):
    if not armazem.existe(cid):
        return JSONResponse({"erro": "conversa não existe"}, status_code=404)
    return {"id": cid, "titulo": armazem.titulo(cid), "mensagens": armazem.mensagens(cid)}


@app.patch("/conversas/{cid}")
async def renomear_conversa(cid: str, req: Request):
    if not armazem.existe(cid):
        return JSONResponse({"erro": "conversa não existe"}, status_code=404)
    novo = armazem.renomear(cid, (await req.json()).get("titulo", ""))
    if not novo:
        return JSONResponse({"erro": "título vazio"}, status_code=400)
    return {"ok": True, "titulo": novo}


@app.delete("/conversas/{cid}")
def apagar_conversa(cid: str):
    armazem.apagar(cid)
    return {"ok": True}


@app.get("/conversas/{cid}/export")
def exportar(cid: str):
    """Baixa a conversa em markdown (pra post, demo, arquivo)."""
    if not armazem.existe(cid):
        return JSONResponse({"erro": "conversa não existe"}, status_code=404)
    linhas = [f"# ADA — {armazem.titulo(cid)}", ""]
    for m in armazem.mensagens(cid):
        if m["role"] == "user":
            linhas += [f"**Victor:** {m['content']}", ""]
        else:
            for t in (m["meta"] or {}).get("tools", []):
                linhas.append(f"> 🔧 `{t['nome']}` → {t['res']}")
            linhas += [f"**ADA:** {m['content']}", ""]
    return Response("\n".join(linhas), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="ada_{cid}.md"'})


@app.post("/chat")
async def chat(req: Request):
    corpo = await req.json()
    cid = corpo.get("conversa", "")
    msg = (corpo.get("msg") or "").strip()
    if not msg or not armazem.existe(cid):
        return JSONResponse({"erro": "faltou msg ou a conversa não existe"}, status_code=400)
    if not pronta.is_set():
        return JSONResponse({"erro": "a ADA ainda está carregando"}, status_code=503)

    armazem.gravar(cid, "user", msg)
    # o histórico do modelo é remontado do banco: system + turnos (sem os metas)
    historico = ([{"role": "system", "content": SYSTEM}] +
                 [{"role": m["role"], "content": m["content"]} for m in armazem.mensagens(cid)])
    job = Job(historico=historico)
    jobs.put(job)

    def stream():
        resposta, think, tools = "", "", []
        t0, t_resp = time.time(), None
        while True:
            ev = job.saida.get()
            if ev is None:
                break
            if ev["t"] == "think":
                think += ev["d"]
            elif ev["t"] == "tool":
                tools.append({"nome": ev["nome"], "res": str(ev["res"])[:200]})
            elif ev["t"] == "resp":
                t_resp = t_resp or time.time()
                resposta += ev["d"]
            yield f"data: {json.dumps(ev)}\n\n"
        if resposta.strip():   # só entra na memória da conversa se chegou inteira
            meta = {"pensou_s": round((t_resp or time.time()) - t0, 1),
                    "respondeu_s": round(time.time() - (t_resp or time.time()), 1),
                    "tools": tools, "think": think.strip()}
            armazem.gravar(cid, "assistant", resposta.strip(), meta)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("ADA_PORT", 8000)),
                log_level="warning")
