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

# TOOLS MOCKADAS: o modelo decide e "executa" normalmente, mas o resultado é
# enlatado e DETERMINÍSTICO — os dois modelos veem o mesmo mundo (comparação
# justa) e nada roda de verdade no Mac (sem app abrindo, sem volume mudando).
MOCKS = {
    "que_horas": "quinta, 11/06/2026, 14:30",
    "status_mac": "bateria 76% | 52% RAM livre | disco livre 31Gi",
    "abrir_app": lambda a: f"abrindo {a.get('nome', '?')}",
    "fechar_app": lambda a: f"fechei {a.get('nome', '?')}",
    "listar_apps_abertos": "abertos: Finder, Safari, Music, Terminal",
    "tocar_musica": "tocando: The Man Comes Around — Johnny Cash",
    "pausar_musica": "música pausada",
    "proxima_musica": "pulei: agora tocando Hurt — Johnny Cash",
    "ajustar_volume": lambda a: f"volume em {a.get('nivel', '?')}%",
    "ajustar_brilho": lambda a: f"brilho em {a.get('nivel', '?')}%",
    "mudar_tema": lambda a: f"tema: {a.get('modo', 'alternado')}",
    "tirar_screenshot": "screenshot em /Users/victordev/Desktop/screenshot_143000.png",
    "buscar_arquivo": lambda a: f"achei:\n/Users/victordev/Documents/{a.get('nome', 'arquivo')}.pdf",
    "criar_lembrete": lambda a: f"lembrete criado: {a.get('texto', '?')}",
    "definir_alarme": "alarme definido",
    "listar_lembretes": "1. ligar pro dentista às 16h",
    "verificar_wifi": "Current Wi-Fi Network: CasaVictor_5G",
    "bloquear_tela": "tela bloqueada",
    "esvaziar_lixeira": "esvaziar_lixeira está desarmada por segurança",
}

def _executar_mock(nome, args):
    m = MOCKS.get(nome)
    if m is None:
        return f"tool '{nome}' ainda nao implementada"
    return m(args) if callable(m) else m

cerebro.executar = _executar_mock   # o runtime real fica intocado; só aqui é dublê

perguntas = [json.loads(l) for l in open(AQUI / "perguntas.jsonl", encoding="utf-8")]
nome = Path(cerebro.ADAPTER).name
print(f"[bench] {nome} — {len(perguntas)} perguntas, tools MOCKADAS (~1h-1h30)")
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
    print(f"  {p['id']:03d}/{len(perguntas)} [{p['cat']}] {resultados[-1]['segundos']}s"
          + (f" tools={resultados[-1]['tools']}" if resultados[-1]["tools"] else ""))
    # salva incremental: se cair no meio, o que rodou tá salvo
    (AQUI / "resultados" / f"bench_{nome}.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"[bench] pronto em {(time.time()-t_ini)/60:.0f}min -> resultados/bench_{nome}.json")
