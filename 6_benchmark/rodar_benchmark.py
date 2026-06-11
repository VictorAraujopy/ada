"""
Roda as 50 perguntas do benchmark num adapter e salva as respostas BRUTAS.
(O harness: perguntas fixas, condições fixas — só o adapter muda entre rodadas.)

    ADA_ADAPTER=ada_v10_9b      .venv/bin/python 6_benchmark/rodar_benchmark.py
    ADA_ADAPTER=ada_v11b_a16_9b .venv/bin/python 6_benchmark/rodar_benchmark.py

Sai bench_<adapter>.json nesta pasta. Cada pergunta roda em conversa limpa,
com o system real de produção (cerebro.SYSTEM) e tools ativas.
"""
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "1_ada"))
import cerebro

perguntas = [json.loads(l) for l in open(AQUI / "perguntas.jsonl", encoding="utf-8")]
nome = Path(cerebro.ADAPTER).name
print(f"[bench] {nome} — 50 perguntas (~30-40min)")
(AQUI / "resultados").mkdir(exist_ok=True)
model, processor, config = cerebro.carregar()

resultados, t_ini = [], time.time()
for p in perguntas:
    t0 = time.time()
    resposta, passos = cerebro.responder(
        model, processor, config,
        [{"role": "system", "content": cerebro.SYSTEM},
         {"role": "user", "content": p["q"]}],
        **cerebro.GEN)
    resultados.append({"id": p["id"], "cat": p["cat"], "q": p["q"],
                       "resposta": resposta,
                       "tools": [nome_t for nome_t, _, _ in (passos or [])],
                       "segundos": round(time.time() - t0, 1)})
    print(f"  {p['id']:02d}/50 [{p['cat']}] {resultados[-1]['segundos']}s"
          + (f" tools={resultados[-1]['tools']}" if resultados[-1]["tools"] else ""))
    # salva incremental: se cair no meio, o que rodou tá salvo
    (AQUI / "resultados" / f"bench_{nome}.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"[bench] pronto em {(time.time()-t_ini)/60:.0f}min -> resultados/bench_{nome}.json")
