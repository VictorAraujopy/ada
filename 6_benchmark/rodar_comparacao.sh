#!/bin/bash
# Roda o benchmark completo nos dois adapters e deixa tudo pronto pro julgamento cego.
#
# Rode do TERMINAL normal (não pelo Claude Code — processo de 3h não sobrevive lá):
#     bash 6_benchmark/rodar_comparacao.sh
#
# Ou desgrudado do terminal (pode fechar a janela, continua rodando):
#     nohup bash 6_benchmark/rodar_comparacao.sh > /tmp/bench.log 2>&1 &
#     tail -f /tmp/bench.log          # acompanhar
#
# ~1h30 por modelo (um de cada vez: 16GB não aguenta os dois).
# caffeinate impede o Mac de dormir no meio.

set -e
cd "$(dirname "$0")/.."

echo "=== 1/3 — v11b (baseline) ==="
caffeinate -i env ADA_ADAPTER=ada_v11b_a16_9b .venv/bin/python 6_benchmark/rodar_benchmark.py

echo "=== 2/3 — v12 ==="
caffeinate -i env ADA_ADAPTER=ada_v12_a16_9b .venv/bin/python 6_benchmark/rodar_benchmark.py

echo "=== 3/3 — pontuando as objetivas ==="
.venv/bin/python 6_benchmark/pontuar_benchmark.py \
    bench_ada_v11b_a16_9b.json bench_ada_v12_a16_9b.json

echo
echo "PRONTO. Agora o julgamento cego (só você pode fazer):"
echo "  1. preencha 6_benchmark/resultados/julgamento_cego_victor.md (vencedor: 1 | 2 | empate)"
echo "  2. peça pro Claude preencher o julgamento_cego_fable.md (ele só lê ESSE arquivo)"
echo "  3. .venv/bin/python 6_benchmark/gerar_grafico.py"
