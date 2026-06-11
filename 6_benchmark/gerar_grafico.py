"""
Gera o gráfico de comparação (SVG, identidade visual da ADA) a partir do
placar.json + julgamento_cego.md preenchido.

    .venv/bin/python 2_treino/v11_build/benchmark/gerar_grafico.py

Sai grafico_benchmark.svg — abre no navegador, dá zoom e tira o screenshot
pro LinkedIn (ou exporta PNG com qualquer conversor).
"""
import json
import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent
dados = json.loads((AQUI / "resultados" / "placar.json").read_text(encoding="utf-8"))
placar = dados["placar"]

# raciocínio: lê os "vencedor:" do julgamento cego e desfaz o embaralhamento
mapa = json.loads((AQUI / "resultados" / "_mapa_cego.json").read_text(encoding="utf-8"))
juizes = {}
for juiz in ("victor", "fable"):
    arq = AQUI / "resultados" / f"julgamento_cego_{juiz}.md"
    if not arq.exists():
        continue
    blocos = re.findall(r"## P(\d+).*?vencedor:\s*([^\n]*)", arq.read_text(encoding="utf-8"), re.DOTALL)
    votos, julgados, escolhas = {"A": 0.0, "B": 0.0}, 0, {}
    for pid, v in blocos:
        v = v.strip().lower()
        if v in ("1", "2"):
            lado = mapa[pid][int(v) - 1]
            votos[lado] += 1; escolhas[pid] = lado; julgados += 1
        elif v.startswith("emp"):
            votos["A"] += 0.5; votos["B"] += 0.5; escolhas[pid] = "empate"; julgados += 1
    if julgados:
        juizes[juiz] = {"votos": votos, "julgados": julgados, "escolhas": escolhas}

if juizes:
    n = len(juizes)
    for lado in ("A", "B"):
        pct = sum(100 * j["votos"][lado] / j["julgados"] for j in juizes.values()) / n
        placar[lado]["raciocinio"] = {"acertos": round(sum(j["votos"][lado] for j in juizes.values()) / n, 1),
                                      "total": max(j["julgados"] for j in juizes.values()),
                                      "pct": round(pct)}
    if len(juizes) == 2:
        ev, ef = juizes["victor"]["escolhas"], juizes["fable"]["escolhas"]
        comum = set(ev) & set(ef)
        iguais = sum(1 for p in comum if ev[p] == ef[p])
        print(f"concordância entre os juízes (humano x Fable): {iguais}/{len(comum)}")
else:
    print("AVISO: nenhum julgamento preenchido — gráfico sai sem a categoria raciocínio")

NOMES = {"matematica": "Matemática do dia a dia", "uso_tool": "Uso correto de ferramentas",
         "armadilha_tool": "Resistência a tool espúria", "factual": "Precisão factual (TWD)",
         "ambiguo": "Pede contexto quando falta", "raciocinio": "Raciocínio (cego duplo)"}
ORDEM = [c for c in NOMES if c in placar["A"]]

BG, INK, DIM, GRID = "#0a0908", "#ece7de", "#847d72", "#2a2724"
COR_A, COR_B = "#56504a", "#b3171d"   # v10 cinza, v11b sangue
W, ALT_CAT, X0, BARW = 980, 78, 330, 560
H = 150 + len(ORDEM) * ALT_CAT + 70

s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="Georgia, serif">',
     f'<rect width="{W}" height="{H}" fill="{BG}"/>',
     f'<text x="40" y="56" fill="{INK}" font-size="30" letter-spacing="6">ADA — v10 vs v11b</text>',
     f'<text x="40" y="84" fill="{DIM}" font-size="13" font-family="Helvetica" letter-spacing="1">'
     f'benchmark próprio · 50 perguntas · Qwen3.5-9B 4-bit + LoRA · 100% local</text>',
     f'<rect x="40" y="104" width="14" height="14" fill="{COR_A}"/>'
     f'<text x="62" y="116" fill="{DIM}" font-size="13" font-family="Helvetica">ada v10</text>',
     f'<rect x="140" y="104" width="14" height="14" fill="{COR_B}"/>'
     f'<text x="162" y="116" fill="{INK}" font-size="13" font-family="Helvetica">ada v11b</text>']

y = 150
for cat in ORDEM:
    a, b = placar["A"][cat], placar["B"][cat]
    s.append(f'<text x="{X0 - 18}" y="{y + 26}" fill="{INK}" font-size="14.5" '
             f'font-family="Helvetica" text-anchor="end">{NOMES[cat]}</text>')
    for i, (val, cor, lab) in enumerate(((a, COR_A, "A"), (b, COR_B, "B"))):
        by = y + i * 22
        w = BARW * val["pct"] / 100
        s.append(f'<rect x="{X0}" y="{by}" width="{max(w, 2):.0f}" height="16" fill="{cor}"/>')
        s.append(f'<text x="{X0 + max(w, 2) + 10:.0f}" y="{by + 13}" fill="{INK if lab == "B" else DIM}" '
                 f'font-size="13" font-family="Helvetica">{val["pct"]}%</text>')
    s.append(f'<line x1="{X0}" y1="{y + 52}" x2="{X0 + BARW}" y2="{y + 52}" stroke="{GRID}" stroke-width="0.5"/>')
    y += ALT_CAT

s.append(f'<text x="40" y="{H - 28}" fill="{DIM}" font-size="11.5" font-family="Helvetica">'
         f'Categorias objetivas pontuadas por script contra gabarito; raciocínio por julgamento cego duplo (humano + Fable 5). '
         f'Perguntas fora do dataset de treino.</text>')
s.append(f'<text x="40" y="{H - 12}" fill="#3a302e" font-size="10" font-family="Helvetica" '
         f'letter-spacing="3">WE ARE THE WALKING DEAD</text>')
s.append('</svg>')

(AQUI / "resultados" / "grafico_benchmark.svg").write_text("\n".join(s), encoding="utf-8")
print(">>> grafico_benchmark.svg pronto — abre no navegador e confere os números no placar.json")
