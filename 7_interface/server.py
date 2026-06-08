"""
Interface web da ADA — SO pra gravar o video do LinkedIn (nao e producao, e descartavel).
Backend minimo: carrega a ADA e streama os eventos (pensar -> tools -> falar) via SSE.

    .venv/bin/python 7_interface/server.py
    # depois abre http://localhost:8000 no navegador

Trocar de versao:  ADA_ADAPTER=ada_v9_9b .venv/bin/python 7_interface/server.py
"""
import json
import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse

from mlx_vlm import load
from mlx_vlm.trainer.utils import apply_lora_layers

RAIZ = Path(__file__).resolve().parent.parent
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "6_assistente"))
import cerebro_tools as ct  # reaproveita o runtime de tools (responder_eventos)

MODELO = "mlx-community/Qwen3.5-9B-MLX-4bit"
ADAPTER = str(RAIZ / "1_modelo" / os.environ.get("ADA_ADAPTER", "ada_v9_9b"))
SYSTEM = "Usuário atual: Victor, seu criador."
GEN = dict(max_tokens=4096, temperature=0.6, top_p=0.9, repetition_penalty=1.05)

print(f"[interface] carregando a ADA ({Path(ADAPTER).name})... (uns 30-60s)")
model, processor = load(MODELO, processor_config={"trust_remote_code": True})
config = model.config.__dict__
model = apply_lora_layers(model, ADAPTER)
print("[interface] PRONTA  ->  abre http://localhost:8000")

app = FastAPI()
historico = [{"role": "system", "content": SYSTEM}]


@app.get("/")
def index():
    return HTMLResponse((AQUI / "index.html").read_text(encoding="utf-8"))


@app.post("/reset")
def reset():
    """Limpa a conversa — util entre os takes da gravacao."""
    global historico
    historico = [{"role": "system", "content": SYSTEM}]
    return {"ok": True}


@app.post("/chat")
async def chat(req: Request):
    msg = (await req.json()).get("msg", "").strip()
    historico.append({"role": "user", "content": msg})

    def stream():
        resposta = ""
        for ev in ct.responder_eventos(model, processor, config, historico, **GEN):
            if ev["t"] == "resp":
                resposta += ev["d"]
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        historico.append({"role": "assistant", "content": resposta.strip()})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
