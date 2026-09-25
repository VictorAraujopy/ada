"""
Interface web da ADA — backend.

Arquitetura: o modelo tem UMA thread dona (o worker), que tira os pedidos da
fila `entrada` um por vez. Cada POST /chat vira um Job com a SUA fila de saída —
o endpoint streama os eventos dela via SSE, e conversas não se misturam.

As conversas vivem no SQLite (armazem.py): sobrevivem a F5 e a reinício do
servidor. O histórico que vai pro modelo é remontado do banco a cada turno.

Identidade por IP, sem login: os IPs do .env (ADA_IPS_VICTOR / ADA_IPS_CONVIDADO)
escolhem a persona e o dono das conversas; qualquer outro IP é visitante. Cada
um só vê e mexe nas próprias conversas.

O cérebro é caixa-preta aqui: tudo passa por cerebro.responder_eventos().

Rodar:
    .venv/bin/python 2_interface/back/server.py                              # só esta máquina
    ADA_HOST=$(tailscale ip -4) .venv/bin/python 2_interface/back/server.py  # tailnet
Testar a interface SEM carregar o modelo (eventos de mentira, resposta na hora):
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
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import armazem

RAIZ = Path(__file__).resolve().parent.parent.parent
AQUI = Path(__file__).resolve().parent
FRONT = AQUI.parent / "front"
sys.path.insert(0, str(RAIZ / "1_ada"))
load_dotenv(RAIZ / ".env")  # não sobrescreve variável que já veio do terminal

FAKE = os.environ.get("ADA_FAKE") == "1"

# ADA_HOST: 127.0.0.1 (so esta maquina) | IP do Tailscale (so a tailnet — modo convidado)
# NUNCA use 0.0.0.0 sem firewall: exporia a ADA pra rede local inteira.
# `or`: ADA_HOST vazio (ex.: $(tailscale ip) que falhou) NUNCA pode virar 0.0.0.0
HOST = os.environ.get("ADA_HOST") or "127.0.0.1"
PORTA = int(os.environ.get("ADA_PORT", 8000))
URL = f"http://{HOST}:{PORTA}"

# Config, system prompt e params de geração vivem TODOS no núcleo (1_ada/cerebro.py).
# Aqui o backend só importa e repassa. No modo FAKE o núcleo nem é carregado (sem o modelo), então
# o SYSTEM fica vazio (os eventos de mentira ignoram); o worker o preenche ao carregar de verdade.
# só pro /info — mesmo nome que o cerebro.py usa (ADA_ADAPTER="" roda o 27B cru)
ADAPTER = os.environ.get("ADA_ADAPTER", "ada_v12_1_en_a16_27b") or "qwen3.8_27b_cru"
SYSTEMS = {"victor": "", "convidado": "", "visitante": ""}  # preenchidos pelo worker quando o modelo carrega


def _ips(var):
    return {ip.strip() for ip in os.environ.get(var, "").split(",") if ip.strip()}


# Identidade por origem: IPs do Victor = victor; IPs do convidado (.env) = convidado; resto = visitante.
IPS_VICTOR = ({"127.0.0.1", "::1"}
              # o IP que o PRÓPRIO servidor escuta: requisição da máquina pra ela mesma = Victor
              | ({os.environ["ADA_HOST"]} if os.environ.get("ADA_HOST") else set())
              | _ips("ADA_IPS_VICTOR"))
IPS_CONVIDADO = _ips("ADA_IPS_CONVIDADO") - IPS_VICTOR


def usuario_de(req: Request) -> str:
    ip = req.client.host if req.client else ""
    if ip in IPS_VICTOR:
        return "victor"
    return "convidado" if ip in IPS_CONVIDADO else "visitante"


@dataclass
class Job:
    historico: list                                          # snapshot da conversa
    saida: queue.Queue = field(default_factory=queue.Queue)  # eventos só deste job


entrada = queue.Queue()
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
    global SYSTEMS
    if FAKE:
        gerar = _eventos_fake
        print("[interface] MODO FAKE — sem modelo, eventos de mentira")
    else:
        import cerebro  # núcleo da ADA (só carrega o modelo fora do modo FAKE)

        SYSTEMS["victor"] = cerebro.SYSTEM
        SYSTEMS["convidado"] = cerebro.SYSTEM_CONVIDADO
        SYSTEMS["visitante"] = cerebro.SYSTEM_VISITANTE
        print(f"[interface] carregando a ADA ({Path(cerebro.ADAPTER).name})... (uns 30-60s)")
        model, processor, config = cerebro.carregar()

        def gerar(historico):
            return cerebro.responder_eventos(model, processor, config, historico, **cerebro.GEN)

    pronta.set()
    print(f"[interface] PRONTA  ->  {URL}")

    while True:
        job = entrada.get()
        try:
            for ev in gerar(job.historico):
                job.saida.put(ev)
        except Exception as e:
            job.saida.put({"t": "erro", "d": f"{type(e).__name__}: {e}"})
        finally:
            job.saida.put(None)   # sinal de fim pro endpoint, aconteça o que acontecer


app = FastAPI()
app.mount("/static", StaticFiles(directory=FRONT), name="static")
print(f"[interface] victor: {sorted(IPS_VICTOR)} | convidado: {sorted(IPS_CONVIDADO)} | resto = visitante")
threading.Thread(target=worker, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(FRONT / "index.html")


@app.get("/info")
def info(req: Request):
    """A UI consulta isto pra saber se já pode liberar o input."""
    return {"pronta": pronta.is_set(), "adapter": Path(ADAPTER).name,
            "fake": FAKE, "fila": entrada.qsize(),
            "usuario": usuario_de(req), "origem": req.client.host if req.client else "?"}


@app.get("/conversas")
def conversas(req: Request):
    return armazem.listar(usuario_de(req))


@app.post("/conversas")
async def criar_conversa(req: Request):
    corpo = await req.json()
    return armazem.criar(corpo.get("titulo", ""), dono=usuario_de(req))


@app.get("/conversas/{cid}")
def abrir_conversa(cid: str, req: Request):
    if not armazem.existe(cid, usuario_de(req)):
        return JSONResponse({"erro": "conversa não existe"}, status_code=404)
    return {"id": cid, "titulo": armazem.titulo(cid), "mensagens": armazem.mensagens(cid)}


@app.patch("/conversas/{cid}")
async def renomear_conversa(cid: str, req: Request):
    if not armazem.existe(cid, usuario_de(req)):
        return JSONResponse({"erro": "conversa não existe"}, status_code=404)
    novo = armazem.renomear(cid, (await req.json()).get("titulo", ""))
    if not novo:
        return JSONResponse({"erro": "título vazio"}, status_code=400)
    return {"ok": True, "titulo": novo}


@app.delete("/conversas/{cid}")
def apagar_conversa(cid: str, req: Request):
    if not armazem.existe(cid, usuario_de(req)):
        return JSONResponse({"erro": "conversa não existe"}, status_code=404)
    armazem.apagar(cid)
    return {"ok": True}


@app.get("/conversas/{cid}/export")
def exportar(cid: str, req: Request):
    """Baixa a conversa em markdown (pra post, demo, arquivo)."""
    if not armazem.existe(cid, usuario_de(req)):
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
    if not msg or not armazem.existe(cid, usuario_de(req)):
        return JSONResponse({"erro": "faltou msg ou a conversa não existe"}, status_code=400)
    if not pronta.is_set():
        return JSONResponse({"erro": "a ADA ainda está carregando"}, status_code=503)

    armazem.gravar(cid, "user", msg)
    # o histórico do modelo é remontado do banco: system DO USUÁRIO + turnos
    historico = ([{"role": "system", "content": SYSTEMS[usuario_de(req)]}] +
                 [{"role": m["role"], "content": m["content"]} for m in armazem.mensagens(cid)])
    job = Job(historico=historico)
    entrada.put(job)

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
    print(f"[interface] escutando em {URL}")
    uvicorn.run(app, host=HOST, port=PORTA, log_level="warning")
