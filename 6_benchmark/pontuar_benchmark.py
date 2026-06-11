"""
Pontua as categorias OBJETIVAS dos dois adapters e prepara o julgamento cego.

    .venv/bin/python 6_benchmark/pontuar_benchmark.py bench_ada_v10_9b.json bench_ada_v11b_a16_9b.json

Critérios (declarados — fazem parte da metodologia do post):
  matematica     resposta contém o valor correto do gabarito
  uso_tool       chamou uma das tools esperadas
  armadilha_tool NÃO chamou tool nenhuma
  factual        contém o fato da ficha (case-insensitive)
  ambiguo        pediu contexto (tem "?") e não chamou tool
  raciocinio     não pontua aqui -> vai pro julgamento_cego.md (você decide)

Sai: placar.json + julgamento_cego.md (+ _mapa_cego.json, NÃO abra antes de julgar).
"""
import json
import random
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
random.seed(50)

arq_a, arq_b = sys.argv[1], sys.argv[2]   # A = baseline (v10), B = candidato (v11b)
gab = {p["id"]: p for p in (json.loads(l) for l in open(AQUI / "perguntas.jsonl", encoding="utf-8"))}
res = {n: {r["id"]: r for r in json.loads((AQUI / "resultados" / a).read_text(encoding="utf-8"))}
       for n, a in (("A", arq_a), ("B", arq_b))}


def passou(p, r):
    resp, tools = r["resposta"].lower(), r["tools"]
    if p["cat"] == "matematica":
        return any(a.lower() in resp for a in p["aceita"])
    if p["cat"] == "uso_tool":
        return any(t in tools for t in p["tools_esperadas"])
    if p["cat"] == "armadilha_tool":
        return not tools
    if p["cat"] == "factual":
        return all(k in resp for k in p["deve_conter"])
    if p["cat"] == "ambiguo":
        return "?" in r["resposta"] and not tools
    return None  # raciocinio: julgamento humano


placar = {}
for lado in ("A", "B"):
    por_cat = {}
    for pid, p in gab.items():
        ok = passou(p, res[lado][pid])
        if ok is None:
            continue
        por_cat.setdefault(p["cat"], []).append(ok)
    placar[lado] = {c: {"acertos": sum(v), "total": len(v), "pct": round(100 * sum(v) / len(v))}
                    for c, v in por_cat.items()}

(AQUI / "resultados" / "placar.json").write_text(json.dumps(
    {"arquivos": {"A": arq_a, "B": arq_b}, "placar": placar}, ensure_ascii=False, indent=1))

print(f"{'categoria':<16} {'A (' + arq_a[6:-5] + ')':>22} {'B (' + arq_b[6:-5] + ')':>22}")
for c in placar["A"]:
    a, b = placar["A"][c], placar["B"][c]
    print(f"{c:<16} {a['acertos']:>9}/{a['total']} ({a['pct']}%) {b['acertos']:>9}/{b['total']} ({b['pct']}%)")

# ---- julgamento cego do raciocínio: ordem A/B embaralhada por pergunta ----
mapa, linhas = {}, ["# Julgamento cego — raciocínio",
                    "", "Pra cada pergunta: leia as duas respostas SEM saber de qual modelo são e",
                    "preencha a linha `vencedor:` com **1**, **2** ou **empate**. Não abra o _mapa_cego.json antes.", ""]
for pid, p in gab.items():
    if p["cat"] != "raciocinio":
        continue
    ordem = ["A", "B"]
    random.shuffle(ordem)
    mapa[str(pid)] = ordem
    linhas += [f"## P{pid} — {p['q']}", ""]
    for i, lado in enumerate(ordem, 1):
        linhas += [f"**Resposta {i}:**", res[lado][pid]["resposta"], ""]
    linhas += ["vencedor: ", "", "---", ""]
for juiz in ("victor", "fable"):
    (AQUI / "resultados" / f"julgamento_cego_{juiz}.md").write_text("\n".join(linhas), encoding="utf-8")
(AQUI / "resultados" / "_mapa_cego.json").write_text(json.dumps(mapa))
print("\n>>> placar.json salvo. Julgamento cego DUPLO: você preenche o _victor.md,")
print("    o Claude preenche o _fable.md (mandando ele ler SÓ esse arquivo). Depois: gerar_grafico.py")
