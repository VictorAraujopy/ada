import json
import random
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
random.seed(50)

arq_a, arq_b = sys.argv[1], sys.argv[2]   # A = baseline, B = candidato
# o gabarito é um só pros dois idiomas: aceita "25.30" e "25,30", nomes próprios não mudam
JUIZES = ("ia",)  # quem julga o raciocínio (um arquivo julgamento_cego_<juiz>.md por juiz)
gab = {p["id"]: p for p in (json.loads(l) for l in open(AQUI / "perguntas.jsonl", encoding="utf-8"))}
res = {n: {r["id"]: r for r in json.loads((AQUI / "resultados" / a).read_text(encoding="utf-8"))}
       for n, a in (("A", arq_a), ("B", arq_b))}


def passou(p, r):
    resp, tools = r["resposta"].lower(), r["tools"]
    if p["cat"] in ("matematica", "matematica_dificil", "logica"):
        return any(a.lower() in resp for a in p["aceita"])
    if p["cat"] in ("uso_tool", "uso_tool_dificil"):
        if "tools_todas" in p:  # pedido duplo: tem que chamar TODAS
            return all(t in tools for t in p["tools_todas"])
        return any(t in tools for t in p["tools_esperadas"])
    if p["cat"] in ("armadilha_tool", "armadilha_dificil"):
        return not tools
    if p["cat"] == "factual":
        # cada item tem que aparecer; item que é lista = alternativas (ex.: "preto e branco" ou "black and white")
        return all(any(a in resp for a in (k if isinstance(k, list) else [k])) for k in p["deve_conter"])
    if p["cat"] == "ambiguo":
        # pediu contexto: pergunta direta OU pedido imperativo (jeito dela: "cola o código")
        import re as _re
        pediu = "?" in r["resposta"] or _re.search(
            r"\b(me (diz|diga|conta|fala|passa|manda|mostra|dá|da|de)|cola (aqui|o|a|teu|seu)|manda (o|a|aqui)|preciso saber"
            r"|tell me|give me|let me know|paste (it|the|your|here)|send (me|it|the)|share (it|the|your)|show me|i need to know)\b",
            r["resposta"].lower())
        return bool(pediu) and not tools
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
mapa, linhas = {}, ["# Julgamento — raciocínio",
                    "", "Pra cada pergunta: leia as duas respostas e preencha a linha `vencedor:` com",
                    "**1**, **2** ou **empate**. Não abra o _mapa_cego.json antes. (Se os modelos respondem",
                    "em idiomas diferentes, o idioma entrega quem é quem: aí o julgamento NÃO é cego.)", ""]
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
for juiz in JUIZES:
    alvo = AQUI / "resultados" / f"julgamento_cego_{juiz}.md"
    # NUNCA sobrescreve julgamento já preenchido (lição aprendida na prática)
    if alvo.exists() and __import__("re").search(r"vencedor: \S", alvo.read_text(encoding="utf-8")):
        print(f"    (julgamento_{juiz} já preenchido — preservado)")
        continue
    alvo.write_text("\n".join(linhas), encoding="utf-8")
(AQUI / "resultados" / "_mapa_cego.json").write_text(json.dumps(mapa))
print(f"\n>>> placar.json salvo. Julgamento do raciocínio: preencher {', '.join(f'julgamento_cego_{j}.md' for j in JUIZES)}")
print("    e depois rodar gerar_grafico.py")
