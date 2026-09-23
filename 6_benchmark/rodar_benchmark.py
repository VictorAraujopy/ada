
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "1_ada"))
import cerebro

# TOOLS MOCKADAS: o modelo decide e "executa" normalmente, mas o resultado é
# enlatado e DETERMINÍSTICO — nada roda de verdade no Mac (sem app abrindo, sem volume
# mudando). É o mesmo mundo da old/benchmark.py (ADA antiga), só que em inglês, no
# estilo das tools reais da ADA 27B.
MOCKS = {
    "que_horas": "2026-06-11 14:30, Thursday",
    "status_mac": "battery 76% | 52% RAM free | 31Gi disk free",
    "abrir_app": lambda a: f"{a.get('nome', '?')} opened",
    "fechar_app": lambda a: f"{a.get('nome', '?')} closed",
    "listar_apps_abertos": "open apps: Finder, Safari, Music, Terminal",
    "tocar_musica": "playing: The Man Comes Around — Johnny Cash",
    "pausar_musica": "playback paused",
    "proxima_musica": "next track: Hurt — Johnny Cash",
    "ajustar_volume": lambda a: f"volume at {a.get('nivel', '?')}%",
    "ajustar_brilho": lambda a: f"brightness at {a.get('nivel', '?')}%",
    "mudar_tema": lambda a: f"theme: {a.get('modo', 'toggled')}",
    "tirar_screenshot": "screenshot at ~/Desktop/screenshot_143000.png",
    "buscar_arquivo": lambda a: f"found:\n~/Documents/{a.get('nome', 'file')}.pdf",
    "criar_lembrete": lambda a: f"reminder created: {a.get('texto', '?')}",
    "definir_alarme": "alarm set",
    "listar_lembretes": "reminders: call the dentist at 4pm",
    "verificar_wifi": "Current Wi-Fi Network: Home_5G",
    "bloquear_tela": "screen locked",
    "esvaziar_lixeira": "emptying the trash isn't enabled yet (destructive action, confirmation step missing)",
}

def _executar_mock(nome, args):
    m = MOCKS.get(nome)
    if m is None:
        return f"tool '{nome}' not implemented yet"
    return m(args) if callable(m) else m

cerebro.executar = _executar_mock   # o runtime real fica intocado; só aqui é dublê

perguntas = [json.loads(l) for l in open(AQUI / "perguntas.jsonl", encoding="utf-8")]
nome = Path(cerebro.ADAPTER).name

# GUARDA-CORPO: rodada interrompida não pode destruir um resultado COMPLETO.
# (Aconteceu: uma run morta no meio sobrescreveu o baseline do v11b com 65 respostas
# parciais, e só se descobre na hora de comparar.) Resultado completo vira .bak.
_saida = AQUI / "resultados" / f"bench_{nome}.json"
feitos = {}
if _saida.exists():
    try:
        _antigo = json.loads(_saida.read_text(encoding="utf-8"))
    except Exception:
        _antigo = []
    if len(_antigo) >= len(perguntas):
        _bak = _saida.with_suffix(".json.bak")
        _saida.replace(_bak)
        print(f"[bench] resultado completo anterior ({len(_antigo)}) preservado em {_bak.name}")
    else:
        # rodada interrompida: retomo de onde parou (só as respostas das MESMAS perguntas)
        _q = {p["id"]: p["q"] for p in perguntas}
        feitos = {r["id"]: r for r in _antigo if _q.get(r["id"]) == r.get("q")}
        if feitos:
            print(f"[bench] retomando: {len(feitos)} perguntas já respondidas")
print(f"[bench] {nome} — {len(perguntas)} perguntas, tools MOCKADAS (~2h30 no 27B)")
(AQUI / "resultados").mkdir(exist_ok=True)
model, processor, config = cerebro.carregar()

resultados, t_ini = [], time.time()
for p in perguntas:
    if p["id"] in feitos:
        resultados.append(feitos[p["id"]])
        continue
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
